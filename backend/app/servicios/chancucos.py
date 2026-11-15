"""Referencias de pago rápido ("Chancucos").

Responsabilidad
---------------
Guardar las referencias que el administrador usa para pagar servicios, marcar
favoritos y eliminarlas. El copiado al portapapeles y el botón *Pagar* son
mejoras de interfaz; la validación de la URL vive aquí.
"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Chancuco


def _validar_url(url: str | None) -> str | None:
    """Valida que una URL de pago use HTTP o HTTPS.

    Args:
        url: Dirección opcional de la pasarela.

    Returns:
        La URL limpia o `None` si viene vacía.

    Raises:
        ValueError: Si la URL no es absoluta o usa otro esquema.
    """
    if url is None or not url.strip():
        return None
    limpia = url.strip()
    partes = urlparse(limpia)
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        raise ValueError("La URL de pago debe empezar por http:// o https://.")
    return limpia[:300]


def crear_chancuco(
    bd: Session,
    id_usuario: str,
    descripcion: str,
    numero_referencia: str,
    url_pago: str | None = None,
    favorito: bool = False,
) -> Chancuco:
    """Registra un atajo de pago.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del atajo.
        descripcion: Texto libre que identifica el atajo («EPM energía»).
        numero_referencia: Número que se copia al portapapeles.
        url_pago: Pasarela oficial, si existe; es opcional porque hay recibos
            que solo se pagan en ventanilla.
        favorito: Marca inicial de favorito.

    Returns:
        El atajo persistido.

    Raises:
        ValueError: Si falta la descripción o la referencia, o la URL es inválida.
    """
    descripcion_limpia = descripcion.strip()
    referencia_limpia = numero_referencia.strip()
    if not descripcion_limpia:
        raise ValueError("La descripción del atajo es obligatoria.")
    if not referencia_limpia:
        raise ValueError("El número de referencia es obligatorio.")

    chancuco = Chancuco(
        id_usuario=id_usuario,
        descripcion=descripcion_limpia[:120],
        numero_referencia=referencia_limpia[:60],
        url_pago=_validar_url(url_pago),
        favorito=favorito,
    )
    bd.add(chancuco)
    bd.commit()
    bd.refresh(chancuco)
    return chancuco


def listar_chancucos(bd: Session, id_usuario: str) -> list[Chancuco]:
    """Lista los atajos del usuario, primero los favoritos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los atajos.

    Returns:
        Lista ordenada por favorito y descripción.
    """
    consulta = (
        select(Chancuco)
        .where(Chancuco.id_usuario == id_usuario)
        .order_by(Chancuco.favorito.desc(), Chancuco.descripcion)
    )
    return list(bd.scalars(consulta))


def alternar_favorito(bd: Session, id_usuario: str, id_chancuco: str) -> Chancuco | None:
    """Cambia el estado de favorito de una referencia.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la referencia.
        id_chancuco: Referencia a modificar.

    Returns:
        La referencia actualizada o `None` si no existe o es de otro usuario.
    """
    chancuco = bd.get(Chancuco, id_chancuco)
    if chancuco is None or chancuco.id_usuario != id_usuario:
        return None
    chancuco.favorito = not chancuco.favorito
    bd.commit()
    bd.refresh(chancuco)
    return chancuco


def eliminar_chancuco(bd: Session, id_usuario: str, id_chancuco: str) -> bool:
    """Elimina una referencia de pago.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la referencia.
        id_chancuco: Referencia a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    chancuco = bd.get(Chancuco, id_chancuco)
    if chancuco is None or chancuco.id_usuario != id_usuario:
        return False
    bd.delete(chancuco)
    bd.commit()
    return True
