"""Repositorio de usuarios sobre SQLAlchemy (Fase 2).

Responsabilidad
---------------
Concentrar el alta, la autenticación y la administración de cuentas. Los routers
y dependencias no conocen SQL: solo llaman a estas funciones.

La contraseña se guarda exclusivamente como hash PBKDF2 (ver `core/seguridad.py`).
Las cuentas de demostración se siembran una sola vez, cuando la tabla está vacía.
"""

from __future__ import annotations

import hashlib

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import obtener_configuracion
from app.core.seguridad import hash_contrasena, verificar_contrasena
from app.modelos import Usuario

CORREO_PATRON = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

ROL_ADMIN = "ADMIN_OLB"
ROL_USUARIO = "USER_FINANZAS"
ROLES_VALIDOS = (ROL_ADMIN, ROL_USUARIO)

# Cuentas de demostración. Se eliminan cuando exista un flujo de aprovisionamiento
# real; mientras tanto permiten probar ambos roles sin datos previos.
CUENTAS_DEMO = (
    ("admin@olbbyte.co", "Admin123*", "Esteban", ROL_ADMIN),
    ("usuario@finanzas.co", "Usuario123*", "Camila", ROL_USUARIO),
)


def _normalizar_correo(correo: str) -> str:
    """Limpia y normaliza un correo electrónico.

    Args:
        correo: Texto ingresado por el usuario.

    Returns:
        Correo sin espacios y en minúsculas.
    """
    return correo.strip().lower()


def correo_valido(correo: str) -> bool:
    """Valida el formato básico de un correo electrónico.

    Args:
        correo: Correo a validar.

    Returns:
        `True` si cumple el patrón `usuario@dominio.xx`.
    """
    return bool(CORREO_PATRON.fullmatch(correo))


def sembrar_demostracion(bd: Session) -> None:
    """Crea las cuentas de demostración si la tabla está vacía.

    Args:
        bd: Sesión de base de datos.
    """
    # En producción nunca se crean cuentas con contraseñas conocidas: el acceso de
    # administrador sale del inicio con Google y de CORREOS_ADMIN_OLB (ADR-49).
    if obtener_configuracion().es_produccion:
        return
    total = bd.scalar(select(func.count()).select_from(Usuario)) or 0
    if total:
        return

    for correo, contrasena, alias, rol in CUENTAS_DEMO:
        bd.add(
            Usuario(
                correo=correo,
                hash_contrasena=hash_contrasena(contrasena),
                alias=alias,
                rol=rol,
            )
        )
    bd.commit()


def buscar_por_correo(bd: Session, correo: str) -> Usuario | None:
    """Busca un usuario por correo.

    Args:
        bd: Sesión de base de datos.
        correo: Correo a consultar.

    Returns:
        El usuario encontrado o `None`.
    """
    return bd.scalar(select(Usuario).where(Usuario.correo == _normalizar_correo(correo)))


def obtener_por_id(bd: Session, id_usuario: str) -> Usuario | None:
    """Busca un usuario por su identificador.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Identificador a consultar.

    Returns:
        El usuario encontrado o `None`.
    """
    return bd.get(Usuario, id_usuario)


def listar_usuarios(bd: Session) -> list[Usuario]:
    """Devuelve todas las cuentas ordenadas por fecha de registro.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Lista de usuarios (incluye inactivos, para la vista de administración).
    """
    return list(bd.scalars(select(Usuario).order_by(Usuario.fecha_registro)))


def autenticar(bd: Session, correo: str, contrasena: str) -> Usuario | None:
    """Verifica credenciales y devuelve el usuario si son correctas.

    Args:
        bd: Sesión de base de datos.
        correo: Correo ingresado.
        contrasena: Contraseña en texto plano.

    Returns:
        El usuario activo o `None` si las credenciales fallan.
    """
    usuario = buscar_por_correo(bd, correo)
    if usuario is None or not usuario.activo:
        return None
    if not verificar_contrasena(contrasena, usuario.hash_contrasena):
        return None

    usuario.ultimo_acceso = datetime.now(timezone.utc)
    bd.commit()
    return usuario


def crear_usuario(
    bd: Session,
    correo: str,
    contrasena: str,
    alias: str,
    rol: str = ROL_USUARIO,
) -> Usuario:
    """Registra una cuenta nueva.

    Args:
        bd: Sesión de base de datos.
        correo: Correo del nuevo usuario.
        contrasena: Contraseña en texto plano (mínimo 8 caracteres).
        alias: Apodo para los saludos.
        rol: Rol RBAC; por defecto `USER_FINANZAS`.

    Returns:
        El usuario creado y persistido.

    Raises:
        ValueError: Si el correo es inválido o ya existe, el alias es muy corto,
            la contraseña no cumple la política o el rol no es válido.
    """
    correo_normalizado = _normalizar_correo(correo)
    alias_limpio = alias.strip()

    if not correo_valido(correo_normalizado):
        raise ValueError("El correo electrónico no tiene un formato válido.")
    if buscar_por_correo(bd, correo_normalizado) is not None:
        raise ValueError("Ya existe una cuenta con ese correo.")
    if len(alias_limpio) < 2:
        raise ValueError("El alias debe tener al menos 2 caracteres.")
    if rol not in ROLES_VALIDOS:
        raise ValueError(f"Rol no válido: {rol!r}.")

    usuario = Usuario(
        correo=correo_normalizado,
        hash_contrasena=hash_contrasena(contrasena),
        alias=alias_limpio,
        rol=rol,
    )
    bd.add(usuario)
    bd.commit()
    bd.refresh(usuario)
    return usuario


