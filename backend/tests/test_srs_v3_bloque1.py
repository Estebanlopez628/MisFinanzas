"""Pruebas de la SRS v3.0, bloque 1 (retorno de deudas y WhatsApp directo)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, usuarios

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_enlace_de_retorno_persiste_tras_guardar(cliente_admin: TestClient) -> None:
    """El redirect conserva `volver` y el enlace sigue visible tras guardar."""
    respuesta = cliente_admin.post(
        "/deudas",
        data={
            "acreedor": "Banco Retorno",
            "saldo_total": "1.200.000",
            "cuota": "100.000",
            "cuotas_pendientes": "12",
            "periodicidad": "MENSUAL",
            "volver": "finanzas",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert "volver=finanzas" in respuesta.headers["location"]

    html = cliente_admin.get(respuesta.headers["location"]).text
    assert "Volver a Gastos Fijos - Finanzas para completar el registro" in html
    assert "data-volver-origen" in html


def test_enlace_de_retorno_es_texto_y_esta_bajo_el_formulario(
    cliente_admin: TestClient,
) -> None:
    """No es un botón pesado ni aparece sobre el título de la página."""
    html = cliente_admin.get("/deudas?volver=deducciones").text

    titulo = html.find("Registro y Detalles de deudas")
    formulario = html.find('name="acreedor"')
    enlace = html.find("data-volver-origen")
    assert titulo < formulario < enlace

    trozo = html[enlace - 120 : enlace + 220]
    assert 'class="enlace"' in trozo
    assert 'class="boton' not in trozo
    assert "banner-volver-deuda" not in html


def test_clave_de_session_storage_no_se_borra_en_deudas() -> None:
    """La clave vive hasta que el formulario de origen restaura sus datos."""
    js_deudas = (RUTA_APP / "static/js/deudas.js").read_text(encoding="utf-8")
    js_categorias = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")

    assert "misfinanzas_pending_debt_link" in js_deudas
    assert 'removeItem("misfinanzas_pending_debt_link")' not in js_deudas
    assert "sessionStorage.removeItem(CLAVE_PENDIENTE)" in js_categorias


def test_whatsapp_directo_sin_selector_de_aplicaciones() -> None:
    """Los tres botones abren el chat con número; no hay Web Share API."""
    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")

    assert "navigator.share" not in js
    assert "compartirArchivo" not in js
    assert 'var numero = numeroDelEnlace(whatsapp);' in js
    assert '"https://wa.me/" + numero + "?text=" + encodeURIComponent(texto)' in js
    assert 'window.open(enlaceDirecto, "_blank", "noopener,noreferrer")' in js
    assert "window.location.href = enlaceDirecto" not in js

    # Los tres puntos comparten el mismo manejador.
    assert '[data-compartir], [data-compartir-factura]' in js
    plantillas = RUTA_APP / "templates/olb_byte"
    assert "data-compartir" in (plantillas / "factura.html").read_text(encoding="utf-8")
    assert "data-compartir" in (plantillas / "recibo.html").read_text(encoding="utf-8")
    assert "data-compartir-factura" in (plantillas / "index.html").read_text(encoding="utf-8")


def test_mensaje_de_factura_no_cambia(cliente_admin: TestClient, bd) -> None:
    """El texto precargado sigue siendo el aprobado."""
    from datetime import datetime

    from app.servicios import comercial

    venta = comercial.registrar_venta(
        bd,
        "Ana Pérez",
        "3001234567",
        [
            comercial.LineaVenta(
                nombre="Audífonos",
                categoria="Audio",
                cantidad=1,
                precio_unitario="50000",
                costo_unitario="30000",
            )
        ],
        datetime(2026, 11, 10, 15, tzinfo=comercial.ZONA_TIENDA),
    )
    html = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}").text
    assert 'data-texto="Hola Ana Pérez, adjunto tu factura de compra."' in html
