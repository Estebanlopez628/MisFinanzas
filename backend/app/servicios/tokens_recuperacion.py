"""Tokens de recuperación de contraseña de un solo uso (SRS §6).

Responsabilidad
---------------
- Generar un token aleatorio seguro y guardar **únicamente** su SHA-256.
- Invalidar los enlaces anteriores cada vez que se solicita uno nuevo.
- Validar vigencia (20 minutos) y uso único antes de permitir el cambio.
- Mantener el hash de la contraseña en manos de `servicios.usuarios`, que ya
  aplica PBKDF2-HMAC-SHA256; aquí no se introduce bcrypt ni passlib.

Regla de negocio: el token en claro vive solo en el correo y en la petición.
Si la base de datos se filtrara, no sería posible reconstruir un enlace activo
a partir del hash. Cada enlace se marca como usado en cuanto se aplica, incluso
si el usuario vuelve a intentarlo antes de que venza.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import TokenRecuperacion
from app.servicios import usuarios

MINUTOS_VIGENCIA = 20


def agora_utc() -> datetime:
    """Devuelve la hora actual en UTC.

    Returns:
        Datetime consciente de zona horaria.
    """
    return datetime.now(timezone.utc)


def hash_token(token_crudo: str) -> str:
    """Calcula el SHA-256 del token en claro.

    Args:
        token_crudo: Texto aleatorio enviado en el enlace.

    Returns:
        Resumen hexadecimal de 64 caracteres.
    """
    return hashlib.sha256(token_crudo.encode("utf-8")).hexdigest()


def generar_token() -> str:
    """Crea un token aleatorio criptográficamente seguro.

    Returns:
        Texto de 32 bytes codificado en base64url (sin relleno).
    """
    return secrets.token_urlsafe(32)


def invalidar_previos(bd: Session, id_usuario: str) -> None:
    """Marca como usados todos los enlaces anteriores del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los tokens.

    Returns:
        None. La operación se confirma en la misma sesión.
    """
    for token in bd.scalars(
        select(TokenRecuperacion).where(
            TokenRecuperacion.id_usuario == id_usuario,
            TokenRecuperacion.used.is_(False),
        )
    ):
        token.used = True
    bd.commit()


def crear_registro(bd: Session, id_usuario: str, token_crudo: str) -> TokenRecuperacion:
    """Guarda el hash de un token nuevo con vigencia de 20 minutos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del enlace.
        token_crudo: Token que se enviará al correo (nunca se persiste).

    Returns:
        El registro persistido.
    """
    registro = TokenRecuperacion(
        id_usuario=id_usuario,
        token_hash=hash_token(token_crudo),
        expires_at=agora_utc() + timedelta(minutes=MINUTOS_VIGENCIA),
        used=False,
    )
    bd.add(registro)
    bd.commit()
    bd.refresh(registro)
    return registro


def solicitar_token(bd: Session, correo: str) -> tuple[str, str, str] | None:
    """Prepara un enlace nuevo si el correo pertenece a una cuenta activa.

    Args:
        bd: Sesión de base de datos.
        correo: Correo digitado en el formulario.

    Returns:
        Tupla `(token_en_claro, correo_normalizado, id_usuario)` o `None` si no
        hay cuenta activa.
    """
    correo_limpio = (correo or "").strip().lower()[:254]
    if not correo_limpio:
        return None
    cuenta = usuarios.buscar_por_correo(bd, correo_limpio)
    if cuenta is None or not cuenta.activo:
        return None
    invalidar_previos(bd, cuenta.id_usuario)
    token = generar_token()
    crear_registro(bd, cuenta.id_usuario, token)
    return token, cuenta.correo, cuenta.id_usuario


def _no_vencido(expires_at: datetime) -> bool:
    """Compara la expiración con la hora actual sea cual sea el motor de BD.

    SQLite devuelve datetimes sin zona aun cuando la columna es `timezone=True`;
    PostgreSQL devuelve datetimes conscientes. Se normalizan antes de comparar
    para que el enlace venza a los 20 minutos en ambos motores.

    Args:
        expires_at: Fecha límite leída de la base de datos.

    Returns:
        `True` si todavía queda tiempo de vigencia.
    """
    ahora = agora_utc()
    if expires_at.tzinfo is None:
        ahora = ahora.replace(tzinfo=None)
    else:
        expires_at = expires_at.astimezone(timezone.utc)
    return expires_at > ahora


def buscar_valido(bd: Session, token_crudo: str) -> TokenRecuperacion | None:
    """Busca un token vigente y sin usar.

    Args:
        bd: Sesión de base de datos.
        token_crudo: Token enviado por el enlace.

    Returns:
        El registro válido o `None` si no existe, ya se usó o venció.
    """
    if len(token_crudo) < 10:
        return None
    registro = bd.scalar(
        select(TokenRecuperacion).where(
            TokenRecuperacion.token_hash == hash_token(token_crudo),
            TokenRecuperacion.used.is_(False),
        )
    )
    if registro is None or not _no_vencido(registro.expires_at):
        return None
    return registro


def restablecer(
    bd: Session, token_crudo: str, contrasena_nueva: str
) -> tuple[str, str]:
    """Cambia la contraseña y consume el enlace de un solo uso.

    Args:
        bd: Sesión de base de datos.
        token_crudo: Token del enlace.
        contrasena_nueva: Nueva contraseña (mínimo 8 caracteres).

    Returns:
        Tupla `(id_usuario, correo)` de la cuenta actualizada.

    Raises:
        ValueError: Si el enlace es inválido, venció, ya se usó o la contraseña
            no cumple la longitud mínima.
    """
    registro = buscar_valido(bd, token_crudo)
    if registro is None:
        raise ValueError("El enlace es inválido o ha expirado.")
    cuenta = usuarios.obtener_por_id(bd, registro.id_usuario)
    if cuenta is None or not cuenta.activo:
        raise ValueError("El enlace es inválido o ha expirado.")
    usuarios.restablecer_contrasena(bd, cuenta.id_usuario, contrasena_nueva)
    registro.used = True
    bd.commit()
    return cuenta.id_usuario, cuenta.correo
