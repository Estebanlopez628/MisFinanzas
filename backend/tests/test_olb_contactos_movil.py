"""Pruebas del botón de número en Registrar venta (solo móvil abre WhatsApp)."""

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


def javascript_leido() -> str:
    """Lee el JavaScript de OLB_BYTE.

    Returns:
        Contenido de `olb_byte.js`.
    """
    return (RUTA / "static/js/olb_byte.js").read_text(encoding="utf-8")


def test_boton_tiene_un_solo_rotulo() -> None:
    """El DOM trae solo «Agregar Numero»; el escritorio lo cambia por JS."""
    bloque = plantilla_leida().split("data-pegar-numero>", 1)[1].split("</button>", 1)[0]
    assert "Agregar Numero" in bloque
    assert "Pegar número" not in bloque
    assert "data-rotulo-numero" in bloque


def test_movil_abre_whatsapp_y_el_campo_limpia_lo_pegado() -> None:
    """El botón móvil abre WhatsApp y el campo quita espacios e indicativo al pegar."""
    js = javascript_leido()
    movil = js.split("function agregarNumeroMovil() {", 1)[1].split("}", 1)[0]
    assert 'window.location.href = "whatsapp://"' in movil
    assert "navigator.contacts.select" not in js
    assert "data-elegir-contacto" not in js
    assert "data-abrir-whatsapp" not in js
    assert "data-pegar-portapapeles" not in js
    assert 'campoTelefono.addEventListener("input"' in js
    normalizar = js.split("function normalizarTelefono(texto) {", 1)[1].split("}", 1)[0]
    assert "replace(/\\D/g" in normalizar
    assert "digitos.slice(2)" in normalizar


def test_rotulo_de_escritorio_sigue_siendo_portapapeles() -> None:
    """El mismo botón dice «Pegar número» en web y conserva el portapapeles."""
    js = javascript_leido()
    rotulo = js[js.index("function sincronizarRotuloNumero()") : js.index("if (botonPegar)")]
    assert 'window.matchMedia("(max-width: 767px)").matches' in rotulo
    assert '"Agregar Numero"' in rotulo and '"Pegar número"' in rotulo
    manejar = js[js.index("function manejarBotonNumero()") : js.index("var rotuloNumero")]
    assert "agregarNumeroMovil()" in manejar
    assert "pegarNumero()" in manejar


def test_vista_de_ventas_no_renderiza_los_controles_del_aviso(cliente_admin: TestClient) -> None:
    """La plantilla no ofrece Elegir contacto ni botones de respaldo."""
    respuesta = cliente_admin.get("/olb-byte")
    assert respuesta.status_code == 200
    html = respuesta.text
    rotulo = html.split("data-pegar-numero>", 1)[1].split("</button>", 1)[0]
    assert "Agregar Numero" in rotulo
    assert "Pegar número" not in html
    assert "data-elegir-contacto" not in html
    assert "data-abrir-whatsapp" not in html
    assert "data-pegar-portapapeles" not in html
    assert "data-nota-contactos-texto" in html
