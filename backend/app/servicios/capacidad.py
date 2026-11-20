"""Capacidad de endeudamiento y proyección a doce meses (SRS v1.7, bloque F).

Responsabilidad
---------------
- Repartir el ingreso del mes entre gastos fijos, cuota de deudas y dinero libre,
  para dibujar una dona con semáforo de endeudamiento.
- Listar las deudas que están a punto de terminar (tres cuotas o menos).
- Proyectar doce meses de cuota y saldo libre, teniendo en cuenta que cada deuda
  deja de pesarlo cuando se termina.

Reglas:
- El ingreso base son los pagos del mes (`quincenas.resumen_quincenas`) más el
  neto cobrado de trabajos extras, igual que el diagnóstico de presupuesto.
- Los gastos fijos incluyen gastos, deducciones de ley y deducciones fijas del
  salario; las cuotas de deuda se muestran aparte para que se vea su peso.
- El semáforo mira el porcentaje de la cuota de deuda sobre el ingreso: hasta
  20 % verde, hasta 35 % ámbar y por encima rojo.
- La proyección supone el mismo ingreso y los mismos gastos fijos: solo cambia la
  cuota de deuda al terminar cada obligación. Es una estimación, no un cierre.

Este módulo no escribe en la base de datos: solo lee y calcula.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.modelos import Deuda, PerfilFinanciero
from app.servicios import deducciones_fijas as servicio_deducciones
from app.servicios import deudas as servicio_deudas
from app.servicios import quincenas as servicio_quincenas
from app.servicios import trabajos as servicio_trabajos

CERO = Decimal("0")
CIEN = Decimal("100")
MESES_PROYECCION = 12
CUOTAS_POR_TERMINAR = 3
# SRS v1.8: reserva mensual de supervivencia. El dinero libre que no supere este
# monto no se ofrece para abonos ni metas; solo el remanente se considera
# capacidad real de abono.
BASE_MINIMA_LIQUIDEZ = Decimal("300000")
# Una deducción fija cuya descripción diga «crédito» o «créditos» (por ejemplo,
# una libranza) se trata como deuda y no como gasto fijo.
PATRON_CREDITO = re.compile(r"\bcreditos?\b")

# Umbrales del semáforo, en porcentaje del ingreso mensual.
UMBRAL_VERDE = Decimal("20")
UMBRAL_AMBAR = Decimal("35")

ESTADO_VERDE = "verde"
ESTADO_AMBAR = "ambar"
ESTADO_ROJO = "rojo"
ESTADO_SIN_DATOS = "sin-datos"

MESES_CORTOS = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


@dataclass(frozen=True)
class Capacidad:
    """Reparto del ingreso del mes y su proyección a doce meses.

    Attributes:
        ingreso: Ingreso mensual consolidado (sueldo del mes + extras cobrados).
        gastos: Gastos fijos, deducciones de ley y deducciones fijas del salario.
        deudas: Cuota mensual equivalente de las deudas activas.
        libre: Dinero que queda después de gastos y deudas; puede ser negativo.
        porcentaje_gastos: Peso de los gastos fijos sobre el ingreso.
        porcentaje_deudas: Peso real de las deudas sobre el ingreso (semáforo).
        porcentaje_libre: Porcentaje que queda libre sobre el ingreso.
        semaforo: `verde`, `ambar`, `rojo` o `sin-datos`.
        mensaje: Explicación del semáforo en lenguaje natural.
        arcos: Segmentos de la dona, normalizados para que sumen 100.
        por_terminar: Deudas con tres cuotas o menos por pagar.
        proyeccion: Doce meses de cuota y saldo libre estimados.
        base_minima: Parte del libre reservada como base mínima de liquidez.
        disponible_abono: Remanente del libre que sí puede abonarse o ahorrarse.
    """

    ingreso: Decimal
    gastos: Decimal
    deudas: Decimal
    libre: Decimal
    porcentaje_gastos: Decimal
    porcentaje_deudas: Decimal
    porcentaje_libre: Decimal
    semaforo: str
    mensaje: str
    arcos: list[dict[str, object]] = field(default_factory=list)
    por_terminar: list[dict[str, object]] = field(default_factory=list)
    proyeccion: list[dict[str, object]] = field(default_factory=list)
    libre_salario: Decimal = CERO
    libre_extras: Decimal = CERO
    base_minima: Decimal = CERO
    disponible_abono: Decimal = CERO


def repartir_libre(libre: Decimal) -> tuple[Decimal, Decimal]:
    """Separa el dinero libre entre la base mínima y el disponible para abonar.

    SRS v1.8: la base mínima de liquidez ($300.000) se reserva completa en cuanto
    el libre la alcance; si el libre es menor, todo él queda como base y no hay
    disponible. Un libre negativo no reserva nada.

    Args:
        libre: Dinero que queda después de gastos y cuotas (puede ser negativo).

    Returns:
        Tupla `(base_minima, disponible_abono)` con ambos montos redondeados.
    """
    positivo = max(redondear_dinero(libre), CERO)
    base = min(positivo, BASE_MINIMA_LIQUIDEZ)
    disponible = max(redondear_dinero(positivo - BASE_MINIMA_LIQUIDEZ), CERO)
    return redondear_dinero(base), redondear_dinero(disponible)


def es_credito(descripcion: str) -> bool:
    """Indica si una deducción fija es un crédito (por ejemplo, una libranza).

    Ignora tildes y mayúsculas: «Crédito», «CREDITOS» y «credito» cuentan.

    Args:
        descripcion: Texto que escribió la usuaria.

    Returns:
        `True` si la descripción contiene la palabra crédito o créditos.
    """
    normal = unicodedata.normalize("NFKD", descripcion or "").encode("ascii", "ignore").decode("ascii").lower()
    return bool(PATRON_CREDITO.search(normal))


def _porcentaje(valor: Decimal, total: Decimal) -> Decimal:
    """Calcula el porcentaje de un valor sobre un total, sin superar cero.

    Args:
        valor: Monto a expresar.
        total: Base de comparación.

    Returns:
        Porcentaje redondeado a un decimal; cero si el total no es positivo.
    """
    if total <= CERO:
        return CERO
    return redondear_dinero(max(valor, CERO) / total * CIEN)


def _repartir_arcos(
    gastos: Decimal,
    deudas: Decimal,
    libre: Decimal,
    ingreso: Decimal,
) -> list[dict[str, object]]:
    """Construye los arcos de la dona de capacidad.

    Cuando gastos y deudas superan el ingreso, el dibujo se escala de forma
    proporcional para que la circunferencia cierre y el segmento libre quede en
    cero; así el gráfico no muestra arcos mayores que la vuelta completa.

    SRS v1.8: el dinero libre se parte en «Base mínima de liquidez» (hasta
    $300.000) y «Disponible para abonar» (el remanente). Si el libre no alcanza
    la base, solo se dibuja el arco de la base.

    Args:
        gastos: Gastos fijos del mes.
        deudas: Cuota mensual de deudas.
        libre: Dinero restante (puede ser negativo).
        ingreso: Ingreso mensual consolidado.

    Returns:
        Lista de diccionarios con etiqueta, valor, porcentaje, longitud,
        desplazamiento, color para el SVG y `clase` de color de la cifra
        (verde para el dinero a favor, rojo para gastos y deudas).
    """
    if ingreso <= CERO:
        return []

    base, disponible = repartir_libre(libre)
    gastos_positivos = max(gastos, CERO)
    deudas_positivas = max(deudas, CERO)

    # La decisión de escalar se toma con dinero, no con porcentajes redondeados:
    # dos decimales pueden sumar 100,01 y dibujar un arco libre inexistente.
    if gastos_positivos + deudas_positivas + base + disponible > ingreso:
        # El ingreso no alcanza: se reparte la vuelta completa entre gastos y
        # deudas sin dibujar un segmento libre que no existe.
        comprometido = gastos_positivos + deudas_positivas
        if comprometido > CERO:
            porcentaje_gastos = gastos_positivos / comprometido * CIEN
            porcentaje_deudas = CIEN - porcentaje_gastos
        else:
            porcentaje_gastos = CERO
            porcentaje_deudas = CERO
        porcentaje_base = CERO
        porcentaje_disponible = CERO
    else:
        porcentaje_gastos = _porcentaje(gastos_positivos, ingreso)
        porcentaje_deudas = _porcentaje(deudas_positivas, ingreso)
        porcentaje_base = _porcentaje(base, ingreso)
        porcentaje_disponible = _porcentaje(disponible, ingreso)

    # `clase` pinta la cifra de la leyenda con la paleta de referencia: rojo para
    # lo que sale del bolsillo (gastos y deudas) y verde para lo que queda a favor
    # (base mínima y disponible). El color del arco se conserva como guía visual.
    candidatos = [
        ("Gastos fijos", gastos_positivos, porcentaje_gastos, "var(--accent-blue)", "valor-negativo"),
        ("Cuota de deudas", deudas_positivas, porcentaje_deudas, "var(--accent-red)", "valor-negativo"),
        ("Base mínima de liquidez", base, porcentaje_base, "var(--accent-green)", "valor-positivo"),
        ("Disponible para abonar", disponible, porcentaje_disponible, "var(--accent-amber)", "valor-positivo"),
    ]

    # Los porcentajes se muestran con un decimal; el redondeo de cada uno puede
    # dejar la suma en 99,9 o 100,1. El ajuste va al arco mayor para que la dona
    # cierre exactamente en 100 % sin mover los montos.
    visibles = [fila for fila in candidatos if fila[2] > CERO]
    if visibles:
        redondeados = [fila[2].quantize(Decimal("0.1")) for fila in visibles]
        diferencia = CIEN - sum(redondeados, start=CERO)
        mayor = max(range(len(visibles)), key=lambda indice: visibles[indice][2])
        redondeados[mayor] += diferencia
    else:
        redondeados = []

    arcos: list[dict[str, object]] = []
    avance = CERO
    for (etiqueta, valor, _pct, color, clase), porcentaje in zip(visibles, redondeados):
        longitud = redondear_dinero(porcentaje)
        arcos.append(
            {
                "etiqueta": etiqueta,
                "valor": redondear_dinero(valor),
                "porcentaje": porcentaje,
                "longitud": longitud,
                "desplazamiento": redondear_dinero(-avance),
                "color": color,
                "clase": clase,
            }
        )
        avance += porcentaje
    return arcos


def _meses_equivalentes(deuda: Deuda) -> int:
    """Traduce las cuotas pendientes a meses de pago.

    Una deuda quincenal paga dos cuotas por mes; la última fracción cuenta como
    un mes completo porque la cuota todavía pesa en el presupuesto.

    Args:
        deuda: Deuda activa.

    Returns:
        Número de meses en los que la deuda seguirá descontándose.
    """
    cuotas = max(deuda.cuotas_pendientes, 0)
    if cuotas <= 0:
        return 0
    if deuda.periodicidad == servicio_deudas.PERIODICIDAD_QUINCENAL:
        return int(math.ceil(cuotas / 2))
    return cuotas


def _etiqueta_mes(anio: int, mes: int) -> str:
    """Devuelve el rótulo corto de un mes.

    Args:
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Texto tipo «ene 2027».
    """
    return f"{MESES_CORTOS[mes - 1]} {anio}"


def _mover_mes(anio: int, mes: int, avance: int) -> tuple[int, int]:
    """Desplaza un mes un número de posiciones.

    Args:
        anio: Año de partida.
        mes: Mes de partida (1–12).
        avance: Meses a sumar.

    Returns:
        Tupla `(anio, mes)` resultante.
    """
    total = (anio * 12) + (mes - 1) + avance
    return total // 12, (total % 12) + 1


def meses_siguientes(
    anio: int, mes: int, cantidad: int = MESES_PROYECCION
) -> list[tuple[int, int, str]]:
    """Lista los próximos meses con su rótulo corto.

    Args:
        anio: Año de partida.
        mes: Mes de partida (1–12).
        cantidad: Número de meses a devolver.

    Returns:
        Lista de tuplas `(anio, mes, etiqueta)` desde el mes de partida.
    """
    return [
        (a, m, _etiqueta_mes(a, m))
        for a, m in (_mover_mes(anio, mes, avance) for avance in range(cantidad))
    ]


def deudas_por_terminar(
    bd: Session,
    id_usuario: str,
    maximo: int = CUOTAS_POR_TERMINAR,
) -> list[dict[str, object]]:
    """Lista las deudas activas con pocas cuotas pendientes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.
        maximo: Número máximo de cuotas para considerar que está por terminar.

    Returns:
        Lista de diccionarios ordenada por cuotas restantes y fecha estimada de
        la última cuota. Las deudas ya pagadas no aparecen.
    """
    pagos_por_deuda = servicio_deudas.listar_pagos(bd, id_usuario)
    filas: list[dict[str, object]] = []
    for deuda in servicio_deudas.listar_deudas(bd, id_usuario):
        if deuda.estado != servicio_deudas.ESTADO_ACTIVA:
            continue
        if deuda.cuotas_pendientes <= 0 or deuda.cuotas_pendientes > maximo:
            continue
        pagos = pagos_por_deuda.get(deuda.id_deuda, [])
        desde = pagos[-1].fecha_aplicacion if pagos else None
        cuotas = servicio_deudas.proyeccion_deuda(deuda, desde)
        fecha_fin = cuotas[-1].fecha if cuotas else None
        filas.append(
            {
                "acreedor": deuda.acreedor,
                "descripcion": deuda.descripcion or "",
                "saldo": redondear_dinero(deuda.saldo_total),
                "cuota": servicio_deudas.cuota_mensual_equivalente(deuda),
                "cuotas_pendientes": deuda.cuotas_pendientes,
                "periodicidad": deuda.periodicidad,
                "fecha_fin": fecha_fin,
            }
        )
    filas.sort(
        key=lambda fila: (
            fila["cuotas_pendientes"],
            fila["fecha_fin"] or date.max,
        )
    )
    return filas


def proyeccion_capacidad(
    ingreso: Decimal,
    gastos: Decimal,
    deudas: list[Deuda],
    hoy: date | None = None,
    creditos: Decimal = CERO,
) -> list[dict[str, object]]:
    """Estima doce meses de cuota de deuda y saldo libre.

    Args:
        ingreso: Ingreso mensual consolidado que se mantiene constante.
        gastos: Gastos fijos mensuales que se mantienen constantes.
        deudas: Deudas activas del usuario.
        hoy: Mes de partida; por defecto, el mes actual.
        creditos: Deducciones fijas que son créditos; se cobran cada mes de la
            proyección, porque una deducción no tiene fecha de fin.

    Returns:
        Lista de doce diccionarios con etiqueta, cuota, libre, porcentaje de
        deuda y la lista de deudas que terminan ese mes.
    """
    referencia = hoy or date.today()
    activas = [
        (deuda, _meses_equivalentes(deuda), servicio_deudas.cuota_mensual_equivalente(deuda))
        for deuda in deudas
        if deuda.estado == servicio_deudas.ESTADO_ACTIVA and deuda.cuotas_pendientes > 0
    ]

    filas: list[dict[str, object]] = []
    for avance, (_anio, _mes, etiqueta) in enumerate(
        meses_siguientes(referencia.year, referencia.month)
    ):
        cuota = redondear_dinero(
            sum(
                (
                    valor
                    for _deuda, meses, valor in activas
                    if meses > avance
                ),
                start=CERO,
            )
            + creditos
        )
        libre = redondear_dinero(ingreso - gastos - cuota)
        porcentaje_deuda = _porcentaje(cuota, ingreso)
        filas.append(
            {
                "etiqueta": etiqueta,
                "deuda": cuota,
                "libre": libre,
                "porcentaje_deuda": porcentaje_deuda,
                "porcentaje_libre": _porcentaje(libre, ingreso),
                "terminan": [
                    deuda.acreedor
                    for deuda, meses, _valor in activas
                    if meses == avance + 1
                ],
            }
        )
    return filas


def _mensaje_semaforo(estado: str, porcentaje_deudas: Decimal) -> str:
    """Redacta la explicación del semáforo de endeudamiento.

    Args:
        estado: Resultado del semáforo.
        porcentaje_deudas: Peso real de las deudas sobre el ingreso.

    Returns:
        Texto listo para la interfaz.
    """
    if estado == ESTADO_VERDE:
        return (
            f"Tus deudas consumen el {porcentaje_deudas} % del ingreso; hay margen "
            "para asumir una cuota nueva con cuidado."
        )
    if estado == ESTADO_AMBAR:
        return (
            f"Tus deudas consumen el {porcentaje_deudas} % del ingreso; evita "
            "adquirir obligaciones nuevas hasta bajarlas."
        )
    if estado == ESTADO_ROJO:
        return (
            f"Tus deudas consumen el {porcentaje_deudas} % del ingreso; prioriza "
            "pagarlas antes de proyectar gastos nuevos."
        )
    return (
        "Completa tu perfil financiero para calcular cuánto de tu ingreso está "
        "comprometido."
    )


def capacidad_trabajos(
    bd: Session,
    id_usuario: str,
    anio: int,
    mes: int,
) -> Capacidad:
    """Calcula la dona de Trabajos Extras con solo sus datos.

    El ingreso son los valores de pago de trabajos extras del mes, cobrados o no; los gastos son los
    gastos fijos puestos dentro de esos trabajos. No cuentan el sueldo, las quincenas
    de Mis Finanzas ni las deudas.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los trabajos.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Un `Capacidad` con ingreso, gastos fijos, libre y arcos de la dona.
    """
    bloques = servicio_trabajos.pagos_del_mes(bd, id_usuario, anio, mes)
    ingreso = redondear_dinero(sum((bloque["ingreso"] for bloque in bloques), start=CERO))
    gastos = redondear_dinero(sum((bloque["gastos_total"] for bloque in bloques), start=CERO))
    libre = redondear_dinero(ingreso - gastos)
    base, disponible = repartir_libre(libre)
    return Capacidad(
        ingreso=ingreso,
        gastos=gastos,
        deudas=CERO,
        libre=libre,
        porcentaje_gastos=_porcentaje(gastos, ingreso),
        porcentaje_deudas=CERO,
        porcentaje_libre=_porcentaje(libre, ingreso),
        semaforo=ESTADO_VERDE,
        mensaje="",
        arcos=_repartir_arcos(gastos, CERO, libre, ingreso),
        base_minima=base,
        disponible_abono=disponible,
    )


def capacidad_endeudamiento(
    bd: Session,
    id_usuario: str,
    perfil: PerfilFinanciero | None,
    anio: int,
    mes: int,
    hoy: date | None = None,
) -> Capacidad:
    """Calcula la capacidad de endeudamiento del mes y su proyección.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos, deudas y trabajos.
        perfil: Perfil financiero del usuario.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).
        hoy: Fecha de referencia para la proyección; por defecto, hoy.

    Returns:
        Un `Capacidad` con el reparto del ingreso, el semáforo, las deudas por
        terminar y la proyección a doce meses.
    """
    resumen = servicio_quincenas.resumen_quincenas(bd, id_usuario, perfil, anio, mes)
    ingreso_base = redondear_dinero(sum((fila.ingreso for fila in resumen), start=CERO))

    # Trabajos extras: entran por su valor de pago y salen con sus gastos fijos.
    # Su libre se muestra aparte del libre del salario.
    bloques = servicio_trabajos.pagos_del_mes(bd, id_usuario, anio, mes)
    ingreso_extras = redondear_dinero(sum((bloque["ingreso"] for bloque in bloques), start=CERO))
    gastos_extras = redondear_dinero(sum((bloque["gastos_total"] for bloque in bloques), start=CERO))
    libre_extras = redondear_dinero(sum((bloque["disponible"] for bloque in bloques), start=CERO))
    ingreso = redondear_dinero(ingreso_base + ingreso_extras)

    # Las deducciones fijas que son créditos pasan a deuda; el resto es gasto fijo.
    creditos = redondear_dinero(
        sum(
            (fija.valor for fija in servicio_deducciones.listar_deducciones(bd, id_usuario) if es_credito(fija.descripcion)),
            start=CERO,
        )
    )
    deducciones_fijas_total = redondear_dinero(
        sum((fila.deducciones_fijas for fila in resumen), start=CERO)
    )
    gastos = redondear_dinero(
        sum((fila.gastos + fila.deducciones for fila in resumen), start=CERO)
        + (deducciones_fijas_total - creditos)
        + gastos_extras
    )
    deudas = list(servicio_deudas.listar_deudas(bd, id_usuario))
    cuota_deudas = redondear_dinero(
        servicio_deudas.resumen_deudas(bd, id_usuario)["cuota_mensual"] + creditos
    )
    libre = redondear_dinero(ingreso - gastos - cuota_deudas)
    libre_salario = redondear_dinero(libre - libre_extras)
    base, disponible = repartir_libre(libre)

    if ingreso <= CERO:
        estado = ESTADO_SIN_DATOS
        porcentaje_deudas = CERO
    else:
        porcentaje_deudas = redondear_dinero(cuota_deudas / ingreso * CIEN)
        if porcentaje_deudas <= UMBRAL_VERDE:
            estado = ESTADO_VERDE
        elif porcentaje_deudas <= UMBRAL_AMBAR:
            estado = ESTADO_AMBAR
        else:
            estado = ESTADO_ROJO

    return Capacidad(
        ingreso=ingreso,
        gastos=gastos,
        deudas=cuota_deudas,
        libre=libre,
        porcentaje_gastos=_porcentaje(gastos, ingreso),
        porcentaje_deudas=porcentaje_deudas,
        porcentaje_libre=_porcentaje(libre, ingreso),
        semaforo=estado,
        mensaje=_mensaje_semaforo(estado, porcentaje_deudas),
        arcos=_repartir_arcos(gastos, cuota_deudas, libre, ingreso),
        por_terminar=deudas_por_terminar(bd, id_usuario),
        proyeccion=proyeccion_capacidad(ingreso, gastos, deudas, hoy, creditos),
        libre_salario=libre_salario,
        libre_extras=libre_extras,
        base_minima=base,
        disponible_abono=disponible,
    )
