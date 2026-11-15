"""Planificador de ahorro y metas del usuario (SRS v1.3, bloque 3).

Responsabilidad
---------------
- Crear metas de ahorro o gastos programados con cuota mensual, duración y
  quincena de descuento.
- Registrar los abonos mensuales y calcular el progreso frente al total
  proyectado.
- Entregar el diagnóstico de liquidez del mes (saldo libre total de las
  quincenas) para el banner de «Gastos y Presupuesto».

La aritmética salarial vive en `app.servicios.nomina` y el saldo por pago en
`app.servicios.quincenas`; aquí solo se suma lo que ya está calculado.

Reglas:
- Una meta `LIMITADO` exige `meses` (1–120) y tiene total cerrado.
- Una meta `FIJO` no tiene total: se compara contra una ventana de 12 meses.
- Hay un único abono por meta y mes: volver a registrar el mismo mes actualiza
  el monto en lugar de duplicarlo.
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
from app.modelos import AbonoProyeccion, PerfilFinanciero, ProyeccionAhorro
from app.servicios import quincenas as servicio_quincenas

CERO = Decimal("0")

DURACION_FIJA = "FIJO"
DURACION_LIMITADA = "LIMITADO"
MESES_MAXIMOS = 120
# Ventana de comparación para los gastos fijos indefinidos, que no tienen final.
MESES_VENTANA_FIJA = 12
UMBRAL_ALERTA = Decimal("300000")

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
        abono: Monto realmente abonado, o `None` si aún no se registra.
    """

    anio: int
    mes: int
    etiqueta: str
    planeado: Decimal
    abono: Decimal | None = None

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
    if tipo == DURACION_FIJA:
        return tipo, None

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
) -> ProyeccionAhorro:
    """Registra una meta de ahorro o un gasto programado.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta.
        categoria: Categoría sugerida o texto libre.
        descripcion: Detalle del objetivo.
        valor_mensual: Cuota mensual; no puede ser negativa.
        tipo_duracion: `FIJO` (indefinido) o `LIMITADO`.
        meses: Cantidad de cuotas cuando la duración es limitada.
        fecha_inicio: Primer mes de la proyección; por defecto el mes en curso.
        quincena: `1` o `2`, pago del que se descuenta la cuota.

    Returns:
        La meta persistida.

    Raises:
        ValueError: Si falta la categoría o la descripción, el monto es negativo
            o inválido, la duración no es coherente o la quincena no es 1 ni 2.
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
        raise ValueError("La quincena de descuento debe ser 1 o 2.") from error
    if numero_quincena not in (1, 2):
        raise ValueError("La quincena de descuento debe ser 1 o 2.")

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


def eliminar_proyeccion(bd: Session, id_usuario: str, id_proyeccion: str) -> bool:
    """Elimina una meta y, en cascada, sus abonos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta (evita borrar datos ajenos).
        id_proyeccion: Identificador de la meta.

    Returns:
        `True` si se eliminó; `False` si no existe o es de otro usuario.
    """
    proyeccion = bd.get(ProyeccionAhorro, id_proyeccion)
    if proyeccion is None or proyeccion.id_usuario != id_usuario:
        return False
    bd.delete(proyeccion)
    bd.commit()
    return True


def registrar_abono(
    bd: Session,
    id_usuario: str,
    id_proyeccion: str,
    anio: int,
    mes: int,
    valor: Decimal | str | int | float,
) -> AbonoProyeccion | None:
    """Registra o actualiza el abono de un mes concreto.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta.
        id_proyeccion: Meta a la que se abona.
        anio: Año del abono.
        mes: Mes del abono (1–12).
        valor: Monto abonado; no puede ser negativo.

    Returns:
        El abono persistido, o `None` si la meta no existe o es de otro usuario.

    Raises:
        ValueError: Si el mes está fuera de rango o el monto es inválido.
    """
    proyeccion = bd.get(ProyeccionAhorro, id_proyeccion)
    if proyeccion is None or proyeccion.id_usuario != id_usuario:
        return None

    if mes < 1 or mes > 12:
        raise ValueError("El mes del abono debe estar entre 1 y 12.")

    monto = redondear_dinero(parsear_monto(str(valor)))
    if monto < CERO:
        raise ValueError("El valor del abono no puede ser negativo.")

    existente = bd.scalar(
        select(AbonoProyeccion).where(
            AbonoProyeccion.id_proyeccion == id_proyeccion,
            AbonoProyeccion.anio == anio,
            AbonoProyeccion.mes == mes,
        )
    )

    if existente is not None:
        # Un solo abono por mes: volver a registrar corrige el monto anterior.
        existente.valor = monto
        bd.commit()
        bd.refresh(existente)
        return existente

    abono = AbonoProyeccion(
        id_proyeccion=id_proyeccion,
        anio=anio,
        mes=mes,
        valor=monto,
    )
    bd.add(abono)
    bd.commit()
    bd.refresh(abono)
    return abono


def _meses_de_la_meta(proyeccion: ProyeccionAhorro) -> list[tuple[int, int]]:
    """Calcula la línea de tiempo de una meta.

    Args:
        proyeccion: Meta persistida.

    Returns:
        Lista de tuplas `(anio, mes)` desde el inicio hasta el final planificado.
    """
    cantidad = (
        proyeccion.meses
        if proyeccion.tipo_duracion == DURACION_LIMITADA and proyeccion.meses
        else MESES_VENTANA_FIJA
    )
    inicio = proyeccion.fecha_inicio
    return [
        _mover_mes(inicio.year, inicio.month, avance) for avance in range(cantidad)
    ]


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

    resumenes: list[MetaResumen] = []
    for proyeccion in proyecciones:
        meses = [
            MesMeta(
                anio=anio,
                mes=mes,
                etiqueta=_etiqueta_mes(anio, mes),
                planeado=proyeccion.valor_mensual,
                abono=por_mes.get((proyeccion.id_proyeccion, anio, mes)),
            )
            for anio, mes in _meses_de_la_meta(proyeccion)
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

        if proyeccion.tipo_duracion == DURACION_LIMITADA and proyeccion.meses:
            total: Decimal | None = redondear_dinero(
                proyeccion.valor_mensual * proyeccion.meses
            )
        else:
            total = None

        if total and total > CERO:
            porcentaje = redondear_dinero(acumulado / total * Decimal("100"))
            if porcentaje > Decimal("100"):
                porcentaje = Decimal("100")
        else:
            porcentaje = CERO

        resumenes.append(
            MetaResumen(
                proyeccion=proyeccion,
                total_proyectado=total,
                acumulado=acumulado,
                porcentaje=porcentaje,
                meses=meses,
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
        Diccionario con `saldo_libre` (Decimal), `alerta` (bool) y `umbral`
        (Decimal); `alerta` indica que el saldo quedó por debajo de $300.000.
    """
    saldo = saldo_libre_total(bd, id_usuario, perfil, anio, mes)
    return {
        "saldo_libre": saldo,
        "alerta": saldo < UMBRAL_ALERTA,
        "umbral": UMBRAL_ALERTA,
    }
