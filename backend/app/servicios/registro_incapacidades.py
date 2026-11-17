"""Persistencia de incapacidades y consulta de sus tramos mensuales.

Responsabilidad
---------------
Traducir el resultado de `servicios/incapacidad` a filas de `incapacidades` y
consultar los registros del usuario.

SRS v1.5: el descuento de cada mes sale solo del tramo calendario que cae en ese
mes. Ya no se generan saldos que se arrastren; cuando el usuario liquida otro
periodo, el sistema busca las incapacidades registradas que lo cubren y toma su
porción. Así el día 3 se cuenta una sola vez sobre la incapacidad completa.

El cálculo sigue siendo puro: este módulo solo guarda lo ya calculado y lo
vuelve a consultar.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modelos import Incapacidad, SaldoIncapacidad
from app.servicios.incapacidad import TramoMensual, calcular_incapacidad

CERO = Decimal("0")


def registrar_incapacidad(
    bd: Session,
    id_usuario: str,
    fecha_inicio: date,
    fecha_fin: date,
    sueldo_basico: Decimal | str,
    numero_incapacidad: str | None = None,
    origen: str = "COMUN",
) -> Incapacidad:
    """Registra una incapacidad con su rango y el descuento total.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la incapacidad.
        fecha_inicio: Primer día del rango.
        fecha_fin: Último día del rango (inclusive).
        sueldo_basico: Sueldo mensual con el que se calcula el descuento.
        numero_incapacidad: Número emitido por la EPS (opcional).
        origen: `COMUN` o `LABORAL`.

    Returns:
        La incapacidad persistida.

    Raises:
        ValueError: Si el rango o el origen son inválidos.
    """
    origen = origen.strip().upper()
    if origen not in ("COMUN", "LABORAL"):
        raise ValueError("El origen de la incapacidad debe ser COMUN o LABORAL.")

    liquidacion = calcular_incapacidad(fecha_inicio, fecha_fin, sueldo_basico)
    porcentaje = Decimal("66.67") if liquidacion.dias_al_66 else Decimal("100.00")

    incapacidad = Incapacidad(
        id_usuario=id_usuario,
        numero_incapacidad=(numero_incapacidad or "").strip() or None,
        origen=origen,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        # Días calendario del rango: fines de semana y festivos también cuentan.
        dias_totales=liquidacion.dias_totales,
        # El tramo del primer mes se conserva como referencia del registro.
        dias_mes_actual=liquidacion.tramos[0].dias if liquidacion.tramos else 0,
        # SRS v1.5: no hay días arrastrados que perseguir; cada mes se recalcula
        # desde las fechas cuando se liquida.
        dias_arrastrados=0,
        porcentaje_pago=porcentaje,
        valor_descontado=liquidacion.valor_descontado,
        estado="REGISTRADA",
    )
    bd.add(incapacidad)
    bd.commit()
    bd.refresh(incapacidad)
    return incapacidad


def tramos_del_mes(
    bd: Session,
    id_usuario: str,
    anio: int,
    mes: int,
    sueldo_basico: Decimal | str,
) -> list[TramoMensual]:
    """Devuelve el tramo del mes de cada incapacidad registrada que lo cubre.

    SRS v1.5: sustituye al rollover. Al liquidar un periodo se consultan las
    incapacidades guardadas que tocan ese mes y se toma únicamente su porción
    calendario; el resto de meses se liquidará en su propio periodo.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las incapacidades.
        anio: Año del periodo que se liquida.
        mes: Mes del periodo (1–12).
        sueldo_basico: Sueldo con el que se valora el día de incapacidad.

    Returns:
        Lista de tramos; vacía si ninguna incapacidad cubre el mes.
    """
    primero = date(anio, mes, 1)
    ultimo = date(anio + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1)
    consulta = (
        select(Incapacidad)
        .where(
            Incapacidad.id_usuario == id_usuario,
            Incapacidad.fecha_inicio <= ultimo,
            Incapacidad.fecha_fin >= primero,
        )
        .order_by(Incapacidad.fecha_inicio)
    )

    tramos: list[TramoMensual] = []
    for incapacidad in bd.scalars(consulta):
        liquidacion = calcular_incapacidad(
            incapacidad.fecha_inicio, incapacidad.fecha_fin, sueldo_basico
        )
        tramos.extend(
            tramo
            for tramo in liquidacion.tramos
            if (tramo.anio, tramo.mes) == (anio, mes)
        )
    return tramos


def descuento_del_mes(
    bd: Session,
    id_usuario: str,
    anio: int,
    mes: int,
    sueldo_basico: Decimal | str,
) -> Decimal:
    """Suma el descuento de las incapacidades registradas que cubren el mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las incapacidades.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).
        sueldo_basico: Sueldo con el que se valora el día de incapacidad.

    Returns:
        Descuento total en pesos; cero si no hay incapacidades en el mes.
    """
    tramos = tramos_del_mes(bd, id_usuario, anio, mes, sueldo_basico)
    return sum((tramo.valor_descontado for tramo in tramos), start=CERO)


def listar_incapacidades(bd: Session, id_usuario: str) -> list[Incapacidad]:
    """Devuelve las incapacidades del usuario, de la más reciente a la más antigua.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los registros.

    Returns:
        Lista de incapacidades ordenada por fecha de inicio descendente.
    """
    consulta = (
        select(Incapacidad)
        .where(Incapacidad.id_usuario == id_usuario)
        .order_by(Incapacidad.fecha_inicio.desc())
    )
    return list(bd.scalars(consulta))


def eliminar_incapacidad(bd: Session, id_usuario: str, id_incapacidad: str) -> bool:
    """Elimina una incapacidad y sus saldos heredados del modelo anterior.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro (evita borrar datos ajenos).
        id_incapacidad: Incapacidad a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    incapacidad = bd.get(Incapacidad, id_incapacidad)
    if incapacidad is None or incapacidad.id_usuario != id_usuario:
        return False

    # SRS v1.5 ya no crea saldos, pero se limpian los de versiones anteriores
    # para no dejar filas huérfanas si la base viene migrada.
    bd.execute(
        delete(SaldoIncapacidad).where(
            SaldoIncapacidad.id_incapacidad_origen == id_incapacidad
        )
    )
    bd.delete(incapacidad)
    bd.commit()
    return True
