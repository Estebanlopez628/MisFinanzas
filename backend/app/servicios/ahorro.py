"""Planificador de ahorro y metas del usuario (SRS v1.3, bloque 3).

Responsabilidad
---------------
- Crear metas de ahorro o gastos programados con cuota mensual, duración y
  quincena de descuento.
- Calcular el progreso frente al total proyectado. SRS v1.6: el abono de cada
  mes no se digita; lo produce el check de pago del gasto fijo de la meta
  (ver `app.servicios.pagos_metas`).
- Entregar el diagnóstico de liquidez del mes (saldo libre total de las
  quincenas) para el banner de «Gastos y Presupuesto».

La aritmética salarial vive en `app.servicios.nomina` y el saldo por pago en
`app.servicios.quincenas`; aquí solo se suma lo que ya está calculado.

Reglas:
- Toda meta exige un periodo (`meses`, de 1 a 600) escogido por el usuario.
  Una meta `LIMITADO` y una `FIJO` calculan total = cuota × meses (SRS v1.6).
- Las metas creadas antes de SRS v1.6 sin periodo usan la ventana de 12 meses.
- Hay un único abono por meta y mes; es la suma de sus pagos marcados.
- El umbral de alerta de liquidez es de $300.000 COP mensuales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import AbonoProyeccion, Gasto, PerfilFinanciero, ProyeccionAhorro
from app.servicios import capacidad as servicio_capacidad
from app.servicios import deducciones_fijas as servicio_fijas
from app.servicios import deudas as servicio_deudas
from app.servicios import quincenas as servicio_quincenas
from app.servicios import trabajos as servicio_trabajos
from app.servicios.gastos import valor_computable

CERO = Decimal("0")

DURACION_FIJA = "FIJO"
DURACION_LIMITADA = "LIMITADO"
# SRS v1.6: tanto la meta indefinida como la limitada tienen un periodo que el
# usuario escoge en meses o años (hasta 50 años).
MESES_MAXIMOS = 600
# SRS v1.5: tercera opción del selector. La cuota mensual se reparte entre los
# dos pagos en lugar de imputarse a uno solo.
QUINCENA_AMBAS = 3
QUINCENAS_VALIDAS = (1, 2, QUINCENA_AMBAS)
# SRS v1.7: comportamiento del monto cuando la meta se descuenta en las dos
# quincenas. `DIVIDIR` reparte la cuota (100.000 → 50.000 + 50.000) y
# `DUPLICAR` cobra la cuota completa en cada pago (100.000 + 100.000).
MODO_DIVIDIR = "DIVIDIR"
MODO_DUPLICAR = "DUPLICAR"
MODOS_AMBAS = (MODO_DIVIDIR, MODO_DUPLICAR)
# Ventana de comparación para los gastos fijos indefinidos, que no tienen final.
MESES_VENTANA_FIJA = 12
# SRS v1.8 y §5: la alerta de liquidez comparte la base mínima del consejero.
# La constante es 0 cuando el usuario no digitó un monto; el umbral real se lee
# del perfil en `diagnostico()`.
UMBRAL_ALERTA = servicio_capacidad.BASE_MINIMA_LIQUIDEZ
# SRS v1.6: estado con el que queda archivada una meta en el historial.
ESTADO_CUMPLIDA = "CUMPLIDA"
ESTADO_ELIMINADA = "ELIMINADA"

CATEGORIAS_SUGERIDAS = (
    "Ahorro",
    "Abono a deudas",
    "Seguro del vehículo",
    "Impuestos del vehículo",
    "Predial",
    "Vacaciones",
)

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
class MesMeta:
    """Un mes de la línea de tiempo de una meta.

    Attributes:
        anio: Año del mes.
        mes: Mes (1–12).
        etiqueta: Texto corto («ene 2027»).
        planeado: Cuota prevista para ese mes.
        abono: Monto pagado (suma de los checks), o `None` si no hay pagos.
        estado: `registrado`, `no_pagado` o `pendiente` (SRS v1.6).
    """

    anio: int
    mes: int
    etiqueta: str
    planeado: Decimal
    abono: Decimal | None = None
    estado: str = "pendiente"

    @property
    def registrado(self) -> bool:
        """Indica si el mes ya tiene un abono registrado.

        Returns:
            `True` cuando existe un abono para el mes.
        """
        return self.abono is not None


@dataclass(frozen=True)
class MetaResumen:
    """Meta con su progreso y su línea de tiempo.

    Attributes:
        proyeccion: Registro persistido.
        total_proyectado: Total cerrado de la meta o `None` si es indefinida.
        acumulado: Suma de los abonos registrados.
        porcentaje: Avance sobre el total proyectado (0–100).
        meses: Meses planificados con su estado de abono.
    """

    proyeccion: ProyeccionAhorro
    total_proyectado: Decimal | None
    acumulado: Decimal
    porcentaje: Decimal
    meses: list[MesMeta] = field(default_factory=list)
    cumplida: bool = False
    fin_etiqueta: str = ""

    @property
    def etiqueta_quincena(self) -> str:
        """Rótulo de la quincena de descuento («Quincena 1» o «Ambas quincenas»).

        Returns:
            Texto listo para la plantilla.
        """
        return etiqueta_quincena(self.proyeccion.quincena)

    @property
    def valor_por_pago(self) -> Decimal:
        """Monto que la meta asigna a cada pago.

        SRS v1.7: con «Ambas quincenas» respeta el modo escogido: la mitad de la
        cuota (`DIVIDIR`) o la cuota completa en cada pago (`DUPLICAR`).

        Returns:
            Cuota por pago, redondeada a centavos.
        """
        return valor_por_pago(
            self.proyeccion.valor_mensual,
            self.proyeccion.quincena,
            self.proyeccion.modo_ambas,
        )


def etiqueta_quincena(quincena: int) -> str:
    """Devuelve el rótulo visible de la quincena de descuento de una meta.

    Args:
        quincena: `1`, `2` o `3` (ambas).

    Returns:
        Texto listo para la interfaz: «Quincena 1», «Quincena 2» o
        «Ambas quincenas».
    """
    if quincena == QUINCENA_AMBAS:
        return "Ambas quincenas"
    return f"Quincena {quincena}"


def valor_por_pago(
    valor_mensual: Decimal | int | str,
    quincena: int,
    modo_ambas: str = MODO_DIVIDIR,
) -> Decimal:
    """Calcula cuánto aporta la cuota ingresada a cada pago.

    SRS v1.7: con «Ambas quincenas» el usuario elige entre repartir la cuota
    (`DIVIDIR`) o cobrarla completa en cada pago (`DUPLICAR`); con quincena 1 o
    2, el pago elegido asume la cuota completa.

    Args:
        valor_mensual: Cuota escrita por el usuario.
        quincena: `1`, `2` o `3` (ambas).
        modo_ambas: `DIVIDIR` o `DUPLICAR`; solo aplica a la quincena 3.

    Returns:
        Monto que corresponde a cada pago, redondeado a centavos.
    """
    monto = redondear_dinero(parsear_monto(str(valor_mensual)))
    if quincena == QUINCENA_AMBAS:
        if _normalizar_modo_ambas(modo_ambas) == MODO_DUPLICAR:
            return monto
        return redondear_dinero(monto / Decimal("2"))
    return monto


def _normalizar_modo_ambas(modo_ambas: str | None) -> str:
    """Normaliza y valida el modo de reparto de «Ambas quincenas».

    Args:
        modo_ambas: Texto recibido del formulario o de la base de datos.

    Returns:
        `DIVIDIR` o `DUPLICAR`.

    Raises:
        ValueError: Si el modo no es uno de los dos admitidos.
    """
    modo = (modo_ambas or MODO_DIVIDIR).strip().upper()
    if modo not in MODOS_AMBAS:
        raise ValueError("El modo de ambas quincenas debe ser DIVIDIR o DUPLICAR.")
    return modo


def valor_mensual_efectivo(proyeccion: ProyeccionAhorro) -> Decimal:
    """Calcula el total que la meta descuenta en el mes.

    Es la suma real de sus pagos: la cuota completa en quincena 1 o 2; la cuota
    repartida o duplicada cuando se descuenta en ambas (SRS v1.7).

    Args:
        proyeccion: Meta persistida.

    Returns:
        Total mensual efectivo, redondeado a centavos.
    """
    return redondear_dinero(
        valor_por_pago(
            proyeccion.valor_mensual,
            proyeccion.quincena,
            proyeccion.modo_ambas,
        )
        * (Decimal("2") if proyeccion.quincena == QUINCENA_AMBAS else Decimal("1"))
    )


def _mover_mes(anio: int, mes: int, avance: int) -> tuple[int, int]:
    """Desplaza un mes un número de posiciones.

    Args:
        anio: Año de partida.
        mes: Mes de partida (1–12).
        avance: Meses a sumar; puede ser negativo.

    Returns:
        Tupla `(anio, mes)` resultante.
    """
    total = (anio * 12) + (mes - 1) + avance
    return total // 12, (total % 12) + 1


def _etiqueta_mes(anio: int, mes: int) -> str:
    """Devuelve el rótulo corto de un mes.

    Args:
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Texto tipo «ene 2027».
    """
    return f"{MESES_CORTOS[mes - 1]} {anio}"


def _validar_duracion(tipo_duracion: str, meses: int | str | None) -> tuple[str, int | None]:
    """Normaliza el tipo de duración y la cantidad de cuotas.

    Args:
        tipo_duracion: `FIJO` o `LIMITADO`.
        meses: Cantidad de cuotas informada por el usuario.

    Returns:
        Tupla `(tipo, meses)` con `meses` en `None` para los gastos fijos.

    Raises:
        ValueError: Si el tipo no es válido o la duración está fuera de rango.
    """
    tipo = (tipo_duracion or DURACION_FIJA).strip().upper()
    if tipo not in (DURACION_FIJA, DURACION_LIMITADA):
        raise ValueError("El tipo de duración debe ser FIJO o LIMITADO.")
    try:
        cantidad = int(meses) if meses not in (None, "") else 0
    except (TypeError, ValueError) as error:
        raise ValueError("El tiempo de pago debe ser un número de meses.") from error
    if cantidad < 1 or cantidad > MESES_MAXIMOS:
        raise ValueError(
            f"El tiempo de pago debe estar entre 1 y {MESES_MAXIMOS} meses."
        )
    return tipo, cantidad


def crear_proyeccion(
    bd: Session,
    id_usuario: str,
    categoria: str,
    descripcion: str,
    valor_mensual: Decimal | str | int | float,
    tipo_duracion: str = DURACION_FIJA,
    meses: int | str | None = None,
    fecha_inicio: date | None = None,
    quincena: int | str = 1,
    modo_ambas: str = MODO_DIVIDIR,
) -> ProyeccionAhorro:
    """Registra una meta de ahorro o un gasto programado.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta.
        categoria: Categoría sugerida o texto libre.
        descripcion: Detalle del objetivo.
        valor_mensual: Cuota escrita por el usuario; no puede ser negativa.
        tipo_duracion: `FIJO` (indefinido) o `LIMITADO`.
        meses: Cantidad de cuotas cuando la duración es limitada.
        fecha_inicio: Primer mes de la proyección; por defecto el mes en curso.
        quincena: `1`, `2` o `3` (ambas quincenas).
        modo_ambas: `DIVIDIR` o `DUPLICAR`; solo aplica a la quincena 3.

    Returns:
        La meta persistida.

    Raises:
        ValueError: Si falta la categoría o la descripción, el monto es negativo
            o inválido, la duración no es coherente, la quincena no es 1, 2 o 3,
            o el modo de ambas quincenas no es válido.
    """
    categoria_limpia = categoria.strip()
    descripcion_limpia = descripcion.strip()
    if not categoria_limpia:
        raise ValueError("La categoría de la meta es obligatoria.")
    if not descripcion_limpia:
        raise ValueError("La descripción de la meta es obligatoria.")

    monto = redondear_dinero(parsear_monto(str(valor_mensual)))
    if monto < CERO:
        raise ValueError("La cuota mensual no puede ser negativa.")

    tipo, cantidad = _validar_duracion(tipo_duracion, meses)

    try:
        numero_quincena = int(quincena)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "La quincena de descuento debe ser 1, 2 o 3 (ambas quincenas)."
        ) from error
    if numero_quincena not in QUINCENAS_VALIDAS:
        raise ValueError(
            "La quincena de descuento debe ser 1, 2 o 3 (ambas quincenas)."
        )

    # El modo solo tiene sentido con «Ambas quincenas»; en un pago único se
    # guarda DIVIDIR para que la columna nunca quede ambigua.
    modo = (
        _normalizar_modo_ambas(modo_ambas)
        if numero_quincena == QUINCENA_AMBAS
        else MODO_DIVIDIR
    )

    inicio = fecha_inicio or date.today()

    proyeccion = ProyeccionAhorro(
        id_usuario=id_usuario,
        categoria=categoria_limpia[:60],
        descripcion=descripcion_limpia[:150],
        valor_mensual=monto,
        tipo_duracion=tipo,
        meses=cantidad,
        fecha_inicio=inicio,
        quincena=numero_quincena,
        modo_ambas=modo,
        activo=True,
    )
    bd.add(proyeccion)
    bd.commit()
    bd.refresh(proyeccion)
    return proyeccion


def listar_proyecciones(bd: Session, id_usuario: str) -> list[ProyeccionAhorro]:
    """Lista las metas activas del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las metas.

    Returns:
        Lista ordenada por fecha de inicio y descripción.
    """
    consulta = (
        select(ProyeccionAhorro)
        .where(
            ProyeccionAhorro.id_usuario == id_usuario,
            ProyeccionAhorro.activo.is_(True),
        )
        .order_by(ProyeccionAhorro.fecha_inicio, ProyeccionAhorro.descripcion)
    )
    return list(bd.scalars(consulta))


def _posicion(anio: int, mes: int) -> int:
    """Convierte un mes en un número consecutivo para compararlos.

    Args:
        anio: Año.
        mes: Mes (1–12).

    Returns:
        Índice mensual que crece de uno en uno.
    """
    return anio * 12 + (mes - 1)


def eliminar_proyeccion(
    bd: Session,
    id_usuario: str,
    id_proyeccion: str,
    hoy: date | None = None,
) -> bool:
    """Archiva una meta: conserva su historial y retira sus cuotas futuras.

    SRS v1.6: la meta sale de la lista activa, pero queda en la base de datos
    con su inicio, su fin, el total recogido y si se cumplió o se eliminó antes.
    Se quitan los gastos de meses futuros que no están pagados; los pagos ya
    registrados se conservan como historial.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta (evita tocar datos ajenos).
        id_proyeccion: Identificador de la meta.
        hoy: Fecha de referencia; por defecto, hoy.

    Returns:
        `True` si se archivó; `False` si no existe o es de otro usuario.
    """
    proyeccion = bd.get(ProyeccionAhorro, id_proyeccion)
    if proyeccion is None or proyeccion.id_usuario != id_usuario:
        return False

    referencia = hoy or date.today()
    anio_fin, mes_fin = meses_de_la_meta(proyeccion)[-1]
    cumplida = _posicion(referencia.year, referencia.month) > _posicion(anio_fin, mes_fin)
    inicio_del_mes = date(referencia.year, referencia.month, 1)
    futuros = bd.scalars(
        select(Gasto).where(
            Gasto.id_proyeccion == id_proyeccion,
            Gasto.pagado.is_(False),
            Gasto.fecha >= inicio_del_mes,
        )
    )
    for gasto in list(futuros):
        bd.delete(gasto)

    proyeccion.activo = False
    proyeccion.archivada_en = referencia
    proyeccion.estado_final = ESTADO_CUMPLIDA if cumplida else ESTADO_ELIMINADA
    bd.commit()
    return True


def extender_proyeccion(
    bd: Session,
    id_usuario: str,
    id_proyeccion: str,
    cantidad: int,
    hoy: date | None = None,
) -> ProyeccionAhorro | None:
    """Agrega meses a una meta activa, a partir de su fin o del mes actual.

    Si la meta ya se cumplió, la extensión cuenta desde el mes en curso. Si aún
    está en curso, cuenta desde el último mes planificado.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta.
        id_proyeccion: Meta a extender.
        cantidad: Meses que se agregan (mayor que cero).
        hoy: Fecha de referencia; por defecto, hoy.

    Returns:
        La meta actualizada, o `None` si no existe o es de otro usuario.

    Raises:
        ValueError: Si la cantidad no es positiva, la meta está archivada o el
            total supera el máximo permitido.
    """
    proyeccion = bd.get(ProyeccionAhorro, id_proyeccion)
    if proyeccion is None or proyeccion.id_usuario != id_usuario:
        return None
    if not proyeccion.activo:
        raise ValueError("Una meta eliminada no se puede extender.")
    if cantidad < 1:
        raise ValueError("La extensión debe ser de al menos un mes.")

    referencia = hoy or date.today()
    anio_fin, mes_fin = meses_de_la_meta(proyeccion)[-1]
    base = max(
        _posicion(anio_fin, mes_fin),
        _posicion(referencia.year, referencia.month) - 1,
    )
    total = base + cantidad - _posicion(
        proyeccion.fecha_inicio.year, proyeccion.fecha_inicio.month
    ) + 1
    if total > MESES_MAXIMOS:
        raise ValueError(
            f"La meta no puede superar {MESES_MAXIMOS} meses (50 años) en total."
        )

    proyeccion.meses = total
    bd.commit()
    bd.refresh(proyeccion)
    return proyeccion


def historial_metas(bd: Session, id_usuario: str) -> list[dict[str, object]]:
    """Lista las metas archivadas con su inicio, fin y total recogido.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las metas.

    Returns:
        Lista de diccionarios, de la más reciente a la más antigua.
    """
    consulta = (
        select(ProyeccionAhorro)
        .where(
            ProyeccionAhorro.id_usuario == id_usuario,
            ProyeccionAhorro.activo.is_(False),
        )
        .order_by(ProyeccionAhorro.archivada_en.desc())
    )
    filas: list[dict[str, object]] = []
    for proyeccion in bd.scalars(consulta):
        recogido = redondear_dinero(
            sum(
                (
                    abono
                    for abono in bd.scalars(
                        select(AbonoProyeccion.valor).where(
                            AbonoProyeccion.id_proyeccion == proyeccion.id_proyeccion
                        )
                    )
                ),
                start=CERO,
            )
        )
        anio_fin, mes_fin = meses_de_la_meta(proyeccion)[-1]
        filas.append(
            {
                "descripcion": proyeccion.descripcion,
                "categoria": proyeccion.categoria,
                "inicio": _etiqueta_mes(
                    proyeccion.fecha_inicio.year, proyeccion.fecha_inicio.month
                ),
                "fin": _etiqueta_mes(anio_fin, mes_fin),
                "estado": proyeccion.estado_final or ESTADO_ELIMINADA,
                "total_recogido": recogido,
                "archivada_en": proyeccion.archivada_en,
                "pagos": _detalle_pagos(bd, proyeccion),
            }
        )
    return filas


def _detalle_pagos(bd: Session, proyeccion: ProyeccionAhorro) -> list[dict[str, object]]:
    """Lista mes por mes lo pagado de una meta archivada.

    Un mes con abono muestra su monto y la fecha de pago. Un mes sin abono que
    ocurrió antes del archivado figura como «No pagado»; los meses posteriores al
    archivado no se muestran como pendientes, porque la meta ya no los reclama.

    Args:
        bd: Sesión de base de datos.
        proyeccion: Meta archivada.

    Returns:
        Lista de diccionarios con `etiqueta`, `estado`, `valor` y `fecha`.
    """
    abonos = {
        (abono.anio, abono.mes): abono.valor
        for abono in bd.scalars(
            select(AbonoProyeccion).where(
                AbonoProyeccion.id_proyeccion == proyeccion.id_proyeccion
            )
        )
    }
    fechas: dict[tuple[int, int], date] = {}
    for gasto in bd.scalars(
        select(Gasto).where(
            Gasto.id_proyeccion == proyeccion.id_proyeccion,
            Gasto.pagado.is_(True),
        )
    ):
        clave = (gasto.fecha.year, gasto.fecha.month)
        if gasto.pagado_en and (clave not in fechas or gasto.pagado_en > fechas[clave]):
            fechas[clave] = gasto.pagado_en

    corte = None
    if proyeccion.archivada_en is not None:
        corte = _posicion(proyeccion.archivada_en.year, proyeccion.archivada_en.month)

    detalle: list[dict[str, object]] = []
    for anio, mes in meses_de_la_meta(proyeccion):
        clave = (anio, mes)
        posicion = _posicion(anio, mes)
        if clave in abonos:
            estado, valor = "Pagado", redondear_dinero(abonos[clave])
        elif corte is None or posicion <= corte:
            estado, valor = "No pagado", None
        else:
            continue
        detalle.append(
            {
                "etiqueta": _etiqueta_mes(anio, mes),
                "estado": estado,
                "valor": valor,
                "fecha": fechas.get(clave),
            }
        )
    return detalle


def meses_de_la_meta(proyeccion: ProyeccionAhorro) -> list[tuple[int, int]]:
    """Calcula la línea de tiempo de una meta.

    Args:
        proyeccion: Meta persistida.

    Returns:
        Lista de tuplas `(anio, mes)` desde el inicio hasta el final planificado.
    """
    cantidad = proyeccion.meses or MESES_VENTANA_FIJA
    inicio = proyeccion.fecha_inicio
    return [
        _mover_mes(inicio.year, inicio.month, avance) for avance in range(cantidad)
    ]


def _estado_mes(
    id_proyeccion: str,
    anio: int,
    mes: int,
    por_mes: dict[tuple[str, int, int], Decimal],
    saltados: set[tuple[str, int, int]],
    hoy: date,
) -> str:
    """Clasifica un mes de la meta para su tarjeta en «Gastos y Presupuesto».

    Args:
        id_proyeccion: Meta evaluada.
        anio: Año del mes.
        mes: Mes (1–12).
        por_mes: Pagos registrados por meta y mes.
        saltados: Meses con algún gasto inhabilitado (× desde la meta).
        hoy: Fecha de referencia para distinguir meses vencidos.

    Returns:
        `registrado` si hay pagos, `no_pagado` si el mes se saltó o venció sin
        pagos, y `pendiente` en cualquier otro caso.
    """
    clave = (id_proyeccion, anio, mes)
    if clave in por_mes:
        return "registrado"
    if clave in saltados or (anio, mes) < (hoy.year, hoy.month):
        return "no_pagado"
    return "pendiente"


def resumen_metas(bd: Session, id_usuario: str) -> list[MetaResumen]:
    """Construye el progreso y la línea de tiempo de cada meta.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las metas.

    Returns:
        Lista de resúmenes listos para la plantilla.
    """
    proyecciones = listar_proyecciones(bd, id_usuario)
    if not proyecciones:
        return []

    ids = [proyeccion.id_proyeccion for proyeccion in proyecciones]
    abonos = list(
        bd.scalars(
            select(AbonoProyeccion).where(AbonoProyeccion.id_proyeccion.in_(ids))
        )
    )
    por_mes = {(abono.id_proyeccion, abono.anio, abono.mes): abono.valor for abono in abonos}
    # SRS v1.6: un mes es «no pagado» si su gasto fue saltado con × o si ya pasó
    # sin ningún pago registrado; el mes actual sin pagos sigue «pendiente».
    hoy = date.today()
    saltados = {
        (gasto.id_proyeccion, gasto.fecha.year, gasto.fecha.month)
        for gasto in bd.scalars(
            select(Gasto).where(
                Gasto.id_proyeccion.in_(ids),
                Gasto.inhabilitado_hasta > hoy,
            )
        )
    }

    resumenes: list[MetaResumen] = []
    for proyeccion in proyecciones:
        meses = [
            MesMeta(
                anio=anio,
                mes=mes,
                etiqueta=_etiqueta_mes(anio, mes),
                planeado=valor_mensual_efectivo(proyeccion),
                abono=por_mes.get((proyeccion.id_proyeccion, anio, mes)),
                estado=_estado_mes(
                    proyeccion.id_proyeccion,
                    anio,
                    mes,
                    por_mes,
                    saltados,
                    hoy,
                ),
            )
            for anio, mes in meses_de_la_meta(proyeccion)
        ]

        acumulado = redondear_dinero(
            sum(
                (
                    valor
                    for (id_meta, _anio, _mes), valor in por_mes.items()
                    if id_meta == proyeccion.id_proyeccion
                ),
                start=CERO,
            )
        )

        if proyeccion.meses:
            total: Decimal | None = redondear_dinero(
                valor_mensual_efectivo(proyeccion) * proyeccion.meses
            )
        else:
            total = None

        if total and total > CERO:
            porcentaje = redondear_dinero(acumulado / total * Decimal("100"))
            if porcentaje > Decimal("100"):
                porcentaje = Decimal("100")
        else:
            porcentaje = CERO

        anio_fin, mes_fin = meses_de_la_meta(proyeccion)[-1]
        cumplida = _posicion(hoy.year, hoy.month) > _posicion(anio_fin, mes_fin)

        resumenes.append(
            MetaResumen(
                proyeccion=proyeccion,
                total_proyectado=total,
                acumulado=acumulado,
                porcentaje=porcentaje,
                meses=meses,
                cumplida=cumplida,
                fin_etiqueta=_etiqueta_mes(anio_fin, mes_fin),
            )
        )
    return resumenes


def saldo_libre_total(
    bd: Session,
    id_usuario: str,
    perfil: PerfilFinanciero | None,
    anio: int,
    mes: int,
) -> Decimal:
    """Suma el saldo libre de todos los pagos del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        perfil: Perfil financiero del usuario.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).

    Returns:
        Saldo libre total redondeado a centavos; puede ser negativo.
    """
    resumen = servicio_quincenas.resumen_quincenas(bd, id_usuario, perfil, anio, mes)
    return redondear_dinero(sum((fila.saldo_libre for fila in resumen), start=CERO))


def diagnostico(
    bd: Session,
    id_usuario: str,
    perfil: PerfilFinanciero | None,
    anio: int,
    mes: int,
) -> dict[str, object]:
    """Resume la liquidez del mes para el banner de presupuesto.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        perfil: Perfil financiero del usuario.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).

    Returns:
        Diccionario con `saldo_libre` (Decimal), `extras_mes` (Decimal),
        `disponible` (Decimal), `alerta` (bool), `umbral` (Decimal) y
        `metas_mes` (Decimal). `saldo_libre` es el libre propio de Gastos y
        Presupuestos (la cuota vinculada ya se descontó en las quincenas);
        `extras_mes` es el saldo **neto** de Trabajos Extras (SRS v4.4).
        `disponible` es el «Total libre consolidado» que consume el Consejero.
        `alerta` indica que el disponible quedó por debajo de la base mínima
        configurada por el usuario (o $300.000 si el perfil es antiguo).
        `metas_mes` es informativo: ya está restado en el saldo porque cada meta
        vive como gasto fijo (SRS v1.6).
    """
    # SRS v4.4, sección 1: la cuota vinculada ya se descontó en las quincenas y
    # vive en la categoría 8 de la dona, así que NO se resta aquí otra vez.
    cuota_deudas = redondear_dinero(
        servicio_deudas.resumen_deudas(bd, id_usuario)["cuota_mensual"]
        + servicio_fijas.total_creditos_sin_vinculo(bd, id_usuario)
    )
    saldo = redondear_dinero(saldo_libre_total(bd, id_usuario, perfil, anio, mes))
    # Del módulo de Trabajos Extras se trae solo su saldo libre neto (ingresos
    # menos todos sus gastos fijos, incluidos los créditos vinculados).
    extras = servicio_trabajos.libre_neto_mes(bd, id_usuario, anio, mes)
    disponible = redondear_dinero(saldo + extras)
    inicio = date(anio, mes, 1)
    fin = date(anio + (mes // 12), (mes % 12) + 1, 1)
    gastos_meta = bd.scalars(
        select(Gasto).where(
            Gasto.id_usuario == id_usuario,
            Gasto.id_proyeccion.is_not(None),
            Gasto.fecha >= inicio,
            Gasto.fecha < fin,
        )
    )
    metas_mes = redondear_dinero(
        sum((valor_computable(gasto) for gasto in gastos_meta), start=CERO)
    )
    # SRS §5: el colchón lo elige cada usuario. Se expone en `umbral` para que
    # la plantilla y el Consejero usen exactamente la misma cifra.
    umbral = servicio_capacidad.base_minima_de(perfil)
    return {
        "saldo_libre": saldo,
        "cuota_deudas": cuota_deudas,
        "extras_mes": extras,
        "disponible": disponible,
        "alerta": disponible < umbral,
        "umbral": umbral,
        "metas_mes": metas_mes,
    }
