"""Pasivos del usuario ("Resumen de Deudas").

Responsabilidad
---------------
Registrar deudas, aplicar abonos al saldo y marcar su estado. La tabla `deudas`
está documentada en `diccionario_datos.md` §8.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import a_decimal, redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import Deuda

CERO = Decimal("0")
ESTADO_ACTIVA = "ACTIVA"
ESTADO_PAGADA = "PAGADA"


def crear_deuda(
    bd: Session,
    id_usuario: str,
    acreedor: str,
    saldo_total: Decimal | str | int | float,
    descripcion: str | None = None,
    cuota_mensual: Decimal | str | int | float | None = None,
    tasa_interes: Decimal | str | int | float | None = None,
    fecha_limite: date | None = None,
) -> Deuda:
    """Registra una deuda.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda.
        acreedor: Persona o entidad acreedora.
        saldo_total: Saldo pendiente inicial.
        descripcion: Detalle opcional.
        cuota_mensual: Cuota pactada, si existe.
        tasa_interes: Tasa porcentual, si existe.
        fecha_limite: Fecha límite de pago.

    Returns:
        La deuda persistida.

    Raises:
        ValueError: Si falta el acreedor o algún monto es negativo o inválido.
    """
    acreedor_limpio = acreedor.strip()
    if not acreedor_limpio:
        raise ValueError("El acreedor es obligatorio.")

    saldo = redondear_dinero(parsear_monto(str(saldo_total)))
    if saldo < CERO:
        raise ValueError("El saldo total no puede ser negativo.")

    cuota = None
    if cuota_mensual not in (None, ""):
        cuota = redondear_dinero(parsear_monto(str(cuota_mensual)))
        if cuota < CERO:
            raise ValueError("La cuota mensual no puede ser negativa.")

    tasa = None
    if tasa_interes not in (None, ""):
        tasa = a_decimal(tasa_interes, "tasa de interés")
        if tasa < CERO:
            raise ValueError("La tasa de interés no puede ser negativa.")

    deuda = Deuda(
        id_usuario=id_usuario,
        acreedor=acreedor_limpio[:100],
        descripcion=(descripcion or "").strip()[:150] or None,
        saldo_total=saldo,
        cuota_mensual=cuota,
        tasa_interes=tasa,
        fecha_limite=fecha_limite,
        estado=ESTADO_PAGADA if saldo == CERO else ESTADO_ACTIVA,
    )
    bd.add(deuda)
    bd.commit()
    bd.refresh(deuda)
    return deuda


def listar_deudas(bd: Session, id_usuario: str) -> list[Deuda]:
    """Lista las deudas del usuario, activas primero.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.

    Returns:
        Lista ordenada por estado y fecha límite.
    """
    consulta = (
        select(Deuda)
        .where(Deuda.id_usuario == id_usuario)
        .order_by(Deuda.estado, Deuda.fecha_limite)
    )
    return list(bd.scalars(consulta))


def abonar_deuda(
    bd: Session, id_usuario: str, id_deuda: str, monto: Decimal | str | int | float
) -> Deuda:
    """Aplica un abono al saldo de una deuda.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda.
        id_deuda: Deuda a modificar.
        monto: Dinero abonado; debe ser positivo y no superar el saldo.

    Returns:
        La deuda actualizada.

    Raises:
        ValueError: Si la deuda no existe, no pertenece al usuario, el monto es
            inválido o supera el saldo pendiente.
    """
    deuda = bd.get(Deuda, id_deuda)
    if deuda is None or deuda.id_usuario != id_usuario:
        raise ValueError("La deuda no existe.")

    valor_normalizado = redondear_dinero(parsear_monto(str(monto)))
    if valor_normalizado <= CERO:
        raise ValueError("El abono debe ser mayor que cero.")
    if valor_normalizado > deuda.saldo_total:
        raise ValueError("El abono no puede superar el saldo pendiente.")

    deuda.saldo_total = redondear_dinero(deuda.saldo_total - valor_normalizado)
    deuda.estado = ESTADO_PAGADA if deuda.saldo_total == CERO else ESTADO_ACTIVA
    bd.commit()
    bd.refresh(deuda)
    return deuda


def eliminar_deuda(bd: Session, id_usuario: str, id_deuda: str) -> bool:
    """Elimina una deuda.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda.
        id_deuda: Deuda a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    deuda = bd.get(Deuda, id_deuda)
    if deuda is None or deuda.id_usuario != id_usuario:
        return False
    bd.delete(deuda)
    bd.commit()
    return True


def resumen_deudas(bd: Session, id_usuario: str) -> dict[str, Decimal | int]:
    """Calcula los totales del módulo de deudas.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.

    Returns:
        Diccionario con saldo total, cuota mensual, número de activas y número
        de pagadas.
    """
    deudas = listar_deudas(bd, id_usuario)
    activas = [deuda for deuda in deudas if deuda.estado == ESTADO_ACTIVA]
    return {
        "saldo_total": redondear_dinero(sum((deuda.saldo_total for deuda in activas), start=CERO)),
        "cuota_mensual": redondear_dinero(
            sum((deuda.cuota_mensual or CERO for deuda in activas), start=CERO)
        ),
        "activas": len(activas),
        "pagadas": len(deudas) - len(activas),
    }
