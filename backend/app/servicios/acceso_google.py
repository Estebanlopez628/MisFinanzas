"""Inicio de sesión con Google (cuenta de Gmail) mediante OAuth 2.0 (ADR-48).

Responsabilidad
---------------
- Indicar si el inicio con Google está configurado (`GOOGLE_CLIENT_ID` y
  `GOOGLE_CLIENT_SECRET`).
- Construir la URL de autorización de Google con un `state` anti-falsificación.
- Cambiar el código devuelto por Google por el perfil verificado de la cuenta.

Se usa solo la biblioteca estándar de Python (`urllib`), así que no añade
dependencias. Este módulo no escribe en la base de datos: la cuenta la crea o
la busca la ruta de `auth.py`.
"""

from __future__ import annotations

import json
from urllib import error, parse, request

from app.core.config import obtener_configuracion

URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_PERFIL = "https://openidconnect.googleapis.com/v1/userinfo"
TIEMPO_ESPERA_SEGUNDOS = 10


class AccesoGoogleError(Exception):
    """Se lanza cuando Google no confirma la cuenta o la conexión falla."""


def google_activo() -> bool:
    """Indica si el inicio con Google tiene sus credenciales configuradas.

    Returns:
        `True` si hay identificador y secreto de cliente.
    """
    configuracion = obtener_configuracion()
    return bool(configuracion.google_client_id and configuracion.google_client_secret)


def url_autorizacion(estado: str) -> str:
    """Construye la URL a la que se envía la persona para elegir su cuenta de Google.

    Args:
        estado: Valor aleatorio que se compara al volver, para evitar falsificaciones.

    Returns:
        URL completa de autorización de Google.
    """
    configuracion = obtener_configuracion()
    parametros = {
        "client_id": configuracion.google_client_id,
        "redirect_uri": configuracion.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": estado,
        "prompt": "select_account",
    }
    return f"{URL_AUTORIZACION}?{parse.urlencode(parametros)}"


def _leer_json(solicitud: request.Request) -> dict[str, object]:
    """Ejecuta una petición HTTP y devuelve el cuerpo JSON.

    Args:
        solicitud: Petición ya preparada.

    Returns:
        Diccionario con la respuesta.

    Raises:
        AccesoGoogleError: Si la conexión falla o la respuesta no es JSON válido.
    """
    try:
        with request.urlopen(solicitud, timeout=TIEMPO_ESPERA_SEGUNDOS) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except (error.URLError, TimeoutError, ValueError) as fallo:
        raise AccesoGoogleError("No se pudo confirmar tu cuenta de Google. Intenta de nuevo.") from fallo


def intercambiar_codigo(codigo: str) -> dict[str, object]:
    """Cambia el código de Google por el perfil de la cuenta verificada.

    Args:
        codigo: Código de autorización que Google devuelve al volver.

    Returns:
        Perfil con `email`, `email_verified`, `name` y `given_name`.

    Raises:
        AccesoGoogleError: Si Google no entrega token, el correo no está verificado
            o la conexión falla.
    """
    configuracion = obtener_configuracion()
    datos = parse.urlencode(
        {
            "code": codigo,
            "client_id": configuracion.google_client_id,
            "client_secret": configuracion.google_client_secret,
            "redirect_uri": configuracion.google_redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    token = _leer_json(
        request.Request(
            URL_TOKEN,
            data=datos,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    )
    acceso = token.get("access_token")
    if not acceso:
        raise AccesoGoogleError("Google no entregó la autorización de tu cuenta.")

    perfil = _leer_json(
        request.Request(URL_PERFIL, headers={"Authorization": f"Bearer {acceso}"})
    )
    verificado = str(perfil.get("email_verified", "")).lower() == "true"
    if not perfil.get("email") or not verificado:
        raise AccesoGoogleError("Google no confirmó tu correo. Usa una cuenta de Gmail verificada.")
    return perfil
