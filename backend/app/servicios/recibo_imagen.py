"""Recibo de abono de OLB_BYTE como imagen PNG para compartir por WhatsApp (RF-07).

Responsabilidad
---------------
- Reunir los datos del recibo de un abono (orden, abonos y saldo).
- Dibujar el recibo con la misma tarjeta de la pantalla (`_recibo.html`) y el CSS
  de la aplicación, y convertirlo en PNG con Chromium.
- Dar el nombre del archivo y el mensaje que acompaña la imagen.

El navegador es el mismo que usa la factura PDF (ADR-36).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.modelos import Abono, Venta
from app.servicios import comercial
from app.servicios.factura_pdf import ChromiumNoDisponible

RUTA_CSS_APLICACION = Path(__file__).resolve().parents[1] / "static" / "css" / "estilos.css"


def nombre_archivo_recibo(venta: Venta, abono: Abono) -> str:
    """Forma el nombre del PNG del recibo.

    Args:
        venta: Orden abonada.
        abono: Abono que se comparte.

    Returns:
        Nombre como `Recibo_OLB_BYTE_No_3_20261118_1530.png`.
    """
    momento = abono.fecha_abono.strftime("%Y%m%d_%H%M")
    return f"Recibo_OLB_BYTE_No_{venta.numero_orden}_{momento}.png"


def texto_compartir_recibo(venta: Venta) -> str:
    """Redacta el mensaje que acompaña la imagen del recibo.

    Args:
        venta: Orden abonada.

    Returns:
        Texto como «Hola Ana Pérez, adjunto tu recibo de abono.».
    """
    return f"Hola {venta.cliente_nombre}, adjunto tu recibo de abono."


def datos_recibo(bd: Session, abono: Abono) -> dict[str, object]:
    """Reúne los datos que muestran el recibo en pantalla y en la imagen.

    Args:
        bd: Sesión de base de datos.
        abono: Abono del recibo.

    Returns:
        Contexto para la plantilla `_recibo.html`, con el CSS de la aplicación.

    Raises:
        ValueError: Si la orden del abono ya no existe.
    """
    venta = bd.get(Venta, abono.id_venta)
    if venta is None:
        raise ValueError("La venta del abono no existe.")
    return {
        "abono": abono,
        "venta": venta,
        "abonos": comercial.abonos_de_venta(bd, venta.id_venta),
        "saldada": venta.saldo_pendiente <= 0,
        "css": RUTA_CSS_APLICACION.read_text(encoding="utf-8"),
        "nombre_archivo": nombre_archivo_recibo(venta, abono),
        "texto_compartir": texto_compartir_recibo(venta),
    }


def imagen_recibo(html: str) -> bytes:
    """Convierte el HTML de un recibo en una imagen PNG nítida (dos veces el tamaño).

    Args:
        html: Documento HTML con el recibo y sus estilos.

    Returns:
        Bytes del PNG, recortado a la tarjeta del recibo.

    Raises:
        ChromiumNoDisponible: Si el navegador de Playwright no está instalado.
    """
    from playwright.sync_api import Error as ErrorPlaywright
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch()
            try:
                pagina = navegador.new_page(
                    viewport={"width": 520, "height": 900}, device_scale_factor=2
                )
                pagina.set_content(html, wait_until="load")
                return pagina.locator(".recibo-captura").screenshot(type="png")
            finally:
                navegador.close()
    except ErrorPlaywright as error:
        raise ChromiumNoDisponible(
            "No se pudo generar la imagen: el navegador no está instalado. "
            "Ejecute «python -m playwright install chromium» en el servidor."
        ) from error
