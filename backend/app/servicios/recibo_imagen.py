"""Recibo de abono de OLB_BYTE como imagen PNG para compartir por WhatsApp (RF-07).

Responsabilidad
---------------
- Reunir los datos del recibo de un abono (orden, abonos y saldo).
- Dibujar el recibo con la misma tarjeta de la pantalla (`_recibo.html`) y el CSS
- Dar el nombre del archivo y el mensaje que acompaña la imagen.

"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.modelos import Abono, Venta
from app.servicios import comercial

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
