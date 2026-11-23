"""Módulo "Mis Finanzas": liquidación, guardado e historial.

Responsabilidad
---------------
- Precargar el sueldo desde el perfil y el descuento de incapacidad del mes a
  partir de las fechas registradas.
- Liquidar el periodo en el servidor (POST clásico, sin JavaScript) y en JSON
  para el recálculo en vivo.
- Guardar la liquidación con su periodo (mensual o quincenal), listar el
  historial, comparar meses, exportar a CSV e imprimir.

SRS v1.5: la incapacidad se descuenta por tramo mensual. No hay rollover: cada
periodo toma solo los días que le corresponden del rango registrado.

La aritmética vive en `app.servicios.nomina`; este router solo valida entradas,
persiste y presenta resultados.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.core.config import ETIQUETAS_TIPO_HORA, FACTORES_RECARGO
from app.core.numeros import a_decimal, redondear_dinero
from app.core.texto import (
    formatear_cop,
    formatear_fecha,
    formatear_mes_anio,
    parsear_monto,
)
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.modelos import DeduccionFija, PerfilFinanciero, PeriodoNomina
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, deudas, gastos, pagos_metas, perfiles, periodos, registro_incapacidades
from app.servicios import deducciones_fijas
from app.servicios.incapacidad import (
    LiquidacionIncapacidad,
    ResultadoMesIncapacidad,
    TramoMensual,
    calcular_incapacidad,
    liquidar_mes_incapacidad,
)
from app.servicios import chancucos as servicio_chancucos
from app.servicios import quincenas
from app.servicios.nomina import (
    DeduccionesLey,
    LiquidacionNomina,
    calcular_deducciones_ley,
    liquidar_periodo,
)

router = APIRouter(tags=["Finanzas"])

CAMPOS_HORAS: tuple[str, ...] = tuple(f"horas_{tipo}" for tipo in FACTORES_RECARGO)
CERO = Decimal("0")


@dataclass
class EntradaFinanzas:
    """Entradas del formulario ya normalizadas.

    Attributes:
        valores: Texto original por campo (para repoblar la plantilla).
        sueldo: Sueldo básico convertido, o `None` si es inválido.
        horas: Horas por tipo de recargo (solo las mayores que cero).
        deduccion_incapacidad: Descuento por incapacidad del periodo.
        anio: Año del periodo seleccionado.
        mes: Mes del periodo (1–12).
        quincena: `0` mensual, `1` o `2` quincenal.
        perfil: Perfil financiero del usuario, si ya lo configuró.
        errores: Mensajes de validación para mostrar al usuario.
    """

    valores: dict[str, str] = field(default_factory=dict)
    sueldo: Decimal | None = None
    horas: dict[str, Decimal] = field(default_factory=dict)
    deduccion_incapacidad: Decimal = CERO
    anio: int = field(default_factory=lambda: date.today().year)
    mes: int = field(default_factory=lambda: date.today().month)
    quincena: int = 0
    perfil: PerfilFinanciero | None = None
    detalle_incapacidad: ResultadoMesIncapacidad | None = None
    # SRS v1.5: rango completo y tramos por mes para mostrar el desglose; el
    # descuento que se aplica es solo el del periodo elegido.
    liquidacion_incapacidad: LiquidacionIncapacidad | None = None
    tramos_incapacidad: list[TramoMensual] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    @property
    def etiqueta_periodo(self) -> str:
        """Devuelve el periodo seleccionado en texto legible.

        Returns:
            Cadena como ``"Noviembre de 2026 · Quincena 1"``.
        """
        base = formatear_mes_anio(self.anio, self.mes)
        if self.quincena == 0:
            return base
        return f"{base} · Quincena {self.quincena}"


def _texto(datos: Mapping[str, Any], clave: str, defecto: str = "") -> str:
    """Extrae un campo de texto y lo normaliza.

    Args:
        datos: Diccionario del formulario o del JSON.
        clave: Nombre del campo.
        defecto: Valor a usar si el campo no viene.

    Returns:
        El texto sin espacios externos.
    """
    valor = datos.get(clave, defecto)
    return str(valor).strip() if valor is not None else ""


def _entero(texto: str, defecto: int, etiqueta: str, errores: list[str]) -> int:
    """Convierte un campo entero del formulario.

    Args:
        texto: Valor recibido.
        defecto: Valor a usar si viene vacío.
        etiqueta: Nombre legible del campo.
        errores: Lista donde se acumulan los mensajes.

    Returns:
        El entero convertido o el valor por defecto.
    """
    if not texto:
        return defecto
    try:
        return int(texto)
    except ValueError:
        errores.append(f"El campo '{etiqueta}' debe ser un número entero.")
        return defecto


def _descuento_por_fechas(datos: Mapping[str, Any], entrada: EntradaFinanzas) -> Decimal:
    """Calcula el descuento del mes por incapacidad a partir de sus fechas.

    Usa el sueldo mensual del perfil (o el del formulario si no hay perfil) porque
    la incapacidad se liquida sobre el salario mensual; el resultado reduce luego
    el sueldo proyectado de la quincena.

    Args:
        datos: Campos enviados con `incapacidad_inicio` e `incapacidad_fin`.
        entrada: Entrada en construcción; se guarda el detalle para la vista.

    Returns:
        Descuento del mes en pesos; cero si las fechas están incompletas o no hay
        sueldo. Un rango inválido se registra como error de validación.
    """
    texto_inicio = _texto(datos, "incapacidad_inicio")
    texto_fin = _texto(datos, "incapacidad_fin")
    if not texto_inicio or not texto_fin:
        # Mientras el usuario escribe, un rango incompleto no es un error.
        return CERO
    try:
        inicio = date.fromisoformat(texto_inicio)
        fin = date.fromisoformat(texto_fin)
    except ValueError:
        entrada.errores.append("Las fechas de la incapacidad no son válidas.")
        return CERO

    if entrada.perfil is not None:
        base = entrada.perfil.sueldo_basico
    elif entrada.sueldo is not None:
        base = entrada.sueldo
    else:
        return CERO

    try:
        detalle = liquidar_mes_incapacidad(
            inicio, fin, base, anio=entrada.anio, mes=entrada.mes
        )
        liquidacion = calcular_incapacidad(inicio, fin, base)
    except ValueError as error:
        entrada.errores.append(str(error))
        return CERO
    entrada.detalle_incapacidad = detalle
    entrada.liquidacion_incapacidad = liquidacion
    # SRS v1.5: todos los tramos se muestran; solo el del periodo se descuenta.
    entrada.tramos_incapacidad = list(liquidacion.tramos)
    return detalle.valor_descontado


def _leer_entradas(
    datos: Mapping[str, Any],
    bd: Session,
    id_usuario: str,
) -> EntradaFinanzas:
    """Valida y convierte los datos de la calculadora.

    Args:
        datos: Campos enviados por formulario o JSON.
        bd: Sesión de base de datos (para el perfil y las incapacidades).
        id_usuario: Dueño de la liquidación.

    Returns:
        `EntradaFinanzas` con los valores convertidos y la lista de errores.
    """
    entrada = EntradaFinanzas()
    hoy = date.today()

    entrada.anio = _entero(_texto(datos, "anio"), hoy.year, "año", entrada.errores)
    entrada.mes = _entero(_texto(datos, "mes"), hoy.month, "mes", entrada.errores)
    entrada.quincena = _entero(
        _texto(datos, "quincena"), 0, "quincena", entrada.errores
    )
    if not 1 <= entrada.mes <= 12:
        entrada.errores.append("El mes debe estar entre 1 y 12.")
    if entrada.quincena not in (0, 1, 2):
        entrada.errores.append("La quincena debe ser 0 (mensual), 1 o 2.")

    perfil = perfiles.obtener_perfil(bd, id_usuario)
    entrada.perfil = perfil
    entrada.valores["anio"] = str(entrada.anio)
    entrada.valores["mes"] = str(entrada.mes)
    entrada.valores["quincena"] = str(entrada.quincena)

    # El sueldo se puede escribir; si se deja vacío se toma del perfil.
    texto_sueldo = _texto(datos, "sueldo_basico")
    if not texto_sueldo and perfil is not None:
        texto_sueldo = f"{perfiles.sueldo_del_periodo(perfil, entrada.quincena):.2f}"
    entrada.valores["sueldo_basico"] = texto_sueldo

    if not texto_sueldo:
        entrada.errores.append(
            "El sueldo básico es obligatorio. Configúralo en Mi perfil para no escribirlo cada vez."
        )
    else:
        try:
            entrada.sueldo = parsear_monto(texto_sueldo)
            if entrada.sueldo <= CERO:
                entrada.errores.append("El sueldo básico debe ser mayor que cero.")
        except ValueError as error:
            entrada.errores.append(str(error))

    for tipo in FACTORES_RECARGO:
        campo = f"horas_{tipo}"
        texto = _texto(datos, campo, "0") or "0"
        entrada.valores[campo] = texto
        try:
            cantidad = a_decimal(texto, campo)
        except ValueError:
            entrada.errores.append(f"Las horas de '{ETIQUETAS_TIPO_HORA[tipo]}' no son válidas.")
            continue

        if cantidad < CERO:
            entrada.errores.append(
                f"Las horas de '{ETIQUETAS_TIPO_HORA[tipo]}' no pueden ser negativas."
            )
        elif cantidad > CERO:
            entrada.horas[tipo] = cantidad

    # SRS v1.5: la incapacidad se descuenta por tramo del mes elegido. Si el
    # formulario trae fechas, manda el rango escrito; si no, se toman las
    # incapacidades registradas que cubren el periodo (reemplazo del rollover).
    texto_inicio = _texto(datos, "incapacidad_inicio")
    texto_fin = _texto(datos, "incapacidad_fin")
    # SRS v1.6: «Limpiar» omite las registradas para este cálculo: el sueldo y las
    # quincenas vuelven a su valor base sin borrar nada.
    omitir_registradas = _texto(datos, "incapacidad_omitir") == "1"
    if texto_inicio and texto_fin:
        entrada.deduccion_incapacidad = _descuento_por_fechas(datos, entrada)
        entrada.valores["incapacidad_inicio"] = texto_inicio
        entrada.valores["incapacidad_fin"] = texto_fin
    elif omitir_registradas:
        entrada.deduccion_incapacidad = CERO
    else:
        base_incapacidad = (
            entrada.perfil.sueldo_basico
            if entrada.perfil is not None
            else entrada.sueldo
        )
        if base_incapacidad is not None and base_incapacidad > CERO:
            tramos = registro_incapacidades.tramos_del_mes(
                bd, id_usuario, entrada.anio, entrada.mes, base_incapacidad
            )
            entrada.tramos_incapacidad = tramos
            entrada.deduccion_incapacidad = redondear_dinero(
                sum((tramo.valor_descontado for tramo in tramos), start=CERO)
            )

    entrada.valores["deduccion_incapacidad"] = f"{entrada.deduccion_incapacidad:.2f}"
    return entrada


def _liquidar(entrada: EntradaFinanzas) -> LiquidacionNomina | None:
    """Liquida el periodo cuando la entrada no tiene errores.

    Args:
        entrada: Datos ya validados.

    Returns:
        La liquidación o `None` si hay errores o falta el sueldo.
    """
    if entrada.errores or entrada.sueldo is None:
        return None

    liquidacion = liquidar_periodo(
        sueldo_basico=entrada.sueldo,
        horas_por_tipo=entrada.horas,
        deduccion_incapacidad=entrada.deduccion_incapacidad,
        aplicar_auxilio_legal=True,
    )
    return _deducciones_segun_quincena(entrada, liquidacion)


def _deducciones_segun_quincena(
    entrada: EntradaFinanzas, liquidacion: LiquidacionNomina
) -> LiquidacionNomina:
    """Imputa salud y pensión al pago que corresponde según el perfil.

    En modalidad `QUINCENAL`, la ley se calcula sobre el sueldo básico
    **mensual** y se resta únicamente de la quincena indicada en
    `perfil.quincena_deducciones` (RF-05 del SRS). En la otra quincena no hay
    deducciones de ley. En modalidad mensual o con periodo de mes completo se
    mantiene el cálculo ordinario.

    Args:
        entrada: Entrada normalizada con el periodo y el perfil.
        liquidacion: Resultado del motor salarial.

    Returns:
        La liquidación original o una copia con las deducciones ajustadas.
    """
    perfil = entrada.perfil
    if (
        perfil is None
        or perfil.modalidad_pago != perfiles.MODALIDAD_QUINCENAL
        or entrada.quincena not in (1, 2)
    ):
        return liquidacion

    if perfil.quincena_deducciones == entrada.quincena:
        # SRS v1.4: la base es el salario mensual devengado, igual que en el panel
        # de quincenas: sueldo + horas extras y recargos − incapacidad.
        base_mensual = max(
            perfil.sueldo_basico + liquidacion.total_recargos - liquidacion.deduccion_incapacidad,
            CERO,
        )
        deducciones = calcular_deducciones_ley(redondear_dinero(base_mensual))
    else:
        deducciones = DeduccionesLey(salud=CERO, pension=CERO, total=CERO)

    total_deducciones = redondear_dinero(
        deducciones.total + liquidacion.deduccion_incapacidad
    )
    return replace(
        liquidacion,
        deducciones_ley=deducciones,
        total_deducciones=total_deducciones,
        saldo_bolsillo=redondear_dinero(
            liquidacion.total_ingresos - total_deducciones
        ),
    )


def _datos_formateados(liquidacion: LiquidacionNomina) -> dict[str, str]:
    """Prepara los totales como texto para actualizar el DOM.

    Args:
        liquidacion: Resultado del motor de nómina.

    Returns:
        Diccionario ``campo → texto formateado``.
    """
    return {
        # SRS v1.4: el sueldo que llega a las quincenas ya incluye extras y el
        # descuento por incapacidad.
        "sueldo_proyectado": formatear_cop(
            redondear_dinero(liquidacion.total_devengado - liquidacion.deduccion_incapacidad)
        ),
        "valor_hora": formatear_cop(liquidacion.valor_hora_ordinaria),
        "total_horas_extra": f"{liquidacion.total_horas_extra:.2f}".replace(".", ","),
        "total_recargos": formatear_cop(liquidacion.total_recargos),
        "deduccion_salud": formatear_cop(liquidacion.deducciones_ley.salud),
        "deduccion_pension": formatear_cop(liquidacion.deducciones_ley.pension),
        "auxilio_transporte": formatear_cop(liquidacion.auxilio_transporte),
        "deduccion_incapacidad": formatear_cop(liquidacion.deduccion_incapacidad),
        "total_devengado": formatear_cop(liquidacion.total_devengado),
        "total_ingresos": formatear_cop(liquidacion.total_ingresos),
        "total_deducciones": formatear_cop(liquidacion.total_deducciones),
        "saldo_bolsillo": formatear_cop(liquidacion.saldo_bolsillo),
    }


def _detalle_formateado(liquidacion: LiquidacionNomina) -> list[dict[str, str]]:
    """Convierte el desglose de recargos en filas listas para la tabla.

    SRS v1.5: solo se publican concepto, horas y valor. El factor se omite para
    que la tabla quepa sin desplazamiento horizontal en el móvil.

    Args:
        liquidacion: Resultado del motor de nómina.

    Returns:
        Lista de diccionarios con etiqueta, horas y valor.
    """
    return [
        {
            "etiqueta": item.etiqueta,
            "horas": f"{item.cantidad_horas:.2f}".replace(".", ","),
            "valor": formatear_cop(item.valor_total),
        }
        for item in liquidacion.detalle_recargos
    ]


def _detalle_incapacidad_json(entrada: EntradaFinanzas) -> dict[str, object] | None:
    """Resume la incapacidad del periodo y sus tramos mensuales.

    SRS v1.5: la interfaz muestra el desglose por mes y solo descuenta el tramo
    del periodo elegido.

    Args:
        entrada: Entrada normalizada con los tramos ya calculados.

    Returns:
        Días del mes, reparto 100 %/66,67 %, descuento aplicado y la lista de
        tramos; `None` si no hay incapacidad.
    """
    tramos = entrada.tramos_incapacidad
    if not tramos:
        return None

    actuales = [
        tramo
        for tramo in tramos
        if (tramo.anio, tramo.mes) == (entrada.anio, entrada.mes)
    ]
    return {
        "dias_mes": sum(tramo.dias for tramo in actuales),
        "dias_al_100": sum(tramo.dias_al_100 for tramo in actuales),
        "dias_al_66": sum(tramo.dias_al_66 for tramo in actuales),
        "descuento": formatear_cop(entrada.deduccion_incapacidad),
        "tramos": [
            {
                "periodo": formatear_mes_anio(tramo.anio, tramo.mes),
                "anio": tramo.anio,
                "mes": tramo.mes,
                "dias": tramo.dias,
                "dias_al_100": tramo.dias_al_100,
                "dias_al_66": tramo.dias_al_66,
                "descuento": formatear_cop(tramo.valor_descontado),
                "actual": (tramo.anio, tramo.mes) == (entrada.anio, entrada.mes),
            }
            for tramo in tramos
        ],
    }


def _fijas_del_periodo(
    bd: Session, id_usuario: str, quincena: int
) -> list[DeduccionFija]:
    """Devuelve las deducciones fijas que se restan del periodo consultado.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deducciones.
        quincena: `0` mes completo, `1` o `2` quincena.

    Returns:
        Las deducciones que aplican al periodo. En el mes completo se incluyen
        las de las dos quincenas.
    """
    fijas = deducciones_fijas.listar_deducciones(bd, id_usuario)
    if quincena in (1, 2):
        return [deduccion for deduccion in fijas if deduccion.quincena == quincena]
    return fijas


def _total_fijas(fijas: list[DeduccionFija]) -> Decimal:
    """Suma el valor de las deducciones fijas de un periodo.

    Args:
        fijas: Deducciones que aplican al periodo.

    Returns:
        Total en pesos redondeado a centavos.
    """
    return redondear_dinero(sum((deduccion.valor for deduccion in fijas), start=CERO))


def _total_deducciones_ley(
    liquidacion: LiquidacionNomina | None, fijas: list[DeduccionFija]
) -> Decimal:
    """Suma salud, pensión, incapacidad del mes y deducciones fijas.

    SRS v1.5: la caja «Deducciones de ley» muestra un único total con todo lo
    que se descuenta del periodo, incluida la incapacidad.

    Args:
        liquidacion: Resultado del motor de nómina, o `None` si no se ha calculado.
        fijas: Deducciones fijas que aplican al periodo.

    Returns:
        Total en pesos; cero cuando todavía no hay liquidación.
    """
    if liquidacion is None:
        return CERO
    return redondear_dinero(
        liquidacion.deducciones_ley.total
        + liquidacion.deduccion_incapacidad
        + _total_fijas(fijas)
    )


def _saldos_quincenas(
    bd: Session,
    id_usuario: str,
    entrada: EntradaFinanzas,
    liquidacion: LiquidacionNomina,
) -> list[dict[str, object]]:
    """Calcula los saldos de cada pago con los valores que se están editando.

    SRS v1.4, REQ-04 y REQ-05: el recálculo en vivo debe reflejar en el panel de
    quincenas los recargos y el descuento por incapacidad del formulario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los datos.
        entrada: Entrada normalizada (incluye el perfil).
        liquidacion: Liquidación del periodo ya calculada.

    Returns:
        Lista de diccionarios con número de pago, ingreso, deducciones, deducciones
        fijas, saldo libre formateados y la bandera `negativo` para la interfaz.
    """
    resumen = quincenas.resumen_quincenas(
        bd,
        id_usuario,
        entrada.perfil,
        entrada.anio,
        entrada.mes,
        recargos=liquidacion.total_recargos,
        descuento_incapacidad=entrada.deduccion_incapacidad,
        auxilio_transporte=liquidacion.auxilio_transporte,
        sueldo_basico=entrada.sueldo,
    )
    return [
        {
            "numero": fila.numero,
            # SRS v4.10: la tarjeta muestra el sueldo ya neto de ley para no
            # restarlo dos veces. La dona sigue leyendo `fila.ingreso`.
            "ingreso": formatear_cop(fila.sueldo_neto_corte),
            "saldo_libre": formatear_cop(fila.saldo_libre),
            "negativo": fila.saldo_libre < CERO,
        }
        for fila in resumen
    ]


def _contexto_calculadora(
    usuario: UsuarioSesion,
    bd: Session,
    entrada: EntradaFinanzas,
    *,
    resultado: LiquidacionNomina | None = None,
    guardado: bool = False,
    guardado_gasto: bool = False,
    error_gasto: str = "",
    guardado_chancuco: bool = False,
    error_chancuco: str = "",
) -> dict[str, object]:
    """Construye el contexto completo de la calculadora.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        entrada: Entrada normalizada.
        resultado: Liquidación calculada, si existe.
        guardado: Bandera de éxito del guardado de la liquidación.
        guardado_gasto: Bandera de éxito al agregar un gasto fijo.
        error_gasto: Mensaje de error del formulario de gastos fijos.
        guardado_chancuco: Bandera de éxito al crear un chancuco embebido.
        error_chancuco: Mensaje de error del formulario de chancucos.

    Returns:
        Diccionario para la plantilla.
    """
    # SRS v1.6: las metas se muestran como gastos fijos del mes visible.
    pagos_metas.asegurar_gastos_de_metas(bd, usuario.id_usuario, entrada.anio, entrada.mes)
    perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
    fijas_periodo = _fijas_del_periodo(bd, usuario.id_usuario, entrada.quincena)
    periodo_guardado = periodos.obtener_periodo(
        bd, usuario.id_usuario, entrada.anio, entrada.mes, entrada.quincena
    )
    resumen_pagos = quincenas.resumen_quincenas(
        bd,
        usuario.id_usuario,
        perfil,
        entrada.anio,
        entrada.mes,
        recargos=resultado.total_recargos if resultado else CERO,
        descuento_incapacidad=entrada.deduccion_incapacidad,
        auxilio_transporte=resultado.auxilio_transporte if resultado else None,
        sueldo_basico=entrada.sueldo,
    )
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Mis Finanzas",
            "hoy": date.today(),
            "tipos_hora": [
                {"clave": tipo, "etiqueta": ETIQUETAS_TIPO_HORA[tipo], "factor": factor}
                for tipo, factor in FACTORES_RECARGO.items()
            ],
            "valores": entrada.valores,
            "errores": entrada.errores,
            "resultado": resultado,
            "entrada": entrada,
            "perfil": perfil,
            "periodo_guardado": periodo_guardado,
            # SRS v1.5: sueldo de solo lectura que se muestra en la liquidación.
            "sueldo_periodo": (
                entrada.sueldo
                if entrada.sueldo is not None
                else (
                    perfiles.sueldo_del_periodo(perfil, entrada.quincena)
                    if perfil is not None
                    else None
                )
            ),
            # SRS v1.5: tramos mensuales de la incapacidad para el desglose.
            "tramos_incapacidad": entrada.tramos_incapacidad,
            "gasto_mes": gastos.total_gastos_mes(
                bd, usuario.id_usuario, entrada.anio, entrada.mes
            ),
            # SRS v4.10: total de gastos del mes para la nota del resultado.
            "total_gastos_mes": redondear_dinero(
                gastos.total_gastos_mes(bd, usuario.id_usuario, entrada.anio, entrada.mes)
                + sum(
                    (fija.valor for fija in deducciones_fijas.listar_vigentes(bd, usuario.id_usuario)),
                    start=CERO,
                )
            ),
            # Gastos del bloque visible: quincena seleccionada o mes completo.
            "gasto_periodo": gastos.total_gastos_periodo(
                bd, usuario.id_usuario, entrada.anio, entrada.mes, entrada.quincena
            ),
            "guardado": guardado,
            "guardado_gasto": guardado_gasto,
            "error_gasto": error_gasto or None,
            "guardado_chancuco": guardado_chancuco,
            "error_chancuco": error_chancuco or None,
            # Panel izquierdo: sueldo devengado, gastos y deducciones por corte.
            "resumen_quincenas": resumen_pagos,
            # SRS v4.8: total neto consolidado del periodo (suma de los cortes).
            "total_devengado_consolidado": redondear_dinero(
                sum((fila.devengado_neto for fila in resumen_pagos), start=CERO)
            ),
            # SRS v1.4, REQ-08: deducciones fijas del salario listadas en la liquidación.
            # SRS v1.5: se muestran una por una dentro de la caja de deducciones y
            # su valor se suma al total del periodo.
            "detalle_fijas_periodo": fijas_periodo,
            "deducciones_fijas_periodo": _total_fijas(fijas_periodo),
            "total_deducciones_ley": _total_deducciones_ley(resultado, fijas_periodo),
            # Chancucos (SRS v1.8): disponibles para todos los usuarios.
            "chancucos": servicio_chancucos.listar_chancucos(bd, usuario.id_usuario),
            # SRS v1.9: opciones del flujo «¿vincular con una deuda?».
            "deudas_activas": deudas.listar_vinculables(bd, usuario.id_usuario),
            "seccion": "liquidacion",
            "quincenas": (
                [0] if perfil is None or perfil.modalidad_pago == perfiles.MODALIDAD_MENSUAL else [0, 1, 2]
            ),
        }
    )
    return contexto


@router.get("/finanzas", response_class=HTMLResponse, name="ver_finanzas")
def ver_finanzas(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    anio: int | None = None,
    mes: int | None = None,
    quincena: int = 0,
    guardado: int = 0,
    guardado_gasto: int = 0,
    error_gasto: str = "",
    guardado_chancuco: int = 0,
    error_chancuco: str = "",
) -> HTMLResponse:
    """Muestra la calculadora con el perfil y el periodo precargados.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        anio: Año solicitado; por defecto el actual.
        mes: Mes solicitado; por defecto el actual.
        quincena: `0`, `1` o `2`.
        guardado: Bandera de éxito del guardado de la liquidación.
        guardado_gasto: Bandera de éxito al agregar un gasto fijo.
        error_gasto: Error devuelto por el formulario de gastos fijos.
        guardado_chancuco: Bandera de éxito al crear un chancuco embebido.
        error_chancuco: Error devuelto por el formulario de chancucos.

    Returns:
        HTML de la calculadora.
    """
    hoy = date.today()
    anio_efectivo = anio if anio and 1 <= anio <= 9999 else hoy.year
    mes_efectivo = mes if mes and 1 <= mes <= 12 else hoy.month
    quincena_efectiva = quincena if quincena in (0, 1, 2) else 0

    datos: dict[str, str] = {
        "anio": str(anio_efectivo),
        "mes": str(mes_efectivo),
        "quincena": str(quincena_efectiva),
    }
    guardado_periodo = periodos.obtener_periodo(
        bd, usuario.id_usuario, anio_efectivo, mes_efectivo, quincena_efectiva
    )
    if guardado_periodo is not None:
        datos["sueldo_basico"] = f"{guardado_periodo.sueldo_basico_periodo:.2f}"
        datos["deduccion_incapacidad"] = f"{guardado_periodo.deduccion_incapacidad:.2f}"
        horas = periodos.horas_del_periodo(bd, guardado_periodo.id_periodo)
        for tipo in FACTORES_RECARGO:
            datos[f"horas_{tipo}"] = f"{horas.get(tipo, CERO):.2f}"
    else:
        perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
        if perfil is not None:
            datos["sueldo_basico"] = f"{perfiles.sueldo_del_periodo(perfil, quincena_efectiva):.2f}"

    entrada = _leer_entradas(datos, bd, usuario.id_usuario)
    contexto = _contexto_calculadora(
        usuario,
        bd,
        entrada,
        guardado=bool(guardado),
        guardado_gasto=bool(guardado_gasto),
        error_gasto=error_gasto,
        guardado_chancuco=bool(guardado_chancuco),
        error_chancuco=error_chancuco,
    )
    return plantillas.TemplateResponse(request, "finanzas/index.html", contexto)


@router.post("/finanzas", response_class=HTMLResponse, name="procesar_finanzas")
async def procesar_finanzas(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Liquida el periodo con el POST clásico (respaldo sin JavaScript).

    Args:
        request: Petición HTTP con el formulario.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML con el resultado o los errores de validación.
    """
    formulario = await request.form()
    entrada = _leer_entradas(formulario, bd, usuario.id_usuario)
    liquidacion = _liquidar(entrada)
    contexto = _contexto_calculadora(usuario, bd, entrada, resultado=liquidacion)
    return plantillas.TemplateResponse(request, "finanzas/index.html", contexto)


