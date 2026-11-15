"""Bitácora de auditoría de acciones sensibles.

Responsabilidad
---------------
Registrar quién ejecutó una acción relevante (acceso, guardado, borrado o cambio
administrativo) sin almacenar contraseñas ni datos sensibles. La tabla
`auditoria` está documentada en `diccionario_datos.md` §13.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Auditoria


def registrar(
    bd: Session,
    id_usuario: str | None,
    accion: str,
    entidad: str | None = None,
    detalle: str | None = None,
) -> Auditoria:
    """Añade un evento a la bitácora.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Usuario que ejecutó la acción; `None` en intentos anónimos.
        accion: Código corto, por ejemplo ``LOGIN_OK`` o ``PERIODO_GUARDADO``.
        entidad: Tabla afectada, si aplica.
        detalle: Contexto legible, sin datos sensibles.

    Returns:
        El evento persistido.
    """
    evento = Auditoria(
        id_usuario=id_usuario,
        accion=accion.strip().upper()[:40],
        entidad=(entidad or "").strip()[:40] or None,
        detalle=(detalle or "").strip()[:300] or None,
    )
    bd.add(evento)
    bd.commit()
    bd.refresh(evento)
    return evento


def listar_eventos(bd: Session, limite: int = 100) -> list[Auditoria]:
    """Devuelve los eventos más recientes.

    Args:
        bd: Sesión de base de datos.
        limite: Número máximo de filas.

    Returns:
        Lista ordenada de la más reciente a la más antigua.
    """
    consulta = select(Auditoria).order_by(Auditoria.fecha.desc()).limit(limite)
    return list(bd.scalars(consulta))
