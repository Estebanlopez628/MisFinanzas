"""Pruebas del botón de número en Registrar venta (SRS v4.44, solo móvil)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_boton_tiene_rotulos_por_ancho() -> None:
    """Escritorio dice «Pegar número» y móvil «Agregar Numero»."""
    plantilla = (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")
    bloque = plantilla.split("data-pegar-numero>", 1)[1].split("</button>", 1)[0]
    assert "Pegar número" in bloque
    assert "Agregar Numero" in bloque

    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert ".texto-escritorio {\n    display: none;\n  }" in css
    assert ".texto-movil {\n    display: inline;\n  }" in css


def test_js_abre_contactos_limpia_y_tiene_respaldo() -> None:
    """El botón usa Contact Picker en móvil y deja el portapapeles en web."""
    js = (RUTA / "static/js/olb_byte.js").read_text(encoding="utf-8")
    bloque = js[js.index("function agregarNumeroMovil()") : js.index("if (botonPegar)")]
    assert "navigator.contacts" in bloque
    assert ".select([\"tel\"], { multiple: false })" in bloque
    assert "normalizarTelefono(numeroContacto)" in bloque
    assert "length !== 10" in bloque
    assert "campoTelefono.focus()" in bloque
    assert "no abre la libreta de contactos" in bloque
    assert 'window.matchMedia("(max-width: 767px)").matches' in bloque
    assert "pegarNumero();" in bloque
    # La limpieza quita +57 y caracteres no numéricos.
    normalizar = js.split("function normalizarTelefono(texto) {", 1)[1].split("}", 1)[0]
    assert "replace(/\\D/g" in normalizar
    assert "digitos.slice(2)" in normalizar


def test_vista_de_ventas_muestra_ambos_rotulos(cliente_admin: TestClient) -> None:
    """La plantilla renderiza el botón sin romper el formulario de venta."""
    respuesta = cliente_admin.get("/olb-byte")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "data-pegar-numero" in html
    assert "Pegar número" in html
    assert "Agregar Numero" in html
