"""Envío de correos del sistema por SMTP estándar (SRS v1.8, bloque 8).

Responsabilidad
---------------
- Enviar correos con `smtplib` usando `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASS` y `SMTP_FROM`.
- Sin SMTP configurado: en desarrollo el contenido se escribe en el registro para
  poder probar el flujo; en producción solo se registra el fallo, sin contenido.
- Nunca registra contraseñas ni enlaces en producción.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import obtener_configuracion

registro = logging.getLogger("app.correo")
TIEMPO_ESPERA_SEGUNDOS = 15


def enviar_correo(destino: str, asunto: str, cuerpo: str) -> bool:
    """Envía un correo de texto plano.

    Args:
        destino: Dirección del destinatario.
        asunto: Asunto del mensaje.
        cuerpo: Texto del mensaje.

    Returns:
        `True` si se envió (o se registró en desarrollo); `False` si falló.
    """
    configuracion = obtener_configuracion()
    if not configuracion.smtp_host:
        if configuracion.es_produccion:
            registro.error("SMTP no está configurado en producción; no se envió un correo del sistema.")
            return False
        registro.warning("SMTP no configurado (desarrollo). Correo para %s · %s\n%s", destino, asunto, cuerpo)
        return True

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = configuracion.smtp_from or configuracion.smtp_user
    mensaje["To"] = destino
    mensaje.set_content(cuerpo)
    try:
        if configuracion.smtp_port == 465:
            servidor = smtplib.SMTP_SSL(configuracion.smtp_host, configuracion.smtp_port, timeout=TIEMPO_ESPERA_SEGUNDOS)
        else:
            servidor = smtplib.SMTP(configuracion.smtp_host, configuracion.smtp_port, timeout=TIEMPO_ESPERA_SEGUNDOS)
            servidor.starttls()
        with servidor:
            if configuracion.smtp_user:
                servidor.login(configuracion.smtp_user, configuracion.smtp_pass)
            servidor.send_message(mensaje)
        return True
    except (smtplib.SMTPException, OSError):
        registro.error("No se pudo enviar un correo del sistema por SMTP.")
        return False