@router.post("/finanzas/calcular", name="calcular_finanzas_json")
async def calcular_finanzas_json(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> JSONResponse:
    """Calcula el periodo y devuelve los totales en JSON para la UI reactiva.

    Args:
        request: Petición con un cuerpo JSON con los campos del formulario.
        usuario: Usuario autenticado (la sesión es obligatoria).
        bd: Sesión de base de datos.

    Returns:
        JSON con `ok`, los totales formateados, el desglose y el mensaje del
        auxilio; o `ok: false` con los errores de validación.
    """
    try:
        datos = await request.json()
    except ValueError:
        return JSONResponse(
            {"ok": False, "errores": ["El cuerpo de la solicitud no es JSON válido."]},
            status_code=400,
        )

    if not isinstance(datos, Mapping):
        return JSONResponse(
            {"ok": False, "errores": ["Se esperaba un objeto con los datos del formulario."]},
            status_code=400,
        )

    entrada = _leer_entradas(datos, bd, usuario.id_usuario)
    liquidacion = _liquidar(entrada)
    if liquidacion is None:
        return JSONResponse({"ok": False, "errores": entrada.errores}, status_code=400)

    mensaje = (
        liquidacion.evaluacion_auxilio.mensaje
        if liquidacion.evaluacion_auxilio is not None
        else ""
    )
    fijas_periodo = _fijas_del_periodo(bd, usuario.id_usuario, entrada.quincena)
    resumen_actual = quincenas.resumen_quincenas(
        bd,
        usuario.id_usuario,
        entrada.perfil,
        entrada.anio,
        entrada.mes,
        recargos=liquidacion.total_recargos,
        descuento_incapacidad=entrada.deduccion_incapacidad,
        auxilio_transporte=liquidacion.auxilio_transporte,
        sueldo_basico=entrada.sueldo,
    )
    total_neto = redondear_dinero(
        sum((fila.devengado_neto for fila in resumen_actual), start=CERO)
    )
    return JSONResponse(
        {
            "ok": True,
            "datos": {
                **_datos_formateados(liquidacion),
                "total_devengado_consolidado": formatear_cop(total_neto),
                "total_gastos_mes": formatear_cop(
                    redondear_dinero(
                        gastos.total_gastos_mes(
                            bd, usuario.id_usuario, entrada.anio, entrada.mes
                        )
                        + sum(
                            (
                                fija.valor
                                for fija in deducciones_fijas.listar_vigentes(
                                    bd, usuario.id_usuario
                                )
                            ),
                            start=CERO,
                        )
                    )
                ),
            },
            "detalle": _detalle_formateado(liquidacion),
            "mensaje_auxilio": mensaje,
            "aplica_auxilio": bool(
                liquidacion.evaluacion_auxilio
                and liquidacion.evaluacion_auxilio.aplica
            ),
            # SRS v1.5: total de la caja de deducciones de ley (incluye fijas).
            "deducciones_fijas_periodo": formatear_cop(_total_fijas(fijas_periodo)),
            "total_deducciones_ley": formatear_cop(
                _total_deducciones_ley(liquidacion, fijas_periodo)
            ),
            "quincenas": _saldos_quincenas(bd, usuario.id_usuario, entrada, liquidacion),
            "incapacidad": _detalle_incapacidad_json(entrada),
        }
    )


@router.post("/finanzas/guardar", name="guardar_liquidacion", response_model=None)
async def guardar_liquidacion(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Guarda la liquidación del periodo seleccionado.

    Args:
        request: Petición con el formulario.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al historial si se guarda; la calculadora con errores en
        caso contrario.
    """
    formulario = await request.form()
    entrada = _leer_entradas(formulario, bd, usuario.id_usuario)
    liquidacion = _liquidar(entrada)
    if liquidacion is None:
        contexto = _contexto_calculadora(usuario, bd, entrada)
        return plantillas.TemplateResponse(
            request, "finanzas/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    periodo = periodos.guardar_liquidacion(
        bd,
        usuario.id_usuario,
        entrada.anio,
        entrada.mes,
        entrada.quincena,
        liquidacion,
        entrada.horas,
        gastos.total_gastos_mes(bd, usuario.id_usuario, entrada.anio, entrada.mes),
    )
    auditoria.registrar(
        bd,
        usuario.id_usuario,
        "PERIODO_GUARDADO",
        "periodos_nomina",
        f"{entrada.etiqueta_periodo} · {formatear_cop(periodo.saldo_bolsillo)}",
    )
    return RedirectResponse(
        url="/finanzas/historial?guardado=1", status_code=status.HTTP_303_SEE_OTHER
    )


def _filas_historial(bd: Session, id_usuario: str) -> list[dict[str, object]]:
    """Prepara el historial con la variación frente al periodo anterior.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los periodos.

    Returns:
        Lista de diccionarios con periodo, fecha de guardado, total de extras,
        gastos, disponible y variación. La lista llega ordenada del más reciente
        al más antiguo.
    """
    lista = periodos.listar_periodos(bd, id_usuario)
    filas: list[dict[str, object]] = []
    for indice, periodo in enumerate(lista):
        anterior = lista[indice + 1] if indice + 1 < len(lista) else None
        variacion = (
            periodo.saldo_bolsillo - anterior.saldo_bolsillo
            if anterior is not None
            else CERO
        )
        filas.append(
            {
                "periodo": periodo,
                "etiqueta": _etiqueta_periodo(periodo),
                # La fecha de guardado se toma de `fecha_creacion`; en filas
                # actualizadas conserva el alta original, que es el dato
                # cronológico que pide el historial.
                "fecha_guardado": formatear_fecha(periodo.fecha_creacion),
                # "Total extras" agrupa horas extra y recargos, que el SRS v1.3
                # muestra en una sola columna.
                "total_extras": periodo.total_horas_extra + periodo.total_recargos,
                "disponible": periodo.saldo_bolsillo - periodo.total_gastos,
                "variacion": variacion,
                "anterior": anterior,
            }
        )
    return filas


def _etiqueta_periodo(periodo: PeriodoNomina) -> str:
    """Genera la etiqueta legible de un periodo guardado.

    Args:
        periodo: Fila de `periodos_nomina`.

    Returns:
        Texto como ``"Noviembre de 2026 · Quincena 1"``.
    """
    base = formatear_mes_anio(periodo.anio, periodo.mes)
    return base if periodo.quincena == 0 else f"{base} · Quincena {periodo.quincena}"


@router.get("/finanzas/historial", response_class=HTMLResponse, name="ver_historial")
def ver_historial(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra el historial de liquidaciones y la comparación entre meses.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.

    Returns:
        HTML del historial.
    """
    filas = _filas_historial(bd, usuario.id_usuario)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Historial",
            "filas": filas,
            "guardado": bool(guardado),
            "seccion": "historial",
            "total_devengado": sum(
                (fila["periodo"].total_devengado for fila in filas), start=CERO
            ),
            "total_bolsillo": sum(
                (fila["periodo"].saldo_bolsillo for fila in filas), start=CERO
            ),
        }
    )
    return plantillas.TemplateResponse(request, "historial/index.html", contexto)


