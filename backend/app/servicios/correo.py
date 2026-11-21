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
# SRS v3.0, punto 6.3: timeout controlado para que el endpoint no se quede
# colgado esperando al servidor SMTP.
TIEMPO_ESPERA_SEGUNDOS = 10


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
    except (smtplib.SMTPException, OSError) as error:
        # Se registra el tipo de fallo y su motivo, nunca credenciales ni el
        # enlace de recuperación (que sí puede alterar la cuenta).
        registro.error(
            "Fallo SMTP al enviar a %s (asunto: %s): %s: %s",
            destino,
            asunto,
            type(error).__name__,
            error,
        )
        return False


def configuracion_valida() -> bool:
    """Indica si hay suficiente configuración SMTP para intentar un envío.

    Returns:
        `True` si el envío puede intentarse. En desarrollo se permite continuar
        sin SMTP porque `enviar_correo` registra el contenido en el log; en
        producción se exigen host, usuario y contraseña.
    """
    configuracion = obtener_configuracion()
    if not configuracion.es_produccion:
        return True
    return bool(
        configuracion.smtp_host
        and configuracion.smtp_user
        and configuracion.smtp_pass
    )


def enviar_recuperacion(destino: str, alias: str, enlace: str) -> bool:
    """Despacha el correo de recuperación y deja constancia explícita del resultado.

    Se ejecuta en una tarea de fondo de FastAPI: la petición responde de inmediato
    y el registro del servidor guarda el éxito o el error SMTP real.

    Args:
        destino: Correo de la cuenta.
        alias: Apodo del usuario, para el saludo.
        enlace: URL de restablecimiento de un solo uso.

    Returns:
        `True` si el correo se entregó al servidor SMTP; `False` si falló.
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
            "Revisa SMTP_HOST, SMTP_PORT, SMTP_USER y la contraseña de aplicación.",
            destino,
        )
    return enviado
