"""Factura de OLB_BYTE: datos, logos, diseño compartido y conversión a PDF (ADR-36).

Responsabilidad
---------------
- Reunir los datos de la factura de una orden. La misma información alimenta la vista
  en pantalla, la vista previa, la descarga y el envío por WhatsApp, para que todas
  muestren exactamente la misma factura.
- Embeber los logos de `assets/` y el CSS del diseño como texto, para que el PDF no
  dependa de rutas ni de la red.
- Dar el nombre de archivo `Factura_OLB_BYTE_No_{numero}_{cliente}.png`.
- Entregar la hoja en HTML: el navegador la convierte en PNG (ADR-50).

Los datos fijos de la empresa (dirección, teléfono, cuenta bancaria, NIT) están en las
constantes de este módulo. El diseño visual vive en `static/css/factura-olb.css` y en
`templates/olb_byte/_hoja_factura.html`; ver `Guia.md` §10 para personalizarlos.
"""

from __future__ import annotations

import base64
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Venta, VentaDetalle
from app.servicios.comercial import ESTADO_ANULADA

RUTA_ASSETS = Path(__file__).resolve().parents[3] / "assets"
RUTA_CSS_FACTURA = Path(__file__).resolve().parents[1] / "static" / "css" / "factura-olb.css"

# La hoja Carta admite hasta diez productos; el diseño completa hasta nueve filas.
MAX_LINEAS_PDF = 10
FILAS_MINIMAS_TABLA = 9

NIT = "1151949473-3"
RESPONSABLE = "Esteban Lopez"
DIRECCION = "Calle 14F # 35-205"
TELEFONO = "316 382 63 66"
NEQUI = "316 382 63 66"
BANCO = {
    "nombre": "BBVA",
    "tipo": "Cuenta de ahorros",
    "cuenta": "0234307957",
    "telefono": "316 382 63 66",
}
PIE_LEGAL = "Documento generado por OLB BYTE. No reemplaza la factura electrónica ante la DIAN."

# Patrones de búsqueda de los logos. Se usan globs porque los nombres de `assets/`
# tienen tildes que cambian según el sistema de archivos.
PATRONES_LOGO = {
    "olb": "Nuevo Logo.png",
    "visa_mastercard": "*Mastercard*",
    "datafono": "*Datafono*",
    "nequi": "*Nequi*",
    "bre_b": "*bre-b*",
    # QR de Bre-B para el apoyo voluntario; no es un logo de la factura.
    "bre_b_qr": "Logo De Bre-B.png",
}


registro = logging.getLogger("app.factura")


def nombre_archivo(numero_orden: int, cliente: str) -> str:
    """Forma el nombre del PDF con el número de orden y el cliente sin tildes.

    Args:
        numero_orden: Consecutivo de la orden.
        cliente: Nombre del cliente tal como se guardó en la orden.

    Returns:
        Nombre como `Factura_OLB_BYTE_No_1_Ana_Perez.png`.
    """
    sin_tildes = unicodedata.normalize("NFKD", cliente).encode("ascii", "ignore").decode("ascii")
    cliente_limpio = re.sub(r"[^A-Za-z0-9]+", "_", sin_tildes).strip("_") or "Cliente"
    return f"Factura_OLB_BYTE_No_{numero_orden}_{cliente_limpio[:60]}.png"


@lru_cache(maxsize=None)
def logo_como_data_uri(clave: str) -> str:
    """Lee un logo de `assets/` y lo devuelve como data URI.

    El resultado se guarda en caché: los logos no cambian durante la ejecución, y así
    no se vuelve a leer ni a codificar un PNG pesado en cada factura. Tras cambiar un
    logo, reinicia el servidor.

    Args:
        clave: Clave de `PATRONES_LOGO`.

    Returns:
        Data URI PNG, o cadena vacía si el archivo no existe. Sin logo la factura
        sigue saliendo; solo falta la imagen.
    """
    archivo = next(RUTA_ASSETS.glob(PATRONES_LOGO[clave]), None) if RUTA_ASSETS.exists() else None
    if archivo is None:
        # Sin logo la factura sale sin imagen; el aviso en el log ayuda a ver en Render
        # si `assets/` no llegó al servidor.
        registro.warning("No se encontró el logo %s en %s", clave, RUTA_ASSETS)
        return ""
    datos = base64.b64encode(archivo.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{datos}"


def datos_factura(bd: Session, venta: Venta, validar_maximo: bool = True) -> dict[str, object]:
    """Reúne los datos que muestran la factura en pantalla y en el PDF.

    Args:
        bd: Sesión de base de datos.
        venta: Orden facturada.
        validar_maximo: Si es verdadero, rechaza órdenes que no caben en una página PDF.

    Returns:
        Contexto compartido: líneas, filas de relleno, totales, datos de la empresa,
        logos, CSS del diseño y nombre del archivo.

    Raises:
        ValueError: Si la orden tiene más líneas de las que caben en una página.
    """
    detalles = list(
        bd.scalars(select(VentaDetalle).where(VentaDetalle.id_venta == venta.id_venta))
    )
    if validar_maximo and len(detalles) > MAX_LINEAS_PDF:
        raise ValueError(
            f"La factura admite hasta {MAX_LINEAS_PDF} productos. "
            "Divide la venta en dos órdenes para imprimirla."
        )
    lineas = [
        {
            "nombre": detalle.producto_nombre,
            "categoria": detalle.categoria or "",
            "cantidad": detalle.cantidad,
            "precio": detalle.precio_unitario,
            "subtotal": detalle.subtotal_item,
            "garantia": detalle.garantia_texto or "",
        }
        for detalle in detalles
    ]
    return {
        "venta": venta,
        "anulada": venta.estado_orden == ESTADO_ANULADA,
        "lineas": lineas,
        "filas_vacias": range(max(FILAS_MINIMAS_TABLA - len(lineas), 0)),
        "nit": NIT,
        "responsable": RESPONSABLE,
        "direccion": DIRECCION,
        "telefono": TELEFONO,
        "nequi": NEQUI,
        "banco": BANCO,
        "pie_legal": PIE_LEGAL,
        "logos": {clave: logo_como_data_uri(clave) for clave in PATRONES_LOGO},
        "css": RUTA_CSS_FACTURA.read_text(encoding="utf-8"),
        "nombre_archivo": nombre_archivo(venta.numero_orden, venta.cliente_nombre),
    }
