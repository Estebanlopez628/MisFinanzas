"""Ingresos independientes ("Trabajos Extras").

Responsabilidad
---------------
Registrar trabajos por fuera del salario, marcarlos como cobrados y calcular los
totales pendientes y cobrados. La tabla `trabajos_extras` está documentada en
`diccionario_datos.md` §12.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import TrabajoExtra

CERO = Decimal("0")
ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_COBRADO = "COBRADO"
ESTADOS_VALIDOS = (ESTADO_PENDIENTE, ESTADO_COBRADO)


def crear_trabajo(
    bd: Session,
    id_usuario: str,
    descripcion: str,
    valor: Decimal | str | int | float,
    fecha: date,
    cliente: str | None = None,
) -> TrabajoExtra:
    """Registra un trabajo extra.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro.
        descripcion: Trabajo o servicio realizado.
        valor: Monto cobrado o pactado.
        fecha: Fecha del ingreso.
        cliente: Persona o empresa que contrató.

    Returns:
        El trabajo persistido.

    Raises:
        ValueError: Si la descripción está vacía o el valor es negativo o
            inválido.
    """
    descripcion_limpia = descripcion.strip()
    if not descripcion_limpia:
        raise ValueError("La descripción del trabajo es obligatoria.")

    monto = redondear_dinero(parsear_monto(str(valor)))
    if monto < CERO:
        raise ValueError("El valor del trabajo no puede ser negativo.")

    trabajo = TrabajoExtra(
        id_usuario=id_usuario,
        descripcion=descripcion_limpia[:150],
        cliente=(cliente or "").strip()[:100] or None,
        valor=monto,
        fecha=fecha,
        estado=ESTADO_PENDIENTE,
    )
    bd.add(trabajo)
    bd.commit()
    bd.refresh(trabajo)
    return trabajo


def listar_trabajos(bd: Session, id_usuario: str) -> list[TrabajoExtra]:
    """Lista los trabajos extra del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los registros.

    Returns:
        Lista ordenada por fecha descendente.
    """
    consulta = (
        select(TrabajoExtra)
        .where(TrabajoExtra.id_usuario == id_usuario)
        .order_by(TrabajoExtra.fecha.desc())
    )
    return list(bd.scalars(consulta))


def cambiar_estado(
    bd: Session, id_usuario: str, id_trabajo: str, estado: str
) -> TrabajoExtra:
    """Marca un trabajo como pendiente o cobrado.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro.
        id_trabajo: Trabajo a modificar.
        estado: `PENDIENTE` o `COBRADO`.

    Returns:
        El trabajo actualizado.

    Raises:
        ValueError: Si el estado no es válido o el trabajo no pertenece al
            usuario.
    """
    estado_limpio = estado.strip().upper()
    if estado_limpio not in ESTADOS_VALIDOS:
        raise ValueError("El estado debe ser PENDIENTE o COBRADO.")

    trabajo = bd.get(TrabajoExtra, id_trabajo)
    if trabajo is None or trabajo.id_usuario != id_usuario:
        raise ValueError("El trabajo no existe.")

    trabajo.estado = estado_limpio
    bd.commit()
    bd.refresh(trabajo)
    return trabajo


def eliminar_trabajo(bd: Session, id_usuario: str, id_trabajo: str) -> bool:
    """Elimina un trabajo extra.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro.
        id_trabajo: Trabajo a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    trabajo = bd.get(TrabajoExtra, id_trabajo)
    if trabajo is None or trabajo.id_usuario != id_usuario:
        return False
    bd.delete(trabajo)
    bd.commit()
    return True


def resumen_trabajos(bd: Session, id_usuario: str) -> dict[str, Decimal | int]:
    """Calcula los totales de trabajos extras.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los registros.

    Returns:
        Diccionario con total cobrado, total pendiente y conteos.
    """
    trabajos = listar_trabajos(bd, id_usuario)
    cobrados = [t for t in trabajos if t.estado == ESTADO_COBRADO]
    pendientes = [t for t in trabajos if t.estado == ESTADO_PENDIENTE]
    return {
        "cobrado": redondear_dinero(sum((t.valor for t in cobrados), start=CERO)),
        "pendiente": redondear_dinero(sum((t.valor for t in pendientes), start=CERO)),
        "cobrados": len(cobrados),
        "pendientes": len(pendientes),
    }