@router.get("/finanzas/historial.csv", name="exportar_historial_csv")
def exportar_historial_csv(
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> Response:
    """Exporta el historial a CSV compatible con Excel en español.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Respuesta `text/csv` con separador punto y coma.
    """
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
    escritor.writerow(
        [
            "Periodo",
            "Sueldo del periodo",
            "Horas extra",
            "Recargos",
            "Salud",
            "Pensión",
            "Auxilio transporte",
            "Descuento incapacidad",
            "Total devengado",
            "Total deducciones",
            "Saldo bolsillo",
            "Gastos",
        ]
    )
    for periodo in periodos.listar_periodos(bd, usuario.id_usuario):
        escritor.writerow(
            [
                _etiqueta_periodo(periodo),
                str(periodo.sueldo_basico_periodo).replace(".", ","),
                str(periodo.total_horas_extra).replace(".", ","),
                str(periodo.total_recargos).replace(".", ","),
                str(periodo.deduccion_salud).replace(".", ","),
                str(periodo.deduccion_pension).replace(".", ","),
                str(periodo.auxilio_transporte).replace(".", ","),
                str(periodo.deduccion_incapacidad).replace(".", ","),
                str(periodo.total_devengado).replace(".", ","),
                str(periodo.total_deducciones).replace(".", ","),
                str(periodo.saldo_bolsillo).replace(".", ","),
                str(periodo.total_gastos).replace(".", ","),
            ]
        )

    contenido = "\ufeff" + salida.getvalue()
    return Response(
        content=contenido,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="historial_nomina.csv"'},
    )


@router.get(
    "/finanzas/historial/{id_periodo}/imprimir",
    response_class=HTMLResponse,
    name="imprimir_periodo",
)
def imprimir_periodo(
    request: Request,
    id_periodo: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Muestra una liquidación con formato de impresión o PDF.

    Args:
        request: Petición HTTP.
        id_periodo: Periodo a imprimir.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML imprimible.

    Raises:
        HTTPException: 404 si el periodo no existe o es de otro usuario.
    """
    from fastapi import HTTPException

    periodo = bd.get(PeriodoNomina, id_periodo)
    if periodo is None or periodo.id_usuario != usuario.id_usuario:
        raise HTTPException(status_code=404, detail="Periodo no encontrado.")

    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": f"Liquidación {_etiqueta_periodo(periodo)}",
            "periodo": periodo,
            "etiqueta": _etiqueta_periodo(periodo),
        }
    )
    return plantillas.TemplateResponse(request, "historial/imprimir.html", contexto)


@router.post(
    "/finanzas/historial/{id_periodo}/eliminar", name="eliminar_periodo"
)
def eliminar_periodo(
    id_periodo: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina una liquidación del historial y libera sus saldos.

    Args:
        id_periodo: Periodo a eliminar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al historial.
    """
    if periodos.eliminar_periodo(bd, usuario.id_usuario, id_periodo):
        auditoria.registrar(
            bd, usuario.id_usuario, "PERIODO_ELIMINADO", "periodos_nomina", id_periodo
        )
    return RedirectResponse(url="/finanzas/historial", status_code=status.HTTP_303_SEE_OTHER)
