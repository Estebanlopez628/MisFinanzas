"""WhatsApp de la factura y avisos de logos (SRS v1.8, ajuste de factura)."""

from __future__ import annotations

import logging
from datetime import datetime

from app.servicios import comercial, factura_pdf


def _producto() -> list[comercial.LineaVenta]:
    """Devuelve un producto de prueba.

    Returns:
        Lista con una línea de venta.
    """
    return [
        comercial.LineaVenta(
            nombre="Audífonos", categoria="Audio", cantidad=1, precio_unitario="50000", costo_unitario="30000"
        )
    ]


def test_orden_con_celular_abre_el_chat_del_cliente(cliente_admin, bd) -> None:
    """El botón de WhatsApp apunta al número del cliente y no marca la orden como sin celular."""
    venta = comercial.registrar_venta(
        bd, "Ana Pérez", "3001234567", _producto(), datetime(2026, 11, 10, 15, tzinfo=comercial.ZONA_TIENDA)
    )

    html = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}").text

    assert "https://wa.me/573001234567?text=" in html
    assert "data-sin-celular" not in html


def test_orden_sin_celular_se_marca_para_avisar(cliente_admin, bd) -> None:
    """Sin celular del cliente el botón lo marca para mostrar el aviso en pantalla."""
    venta = comercial.registrar_venta(
        bd, "Luis Gómez", None, _producto(), datetime(2026, 11, 11, 15, tzinfo=comercial.ZONA_TIENDA)
    )

    html = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}").text

    assert "data-sin-celular" in html


def test_logo_faltante_queda_en_el_registro(monkeypatch, tmp_path, caplog) -> None:
    """Si `assets/` no llega al servidor, el log lo dice en vez de fallar en silencio."""
    monkeypatch.setattr(factura_pdf, "RUTA_ASSETS", tmp_path / "no-existe")
    factura_pdf.logo_como_data_uri.cache_clear()
    try:
        with caplog.at_level(logging.WARNING, logger="app.factura"):
            resultado = factura_pdf.logo_como_data_uri("olb")
    finally:
        factura_pdf.logo_como_data_uri.cache_clear()

    assert resultado == ""
    assert "No se encontró el logo olb" in caplog.text
