"""Pruebas de la SRS v3.1, bloque C (entrega efectiva del correo)."""

from __future__ import annotations

from pathlib import Path

from app.servicios import correo

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def test_configuracion_acepta_proveedores_https() -> None:
    """Se leen las claves de Resend, Brevo y SendGrid desde el entorno."""
    config = (RUTA_APP / "core/config.py").read_text(encoding="utf-8")
    for variable in ("RESEND_API_KEY", "BREVO_API_KEY", "SENDGRID_API_KEY"):
        assert f'os.getenv("{variable}"' in config


def test_prioridad_de_proveedores_y_log_de_respuesta() -> None:
    """Se prueban las APIs en orden y se registra el código exacto."""
    fuente = (RUTA_APP / "servicios/correo.py").read_text(encoding="utf-8")
    assert "def _enviar_por_api(" in fuente
    assert "https://api.resend.com/emails" in fuente
    assert "https://api.brevo.com/v3/smtp/email" in fuente
    assert "https://api.sendgrid.com/v3/mail/send" in fuente
    assert "HTTP %s" in fuente
    assert "error.code" in fuente
    assert "urllib.request.urlopen" in fuente
    # No se añade una dependencia nueva: se usa la biblioteca estándar.
    assert "import urllib.request" in fuente


def test_smtp_ssl_465_con_contraseña_de_aplicación() -> None:
    """Gmail usa SSL en 465 con timeout de 15 s y timeout STARTTLS de 10 s."""
    fuente = (RUTA_APP / "servicios/correo.py").read_text(encoding="utf-8")
    assert "TIEMPO_ESPERA_SEGUNDOS = 10" in fuente
    assert "TIEMPO_ESPERA_SSL_SEGUNDOS = 15" in fuente
    assert "smtplib.SMTP_SSL(" in fuente
    assert "465," in fuente
    assert "servidor.starttls()" in fuente
    assert "Contraseña de aplicación" in fuente or "contraseña de aplicación" in fuente


def test_configuracion_valida_incluye_apis() -> None:
    """Cualquier API habilita el envío sin exigir SMTP."""
    fuente = (RUTA_APP / "servicios/correo.py").read_text(encoding="utf-8")
    inicio = fuente.index("def configuracion_valida()")
    bloque = fuente[inicio : inicio + 900]
    assert "resend_api_key" in bloque
    assert "brevo_api_key" in bloque
    assert "sendgrid_api_key" in bloque


def test_rechazo_de_correo_se_registra_como_fallo() -> None:
    """Si el proveedor rechaza el destinatario se devuelve False."""
    fuente = (RUTA_APP / "servicios/correo.py").read_text(encoding="utf-8")
    assert "rechazados = servidor.send_message(mensaje)" in fuente
    assert "if rechazados:" in fuente
    assert correo.TIEMPO_ESPERA_SSL_SEGUNDOS == 15
