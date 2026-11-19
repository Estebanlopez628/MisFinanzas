"""Pruebas del recibo de abono como imagen PNG para compartir (RF-07).

Usan Chromium real de Playwright, por eso tardan un poco más. Cubren el formato PNG,
el nombre del archivo, el mensaje que acompaña la imagen, el control de acceso y el
caso en que el navegador no está instalado.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.servicios import comercial, factura_pdf, recibo_imagen


def _abono(bd):
    """Crea una venta con un abono de 20.000 y devuelve el abono.

    Args:
        bd: Sesión de base de datos.

    Returns:
        El abono registrado.
    """
    venta = comercial.registrar_venta(
        bd,
        "Ana Pérez",
        "3001234567",
        [comercial.LineaVenta(nombre="Audífonos BT", cantidad=1, precio_unitario="50000", costo_unitario="30000")],
    )
    return comercial.registrar_abono(bd, venta.id_venta, "20000", "TRANSFERENCIA")


def test_imagen_del_recibo_es_png_con_nombre_de_archivo(cliente_admin: TestClient, bd) -> None:
    """La imagen es un PNG y se descarga con el nombre del recibo."""
    abono = _abono(bd)

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}/imagen")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/png"
    assert respuesta.content.startswith(b"\x89PNG")
    assert 'attachment; filename="Recibo_OLB_BYTE_No_1_' in respuesta.headers["content-disposition"]


def test_vista_del_recibo_se_muestra_en_linea(cliente_admin: TestClient, bd) -> None:
    """Con descargar=0 la imagen se muestra en línea."""
    abono = _abono(bd)

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}/imagen", params={"descargar": 0})

    assert respuesta.headers["content-disposition"].startswith("inline")


def test_pagina_del_recibo_ofrece_compartir_la_imagen(cliente_admin: TestClient, bd) -> None:
    """El botón Compartir apunta a la imagen y lleva el mensaje con el nombre del cliente."""
    abono = _abono(bd)

    texto = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}").text

    assert f"/olb-byte/recibos/{abono.id_abono}/imagen" in texto
    assert 'data-texto="Hola Ana Pérez, adjunto tu recibo de abono."' in texto
    assert "data-compartir" in texto


def test_imagen_de_recibo_inexistente_devuelve_404(cliente_admin: TestClient) -> None:
    """Un recibo que no existe responde 404."""
    assert cliente_admin.get("/olb-byte/recibos/no-existe/imagen").status_code == 404


def test_usuario_publico_no_descarga_recibos(cliente_usuario: TestClient, bd) -> None:
    """La imagen del recibo exige administrador."""
    abono = _abono(bd)

    assert cliente_usuario.get(f"/olb-byte/recibos/{abono.id_abono}/imagen").status_code == 403


def test_sin_chromium_la_imagen_responde_503(
    cliente_admin: TestClient, bd, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el navegador no está instalado, se explica cómo instalarlo."""
    abono = _abono(bd)

    def sin_navegador(_html: str) -> bytes:
        raise factura_pdf.ChromiumNoDisponible("No se pudo generar la imagen: playwright install chromium")

    monkeypatch.setattr(recibo_imagen, "imagen_recibo", sin_navegador)

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}/imagen")

    assert respuesta.status_code == 503
    assert "playwright install chromium" in respuesta.text

def test_css_del_recibo_llega_sin_escapar(bd) -> None:
    """El CSS se incrusta tal cual: sin escapar, el navegador lo ignoraría y el recibo saldría sin estilo."""
    from app.routers.vistas import plantillas

    abono = _abono(bd)
    html = plantillas.get_template("olb_byte/recibo_imagen.html").render(recibo_imagen.datos_recibo(bd, abono))

    assert ".recibo__datos > div" in html
    assert "&gt;" not in html
    assert "&quot;" not in html
