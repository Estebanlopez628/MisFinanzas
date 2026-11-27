"""Envío de correos del sistema: APIs transaccionales HTTPS o SMTP (SRS v3.1).

Responsabilidad
---------------
- Priorizar proveedores por API HTTPS (Resend, Brevo, SendGrid), que no sufren
  bloqueo de puertos en Render.
- Si no hay API, usar SMTP SSL en puerto 465 (obligatorio para Gmail con
  contraseña de aplicación) o STARTTLS en el puerto configurado.
- Registrar el código exacto de respuesta del proveedor (por ejemplo `250 OK`
  o el estado HTTP) y el error detallado cuando falle, sin exponer secretos.
- Sin proveedor en desarrollo: registrar el contenido para poder probar el
  flujo. En producción: avisar del fallo sin contenido ni enlaces.

Nunca registra contraseñas ni el enlace de recuperación en producción.
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core.config import obtener_configuracion

registro = logging.getLogger("app.correo")
# Timeout del v3.0 para STARTTLS.
TIEMPO_ESPERA_SEGUNDOS = 10
# SRS v3.1: Gmail SMTP_SSL en 465 con contraseña de aplicación.
TIEMPO_ESPERA_SSL_SEGUNDOS = 15


def _destinatario(configuracion) -> str:
    """Devuelve la dirección `From` disponible.

    Args:
        configuracion: Configuración de la aplicación.

    Returns:
        Correo de origen, o cadena vacía si no hay ninguno configurado.
    """
    return (
        getattr(configuracion, "smtp_from", "")
        or getattr(configuracion, "smtp_user", "")
        or ""
    ).strip()


def _enviar_por_api(
    configuracion,
    destino: str,
    asunto: str,
    cuerpo: str,
    html: str | None = None,
) -> bool | None:
    """Intenta enviar por la primera API transaccional configurada.

    Args:
        configuracion: Configuración de la aplicación.
        destino: Correo del destinatario.
        asunto: Asunto del mensaje.
        cuerpo: Texto plano del mensaje.
        html: Contenido HTML opcional (SRS §6, correo de recuperación).

    Returns:
        `True`/`False` si se intentó un proveedor; `None` si no hay ninguno.
    """
    remitente = _destinatario(configuracion)
    proveedor = None
    url = ""
    cabeceras: dict[str, str] = {"Content-Type": "application/json"}
    datos: dict[str, object] = {}

    if getattr(configuracion, "resend_api_key", ""):
        proveedor = "Resend"
        url = "https://api.resend.com/emails"
        cabeceras["Authorization"] = f"Bearer {configuracion.resend_api_key}"
        # SRS §6: RESEND_FROM manda solo para Resend; los demás proveedores
        # conservan el remitente histórico del proyecto.
        remitente = getattr(configuracion, "resend_from", "").strip() or remitente
        datos = {
            "from": remitente,
            "to": [destino],
            "subject": asunto,
            "text": cuerpo,
        }
        if html:
            datos["html"] = html
    elif getattr(configuracion, "brevo_api_key", ""):
        proveedor = "Brevo"
        url = "https://api.brevo.com/v3/smtp/email"
        cabeceras["api-key"] = configuracion.brevo_api_key
        datos = {
            "sender": {"email": remitente, "name": "MisFinanzas"},
            "to": [{"email": destino}],
            "subject": asunto,
            "textContent": cuerpo,
        }
        if html:
            datos["htmlContent"] = html
    elif getattr(configuracion, "sendgrid_api_key", ""):
        proveedor = "SendGrid"
        url = "https://api.sendgrid.com/v3/mail/send"
        cabeceras["Authorization"] = f"Bearer {configuracion.sendgrid_api_key}"
        contenido = [{"type": "text/plain", "value": cuerpo}]
        if html:
            contenido.append({"type": "text/html", "value": html})
        datos = {
            "personalizations": [{"to": [{"email": destino}]}],
            "from": {"email": remitente},
            "subject": asunto,
            "content": contenido,
        }

    if proveedor is None:
        return None

    if not remitente:
        registro.error(
            "Proveedor %s configurado pero falta la dirección de origen (SMTP_FROM/FROM_EMAIL).",
            proveedor,
        )
        return False

    peticion = urllib.request.Request(
        url,
        data=json.dumps(datos).encode("utf-8"),
        headers=cabeceras,
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA_SEGUNDOS) as respuesta:
            codigo = respuesta.status
        registro.info("Correo enviado por %s: HTTP %s para %s.", proveedor, codigo, destino)
        return 200 <= codigo < 300
    except urllib.error.HTTPError as error:
        registro.error(
            "Fallo %s al enviar a %s: HTTP %s. Revisa la clave de API y el remitente verificado.",
            proveedor,
            destino,
            error.code,
        )
        return False
    except (urllib.error.URLError, OSError) as error:
        registro.error(
            "Fallo de red con %s al enviar a %s: %s: %s",
            proveedor,
            destino,
            type(error).__name__,
            error,
        )
        return False


def enviar_correo(destino: str, asunto: str, cuerpo: str, html: str | None = None) -> bool:
    """Envía un correo de texto plano (y HTML opcional) por API HTTPS o SMTP.

    Args:
        destino: Dirección del destinatario.
        asunto: Asunto del mensaje.
        cuerpo: Texto del mensaje.
        html: Alternativa HTML para APIs que la soportan (SRS §6).

    Returns:
        `True` si se entregó al proveedor (o se registró en desarrollo);
        `False` si falló.
    """
    configuracion = obtener_configuracion()
    por_api = _enviar_por_api(configuracion, destino, asunto, cuerpo, html)
    if por_api is not None:
        return por_api

    if not getattr(configuracion, "smtp_host", ""):
        if getattr(configuracion, "es_produccion", False):
            registro.error(
                "No hay proveedor de correo configurado en producción; no se envió un correo del sistema."
            )
            return False
        registro.warning(
            "Sin proveedor de correo (desarrollo). Correo para %s · %s\n%s",
            destino,
            asunto,
            cuerpo,
        )
        return True

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = _destinatario(configuracion) or configuracion.smtp_user
    mensaje["To"] = destino
    if html:
        mensaje.set_content(cuerpo)
        mensaje.add_alternative(html, subtype="html")
    else:
        mensaje.set_content(cuerpo)
    try:
        if configuracion.smtp_port == 465:
            servidor = smtplib.SMTP_SSL(
                configuracion.smtp_host,
                465,
                timeout=TIEMPO_ESPERA_SSL_SEGUNDOS,
            )
        else:
            servidor = smtplib.SMTP(
                configuracion.smtp_host,
                configuracion.smtp_port,
                timeout=TIEMPO_ESPERA_SEGUNDOS,
            )
            servidor.starttls()
        with servidor:
            if configuracion.smtp_user:
                servidor.login(configuracion.smtp_user, configuracion.smtp_pass)
            rechazados = servidor.send_message(mensaje)
        if rechazados:
            registro.error("SMTP rechazó el correo para %s: %s", destino, rechazados)
            return False
        registro.info("Correo SMTP aceptado por el servidor para %s (250 OK).", destino)
        return True
    except (smtplib.SMTPException, OSError) as error:
        registro.error(
            "Fallo SMTP al enviar a %s (asunto: %s): %s: %s",
            destino,
            asunto,
            type(error).__name__,
            error,
        )
        return False


def configuracion_valida() -> bool:
    """Indica si existe algún medio de envío utilizable.

    Returns:
        `True` con cualquier API configurada, con SMTP completo, o en
        desarrollo (donde el correo se registra en el log).
    """
    configuracion = obtener_configuracion()
    if (
        getattr(configuracion, "resend_api_key", "")
        or getattr(configuracion, "brevo_api_key", "")
        or getattr(configuracion, "sendgrid_api_key", "")
    ):
        return True
    if not getattr(configuracion, "es_produccion", False):
        return True
    return bool(
        getattr(configuracion, "smtp_host", "")
        and getattr(configuracion, "smtp_user", "")
        and getattr(configuracion, "smtp_pass", "")
    )


def enviar_recuperacion(destino: str, alias: str, enlace: str) -> bool:
    """Despacha el correo de recuperación y registra el resultado exacto.

    Args:
        destino: Correo de la cuenta.
        alias: Apodo del usuario, para el saludo.
        enlace: URL de restablecimiento de un solo uso.

    Returns:
        `True` si el correo se entregó al proveedor; `False` si falló.
    """
    cuerpo = (
        f"Hola {alias}.\n\n"
        "Para crear una nueva contraseña abre este enlace. Vence en 15 minutos:\n"
        f"{enlace}\n\n"
        "Si no pediste este cambio, ignora este correo."
    )
    enviado = enviar_correo(destino, "Recupera tu contraseña · OLB Finanzas", cuerpo)
    if enviado:
        registro.info("Correo de recuperación enviado correctamente a %s.", destino)
    else:
        registro.error(
            "No se pudo enviar el correo de recuperación a %s. "
            "Revisa RESEND_API_KEY/BREVO_API_KEY/SENDGRID_API_KEY o SMTP_HOST, "
            "SMTP_PORT, SMTP_USER y la contraseña de aplicación.",
            destino,
        )
    return enviado


# SRS §6: vigencia del enlace de un solo uso generado por `/auth/forgot-password`.
MINUTOS_TOKEN_RECUPERACION = 20


def enviar_recuperacion_token(destino: str, enlace: str) -> bool:
    """Envía el enlace de restablecimiento de 20 minutos con Resend u otro proveedor.

    Args:
        destino: Correo de la cuenta.
        enlace: URL `/reset-password?token=...` con el token en claro.

    Returns:
        `True` si el proveedor aceptó el correo; `False` si falló.
    """
    cuerpo = (
        "Hola,\n\n"
        "Recibimos una solicitud para restablecer tu contraseña.\n"
        f"Abre este enlace: {enlace}\n"
        f"(el enlace vence en {MINUTOS_TOKEN_RECUPERACION} minutos).\n\n"
        "Si no pediste este cambio, ignora este correo."
    )
    html = (
        "<p>Hola,</p><p>Recibimos una solicitud para restablecer tu contraseña.</p>"
        f"<p><a href='{enlace}'>Haz clic aquí para restablecer tu contraseña</a> "
        f"(el enlace vence en {MINUTOS_TOKEN_RECUPERACION} minutos).</p>"
    )
    enviado = enviar_correo(
        destino, "Recupera tu contraseña · OLB BYTE", cuerpo, html=html
    )
    if enviado:
        registro.info("Enlace de recuperación de un solo uso enviado a %s.", destino)
    else:
        registro.error(
            "No se pudo enviar el enlace de recuperación a %s. "
            "Revisa RESEND_API_KEY y RESEND_FROM (o el proveedor de correo alternativo).",
            destino,
        )
    return enviado
