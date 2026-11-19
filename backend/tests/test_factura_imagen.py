"""Factura y recibo como imagen PNG generada en el navegador (ADR-50).

El servidor entrega la hoja en HTML y el navegador la convierte en PNG. Estas pruebas
cubren las hojas, los permisos, los logos embebidos y que ya no se genera PDF en el
servidor.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.servicios import comercial, factura_pdf


def _venta(bd, lineas: int = 2, nombre: str = "Ana Pérez"):
    """Registra una orden con el número de productos indicado.

    Args:
        bd: Sesión de base de datos.
        lineas: Número de productos distintos.
        nombre: Cliente.

    Returns:
        La orden persistida.
    """
    fecha = datetime(2026, 11, 10, 15, 0, tzinfo=comercial.ZONA_TIENDA)
    productos = [
        comercial.LineaVenta(
            nombre=f"Producto {indice}",
            categoria=f"CAT-{indice}",
            cantidad=1,
            precio_unitario="50000",
            costo_unitario="30000",
        )
        for indice in range(lineas)
    ]
    return comercial.registrar_venta(bd, nombre, "3001234567", productos, fecha)


def test_nombre_de_archivo_es_png() -> None:
    """La imagen de la factura se llama .png y conserva el número y el cliente."""
    assert factura_pdf.nombre_archivo(1, "Ana Pérez") == "Factura_OLB_BYTE_No_1_Ana_Perez.png"


def test_logos_se_embeben_como_data_uri() -> None:
    """Los logos viajan dentro del HTML, así la imagen no depende de la red."""
    for clave in factura_pdf.PATRONES_LOGO:
        assert factura_pdf.logo_como_data_uri(clave).startswith("data:image/png;base64,"), clave


def test_datos_factura_rechaza_mas_de_diez_productos(bd) -> None:
    """Una factura con más de diez productos no cabe en una hoja y se rechaza."""
    venta = _venta(bd, lineas=11)

    with pytest.raises(ValueError, match="hasta 10 productos"):
        factura_pdf.datos_factura(bd, venta)


def test_hoja_de_la_factura_lista_para_capturar(cliente_admin, bd) -> None:
    """La hoja trae sus estilos y el contenedor que se convierte en imagen."""
    venta = _venta(bd, lineas=2)

    respuesta = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}/hoja")

    assert respuesta.status_code == 200
    assert "factura-imprimible" in respuesta.text
    assert "<style>" in respuesta.text


def test_hoja_bloqueada_para_correos_no_autorizados(cliente_usuario, bd) -> None:
    """Un usuario que no está autorizado no puede pedir la hoja."""
    venta = _venta(bd, lineas=1)

    assert cliente_usuario.get(f"/olb-byte/factura/{venta.id_venta}/hoja").status_code == 403


def test_hoja_de_orden_inexistente_da_404(cliente_admin) -> None:
    """Una orden que no existe responde 404."""
    assert cliente_admin.get("/olb-byte/factura/no-existe/hoja").status_code == 404


def test_hoja_del_recibo_lista_para_capturar(cliente_admin, bd) -> None:
    """La tarjeta del recibo se entrega para convertirla en imagen."""
    venta = _venta(bd, lineas=1)
    abono = comercial.registrar_abono(bd, venta.id_venta, "10000")

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}/hoja")

    assert respuesta.status_code == 200
    assert "recibo" in respuesta.text


def test_pagina_de_factura_ofrece_imagen_y_no_pdf(cliente_admin, bd) -> None:
    """La factura ofrece descargar la imagen y compartirla; ya no enlaza PDF."""
    venta = _venta(bd, lineas=1)

    html = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}").text

    assert "Descargar imagen" in html
    assert "Compartir por WhatsApp" in html
    assert "/pdf" not in html
    assert "vendor/html-to-image.js" in html


def test_el_servidor_ya_no_genera_pdf() -> None:
    """Chromium y Playwright salieron del servidor: no hay generador de PDF."""
    assert not hasattr(factura_pdf, "generar_pdf")
    assert not hasattr(factura_pdf, "ChromiumNoDisponible")
