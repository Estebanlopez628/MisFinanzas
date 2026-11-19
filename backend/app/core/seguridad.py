"""Seguridad de la aplicación: hash de contraseñas y tokens de sesión.

Responsabilidad
---------------
- Guardar contraseñas con **PBKDF2-HMAC-SHA256** (nunca en texto plano).
- Emitir y verificar un token de sesión firmado con **HMAC-SHA256** (JWT HS256).
- Mantener la lógica criptográfica fuera de los routers.

Decisiones
----------
- Se evita una dependencia externa (passlib/python-jose) para reducir superficie
  y porque la primitiva necesaria está en la librería estándar.
- El token se envía en una cookie `HttpOnly` (ver `app.routers.auth`), por lo que
  JavaScript no puede leerlo.
- La clave de firma proviene de `CLAVE_SECRETA`; en producción es obligatoria.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import obtener_configuracion

# Parámetros de hashing. Subir las iteraciones es seguro: el formato guardado
# incluye el número usado, por lo que los hashes antiguos siguen verificando.
ALGORITMO_HASH = "pbkdf2_sha256"
ITERACIONES_PBKDF2 = 260_000

# Duración de la sesión: 8 horas (una jornada laboral).
DURACION_SESION_MINUTOS = 480


class TokenInvalido(Exception):
    """Se lanza cuando un token está mal formado, alterado o vencido."""


def hash_contrasena(contrasena: str) -> str:
    """Genera un hash seguro de la contraseña con sal aleatoria.

    Args:
        contrasena: Contraseña en texto plano (mínimo 8 caracteres).

    Returns:
        Cadena con formato ``pbkdf2_sha256$iteraciones$sal$hash``.

    Raises:
        ValueError: Si la contraseña es demasiado corta.
    """
    if len(contrasena) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")

    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac(
        "sha256", contrasena.encode("utf-8"), sal, ITERACIONES_PBKDF2
    )
    return f"{ALGORITMO_HASH}${ITERACIONES_PBKDF2}${sal.hex()}${derivada.hex()}"


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    """Comprueba una contraseña contra el hash almacenado.

    Usa comparación en tiempo constante para no filtrar información por tiempos.

    Args:
        contrasena: Contraseña ingresada por el usuario.
        hash_guardado: Hash persistido con `hash_contrasena`.

    Returns:
        `True` si coincide; `False` en cualquier otro caso (hash corrupto incluido).
    """
    try:
        algoritmo, iteraciones, sal_hex, hash_hex = hash_guardado.split("$")
        if algoritmo != ALGORITMO_HASH:
            return False
        derivada = hashlib.pbkdf2_hmac(
            "sha256",
            contrasena.encode("utf-8"),
            bytes.fromhex(sal_hex),
            int(iteraciones),
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(derivada.hex(), hash_hex)


def _codificar_base64url(datos: bytes) -> str:
    """Codifica bytes en base64url sin relleno (formato JWT).

    Args:
        datos: Contenido binario a codificar.

    Returns:
        Cadena base64url sin caracteres ``=``.
    """
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def _decodificar_base64url(texto: str) -> bytes:
    """Decodifica base64url agregando el relleno necesario.

    Args:
        texto: Cadena base64url.

    Returns:
        Bytes originales.

    Raises:
        TokenInvalido: Si la cadena no es base64url válida.
    """
    relleno = "=" * (-len(texto) % 4)
    try:
        return base64.urlsafe_b64decode(texto + relleno)
    except (ValueError, TypeError) as error:
        raise TokenInvalido("El token no es válido.") from error


def _firmar(mensaje: str) -> bytes:
    """Firma un mensaje con HMAC-SHA256 usando la clave de la aplicación.

    Args:
        mensaje: Texto a firmar (cabecera y payload unidos por punto).

    Returns:
        Firma binaria.
    """
    clave = obtener_configuracion().clave_secreta.encode("utf-8")
    return hmac.new(clave, mensaje.encode("ascii"), hashlib.sha256).digest()


def crear_token(
    id_usuario: str,
    rol: str,
    alias: str,
    minutos: int = DURACION_SESION_MINUTOS,
    ahora: float | None = None,
) -> str:
    """Emite un token de sesión firmado (JWT HS256).

    Args:
        id_usuario: Identificador del usuario autenticado.
        rol: Rol RBAC del usuario (`ADMIN_OLB` o `USER_FINANZAS`).
        alias: Apodo para los saludos personalizados.
        minutos: Vigencia del token en minutos.
        ahora: Marca de tiempo Unix de referencia (útil en pruebas).

    Returns:
        Token en formato ``cabecera.payload.firma``.
    """
    instante = int(ahora if ahora is not None else time.time())

    cabecera = {"alg": "HS256", "typ": "JWT"}
    contenido = {
        "sub": id_usuario,
        "rol": rol,
        "alias": alias,
        "iat": instante,
        "exp": instante + minutos * 60,
    }

    cabecera_codificada = _codificar_base64url(
        json.dumps(cabecera, separators=(",", ":")).encode("utf-8")
    )
    contenido_codificado = _codificar_base64url(
        json.dumps(contenido, separators=(",", ":")).encode("utf-8")
    )
    mensaje = f"{cabecera_codificada}.{contenido_codificado}"
    firma = _codificar_base64url(_firmar(mensaje))
    return f"{mensaje}.{firma}"


def _decodificar_contenido(token: str, ahora: float | None = None) -> dict[str, object]:
    """Verifica la firma y vigencia de un token y devuelve su contenido.

    Args:
        token: Token emitido por `crear_token`.
        ahora: Marca de tiempo Unix de referencia (útil en pruebas).

    Returns:
        Diccionario con `sub`, `rol`, `alias`, `iat` y `exp`.

    Raises:
        TokenInvalido: Si el token está mal formado, la firma no coincide o
            está vencido.
    """
    partes = token.split(".")
    if len(partes) != 3:
        raise TokenInvalido("El token no es válido.")

    cabecera_codificada, contenido_codificado, firma_codificada = partes
    mensaje = f"{cabecera_codificada}.{contenido_codificado}"

    try:
        firma_recibida = _decodificar_base64url(firma_codificada)
        cabecera = json.loads(_decodificar_base64url(cabecera_codificada))
        contenido = json.loads(_decodificar_base64url(contenido_codificado))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise TokenInvalido("El token no es válido.") from error

    if cabecera.get("alg") != "HS256":
        raise TokenInvalido("Algoritmo de firma no soportado.")

    if not hmac.compare_digest(firma_recibida, _firmar(mensaje)):
        raise TokenInvalido("La firma del token no coincide.")

    instante = int(ahora if ahora is not None else time.time())
    if not isinstance(contenido.get("exp"), int) or contenido["exp"] <= instante:
        raise TokenInvalido("La sesión ha vencido.")
    if not contenido.get("sub") or not contenido.get("rol"):
        raise TokenInvalido("El token no contiene los datos de sesión.")

    return contenido


def decodificar_token(token: str, ahora: float | None = None) -> dict[str, object]:
    """Verifica un token de sesión. Rechaza los tokens de recuperación (SRS v1.8).

    Args:
        token: Token de la cookie de sesión.
        ahora: Marca de tiempo Unix de referencia (útil en pruebas).

    Returns:
        Contenido del token de sesión.

    Raises:
        TokenInvalido: Si el token no es de sesión o no es válido.
    """
    contenido = _decodificar_contenido(token, ahora)
    if "proposito" in contenido:
        raise TokenInvalido("El token no es una sesión válida.")
    return contenido


def crear_token_recuperacion(
    id_usuario: str,
    rol: str,
    alias: str,
    huella: str,
    minutos: int = 15,
    ahora: float | None = None,
) -> str:
    """Emite un enlace de recuperación de contraseña que vence en 15 minutos.

    La huella es un resumen de la contraseña actual: al cambiarla, el enlace deja de
    servir, así que no se puede usar dos veces.

    Args:
        id_usuario: Cuenta que recupera la contraseña.
        rol: Rol de la cuenta (requerido por el formato común de tokens).
        alias: Alias de la cuenta.
        huella: Resumen de la contraseña vigente.
        minutos: Vigencia en minutos.
        ahora: Marca de tiempo Unix de referencia (útil en pruebas).

    Returns:
        Token firmado con propósito `recuperacion`.
    """
    instante = int(ahora if ahora is not None else time.time())
    cabecera = {"alg": "HS256", "typ": "JWT"}
    contenido = {
        "sub": id_usuario,
        "rol": rol,
        "alias": alias,
        "iat": instante,
        "exp": instante + minutos * 60,
        "proposito": "recuperacion",
        "huella": huella,
    }
    cabecera_codificada = _codificar_base64url(json.dumps(cabecera, separators=(",", ":")).encode("utf-8"))
    contenido_codificado = _codificar_base64url(json.dumps(contenido, separators=(",", ":")).encode("utf-8"))
    mensaje = f"{cabecera_codificada}.{contenido_codificado}"
    firma = _codificar_base64url(_firmar(mensaje))
    return f"{mensaje}.{firma}"


def decodificar_token_recuperacion(token: str, ahora: float | None = None) -> dict[str, object]:
    """Verifica un enlace de recuperación (firma, vigencia y propósito).

    Args:
        token: Token recibido en el enlace del correo.
        ahora: Marca de tiempo Unix de referencia (útil en pruebas).

    Returns:
        Contenido del token, con `sub` y `huella`.

    Raises:
        TokenInvalido: Si no es un enlace de recuperación válido o venció.
    """
    contenido = _decodificar_contenido(token, ahora)
    if contenido.get("proposito") != "recuperacion" or not contenido.get("huella"):
        raise TokenInvalido("El enlace no es de recuperación.")
    return contenido

