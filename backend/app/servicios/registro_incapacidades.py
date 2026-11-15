"""Persistencia de incapacidades y sus saldos de rollover.

Responsabilidad
---------------
Traducir el resultado de `servicios/incapacidad` a filas de `incapacidades` y
`saldos_incapacidad`, y consultar los registros del usuario.

El cálculo sigue siendo puro: este módulo solo guarda lo ya calculado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Incapacidad, SaldoIncapacidad
from app.servicios.incapacidad import liquidar_mes_incapacidad


def registrar_incapacidad(
    bd: Session,
    id_usuario: str,
    fecha_inicio: date,
    fecha_fin: date,
    sueldo_basico: Decimal | str,
    numero_incapacidad: str | None = None,
    origen: str = "COMUN",
) -> Incapacidad:
    """Registra una incapacidad y genera los saldos de los meses posteriores.

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

    resultado = liquidar_mes_incapacidad(fecha_inicio, fecha_fin, sueldo_basico)
    porcentaje = Decimal("66.67") if resultado.dias_al_66 else Decimal("100.00")

    incapacidad = Incapacidad(
        id_usuario=id_usuario,
        numero_incapacidad=(numero_incapacidad or "").strip() or None,
        origen=origen,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        dias_totales=resultado.dias_liquidados + resultado.dias_arrastrados,
        dias_mes_actual=resultado.dias_liquidados,
        dias_arrastrados=resultado.dias_arrastrados,
        porcentaje_pago=porcentaje,
        valor_descontado=resultado.valor_descontado,
        estado="REGISTRADA",
    )
    bd.add(incapacidad)
    bd.flush()

    # Un saldo por cada mes posterior; el día 3 se conserva porque el cálculo ya
    # viene repartido desde el motor puro.
    for saldo in resultado.saldos_pendientes:
        bd.add(
            SaldoIncapacidad(
                id_usuario=id_usuario,
                id_incapacidad_origen=incapacidad.id_incapacidad,
                anio=saldo.anio,
                mes=saldo.mes,
                dias_pendientes=saldo.dias_pendientes,
                valor_pendiente=saldo.valor_pendiente,
            )
        )

    bd.commit()
    bd.refresh(incapacidad)
    return incapacidad


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
    """Elimina una incapacidad y, en cascada, sus saldos pendientes.

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

    bd.delete(incapacidad)
    bd.commit()
    return True
