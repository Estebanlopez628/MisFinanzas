"""Pruebas del botón de número en Registrar venta (SRS v4.44, solo móvil)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA = Path(__file__).resolve().parent.parent / "app"


def plantilla_leida() -> str:
    """Lee la plantilla de ventas.

    Returns:
        Contenido de `index.html`.
    """
    return (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")


def test_boton_tiene_un_solo_rotulo() -> None:
    """El DOM trae solo «Agregar Numero»; el escritorio lo cambia por JS."""
    plantilla = (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")
    bloque = plantilla.split("data-pegar-numero>", 1)[1].split("</button>", 1)[0]
    assert "Agregar Numero" in bloque
    assert "Pegar número" not in bloque
    assert "data-rotulo-numero" in bloque


def test_js_rotulo_y_contactos_con_respaldo() -> None:
    """Un solo rótulo por ancho, Contact Picker y fallback sin errores."""
    js = (RUTA / "static/js/olb_byte.js").read_text(encoding="utf-8")
    rotulo = js[js.index("function sincronizarRotuloNumero()") : js.index("if (botonPegar)")]
    assert 'window.matchMedia("(max-width: 767px)").matches' in rotulo
    assert '"Agregar Numero"' in rotulo and '"Pegar número"' in rotulo
    bloque = js[js.index("function avisarFalloNumero(") : js.index("function manejarBotonNumero()")]
    assert "navigator.contacts.select" in bloque
    assert "try {" in bloque and "Promise.resolve" in bloque
    assert "nota-contactos--aviso" in js
    assert "data-nota-contactos-texto" in plantilla_leida()
    assert "data-pegar-portapapeles" in plantilla_leida()
    assert 'window.location.href = "whatsapp://"' in js
    assert "campoTelefono.focus()" not in bloque
    normalizar = js.split("function normalizarTelefono(texto) {", 1)[1].split("}", 1)[0]
    assert "replace(/\\D/g" in normalizar
    assert "digitos.slice(2)" in normalizar


def test_vista_de_ventas_muestra_un_solo_rotulo(cliente_admin: TestClient) -> None:
    """La plantilla no renderiza el rótulo de escritorio en el móvil."""
    respuesta = cliente_admin.get("/olb-byte")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "data-pegar-numero" in html
    rotulo = html.split("data-pegar-numero>", 1)[1].split("</button>", 1)[0]
    assert "Agregar Numero" in rotulo
    assert "Pegar número" not in rotulo
    # El rótulo «Pegar número» solo existe en el botón de respaldo del aviso.
    assert "data-pegar-portapapeles>Pegar número</button>" in html