def actualizar_alias(bd: Session, id_usuario: str, alias: str) -> Usuario:
    """Actualiza el apodo visible de una cuenta.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Cuenta a modificar.
        alias: Nuevo apodo (mínimo 2 caracteres).

    Returns:
        El usuario actualizado.

    Raises:
        ValueError: Si el alias es demasiado corto o la cuenta no existe.
    """
    alias_limpio = alias.strip()
    if len(alias_limpio) < 2:
        raise ValueError("El alias debe tener al menos 2 caracteres.")

    usuario = obtener_por_id(bd, id_usuario)
    if usuario is None:
        raise ValueError("La cuenta no existe.")

    usuario.alias = alias_limpio[:60]
    bd.commit()
    bd.refresh(usuario)
    return usuario


def cambiar_contrasena(
    bd: Session, id_usuario: str, contrasena_actual: str, contrasena_nueva: str
) -> None:
    """Cambia la contraseña de una cuenta verificando la actual.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Cuenta a modificar.
        contrasena_actual: Contraseña vigente en texto plano.
        contrasena_nueva: Nueva contraseña (mínimo 8 caracteres).

    Raises:
        ValueError: Si el usuario no existe, la contraseña actual no coincide o
            la nueva no cumple la política mínima.
    """
    usuario = obtener_por_id(bd, id_usuario)
    if usuario is None:
        raise ValueError("La cuenta no existe.")
    if not verificar_contrasena(contrasena_actual, usuario.hash_contrasena):
        raise ValueError("La contraseña actual no es correcta.")

    usuario.hash_contrasena = hash_contrasena(contrasena_nueva)
    bd.commit()


def cambiar_rol(bd: Session, id_usuario: str, rol: str) -> None:
    """Asigna un rol a una cuenta (solo administrador).

    Args:
        bd: Sesión de base de datos.
        id_usuario: Cuenta a modificar.
        rol: Nuevo rol RBAC.

    Raises:
        ValueError: Si el rol no existe o la cuenta no está registrada.
    """
    if rol not in ROLES_VALIDOS:
        raise ValueError(f"Rol no válido: {rol!r}.")

    usuario = obtener_por_id(bd, id_usuario)
    if usuario is None:
        raise ValueError("La cuenta no existe.")

    usuario.rol = rol
    bd.commit()


def cambiar_estado(bd: Session, id_usuario: str, activo: bool) -> None:
    """Activa o desactiva una cuenta (baja lógica).

    Args:
        bd: Sesión de base de datos.
        id_usuario: Cuenta a modificar.
        activo: Nuevo estado.

    Raises:
        ValueError: Si la cuenta no existe.
    """
    usuario = obtener_por_id(bd, id_usuario)
    if usuario is None:
        raise ValueError("La cuenta no existe.")
    usuario.activo = activo
    bd.commit()


def huella_contrasena(usuario: Usuario) -> str:
    """Resumen corto de la contraseña vigente, usado en los enlaces de recuperación.

    Args:
        usuario: Cuenta a resumir.

    Returns:
        Huella de 24 caracteres hexadecimales.
    """
    return hashlib.sha256(usuario.hash_contrasena.encode("utf-8")).hexdigest()[:24]


def restablecer_contrasena(bd: Session, id_usuario: str, contrasena_nueva: str) -> None:
    """Fija una contraseña nueva tras validar el enlace de recuperación.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Cuenta a modificar.
        contrasena_nueva: Nueva contraseña (mínimo 8 caracteres).

    Raises:
        ValueError: Si la cuenta no existe o la contraseña es muy corta.
    """
    usuario = obtener_por_id(bd, id_usuario)
    if usuario is None:
        raise ValueError("La cuenta no existe.")
    if len(contrasena_nueva) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    usuario.hash_contrasena = hash_contrasena(contrasena_nueva)
    bd.commit()


# Solo fotos alojadas por Google (HTTPS). Cualquier otra URL se descarta: así la
# base de datos nunca guarda enlaces arbitrarios que el navegador cargaría.
PATRON_AVATAR_GOOGLE = re.compile(r"https://[a-z0-9-]+\.googleusercontent\.com/[A-Za-z0-9_\-./=%?&]+")
LONGITUD_MAXIMA_AVATAR = 500


def url_avatar_valida(url: str | None) -> bool:
    """Indica si una URL de foto proviene de Google y cabe en la columna.

    Args:
        url: Dirección que devolvió el perfil de Google.

    Returns:
        `True` si es HTTPS, de `googleusercontent.com` y no supera 500 caracteres.
    """
    if not url or len(url) > LONGITUD_MAXIMA_AVATAR:
        return False
    return PATRON_AVATAR_GOOGLE.fullmatch(url) is not None


def actualizar_avatar(bd: Session, id_usuario: str, url: str | None) -> None:
    """Guarda la foto de Google de la cuenta, o la quita si ya no es válida.

    Se llama en cada inicio de sesión con Google, así que la foto se mantiene al día.
    Las cuentas con contraseña local nunca llegan aquí y conservan `NULL`.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Cuenta a actualizar.
        url: Foto que informó Google, o `None` si no hay una válida.
    """
    usuario = obtener_por_id(bd, id_usuario)
    if usuario is None:
        return
    usuario.avatar_url = url if url_avatar_valida(url) else None
    bd.commit()

