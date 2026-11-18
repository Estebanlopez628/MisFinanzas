"""Factura PDF de OLB_BYTE: datos, logos y conversión a PDF con Chromium (ADR-36).

Responsabilidad
---------------
- Reunir los datos de la factura de una orden: líneas, totales, saldo, garantía,
  nota del vendedor y medios de pago (RF-18 y sección 4 del SRS).
- Embeber los logos de `assets/` como data URI para que el PDF no dependa de rutas
  externas ni de la red.
- Dar el nombre de archivo `Factura_OLB_BYTE_No_{numero}_{cliente}.pdf`.
- Convertir el HTML ya renderizado en PDF tamaño Carta con Playwright.

El HTML lo renderiza el router con la plantilla `olb_byte/factura_pdf.html`; este
módulo no conoce HTTP.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Venta, VentaDetalle
from app.servicios.comercial import ESTADO_ANULADA

RUTA_ASSETS = Path(__file__).resolve().parents[3] / "assets"

# La plantilla de Carta tiene diez filas de producto; con más líneas la factura no
# cabe en una sola página, que es un requisito del SRS (RF-18).
MAX_LINEAS_PDF = 10
NOTA_VENDEDOR = "Gracias por apoyar nuestro emprendimiento tecnológico"
NEQUI = "316 382 63 66"
NIT = "1151949473-3"
RESPONSABLE = "Esteban Lopez"

# Patrones de búsqueda de los logos. Se usan globs y no nombres exactos porque los
# nombres de `assets/` tienen tildes que cambian según el sistema de archivos.
PATRONES_LOGO = {
    "olb": "*Logotipo OLB*",
    "visa_mastercard": "*Mastercard*",
    "datafono": "*Datafono*",
    "nequi": "*Nequi*",
    "bre_b": "*bre-b*",
}


def nombre_archivo(numero_orden: int, cliente: str) -> str:
    """Forma el nombre del PDF con el número de orden y el cliente sin tildes.

    Args:
        numero_orden: Consecutivo de la orden.
        cliente: Nombre del cliente tal como se guardó en la orden.

    Returns:
        Nombre como `Factura_OLB_BYTE_No_1_Ana_Perez.pdf`.
    """
    sin_tildes = unicodedata.normalize("NFKD", cliente).encode("ascii", "ignore").decode("ascii")
    cliente_limpio = re.sub(r"[^A-Za-z0-9]+", "_", sin_tildes).strip("_") or "Cliente"
    return f"Factura_OLB_BYTE_No_{numero_orden}_{cliente_limpio[:60]}.pdf"


def logo_como_data_uri(clave: str) -> str:
    """Lee un logo de `assets/` y lo devuelve como data URI.

    Args:
        clave: Clave de `PATRONES_LOGO`.

    Returns:
        Data URI PNG, o cadena vacía si el archivo no existe. Sin logo la factura
        sigue saliendo; solo falta la imagen.
    """
    archivo = next(RUTA_ASSETS.glob(PATRONES_LOGO[clave]), None) if RUTA_ASSETS.exists() else None
    if archivo is None:
        return ""
    datos = base64.b64encode(archivo.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{datos}"


def datos_factura(bd: Session, venta: Venta) -> dict[str, object]:
    """Reúne los datos que muestra la factura PDF.

    Args:
        bd: Sesión de base de datos.
        venta: Orden facturada.

    Returns:
        Contexto para la plantilla: líneas, filas vacías para completar la tabla,
        totales, garantía, logos, nota, medios de pago y nombre del archivo.

    Raises:
        ValueError: Si la orden tiene más líneas de las que caben en una página.
    """
    detalles = list(
        bd.scalars(select(VentaDetalle).where(VentaDetalle.id_venta == venta.id_venta))
    )
    if len(detalles) > MAX_LINEAS_PDF:
        raise ValueError(
            f"La factura en PDF admite hasta {MAX_LINEAS_PDF} productos. "
            "Divide la venta en dos órdenes para imprimirla."
        )
    lineas = [
        {
            "nombre": detalle.producto_nombre,
            "referencia": detalle.referencia or "—",
            "cantidad": detalle.cantidad,
            "precio": detalle.precio_unitario,
            "subtotal": detalle.subtotal_item,
            "garantia": detalle.garantia_texto or "—",
        }
        for detalle in detalles
    ]
    return {
        "venta": venta,
        "anulada": venta.estado_orden == ESTADO_ANULADA,
        "lineas": lineas,
        "filas_vacias": range(MAX_LINEAS_PDF - len(lineas)),
        "garantia_vence": venta.garantia_fecha_fin,
        "nota": NOTA_VENDEDOR,
        "nit": NIT,
        "responsable": RESPONSABLE,
        "nequi": NEQUI,
        "logos": {clave: logo_como_data_uri(clave) for clave in PATRONES_LOGO},
        "nombre_archivo": nombre_archivo(venta.numero_orden, venta.cliente_nombre),
    }


class ChromiumNoDisponible(RuntimeError):
    """Se lanza cuando Playwright no encuentra el navegador instalado."""


def generar_pdf(html: str) -> bytes:
    """Convierte HTML en un PDF tamaño Carta con una sola página por factura.

    Usa `printBackground=True` para que se vean la cabecera, el efecto cebra y los
    logos (RF-18). Abre un navegador por petición: es lento, pero sencillo y sin
    estado compartido entre peticiones.

    Args:
        html: Documento HTML completo con estilos y logos embebidos.

    Returns:
        Bytes del PDF.

    Raises:
        ChromiumNoDisponible: Si el navegador de Playwright no está instalado.
    """
    from playwright.sync_api import Error as ErrorPlaywright
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch()
            try:
                pagina = navegador.new_page()
                pagina.set_content(html, wait_until="load")
                return pagina.pdf(
                    format="Letter",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    prefer_css_page_size=True,
                )
            finally:
                navegador.close()
    except ErrorPlaywright as error:
        raise ChromiumNoDisponible(
            "No se pudo generar el PDF: el navegador no está instalado. "
            "Ejecute «python -m playwright install chromium» en el servidor."
        ) from error
