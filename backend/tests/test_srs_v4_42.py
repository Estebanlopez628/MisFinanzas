"""Pruebas de la SRS v4.42: Deep Links, scroll de tabla y tarjetas móviles."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.servicios.chancucos import _validar_url

RUTA = Path(__file__).resolve().parent.parent / "app"


@pytest.mark.parametrize(
    "url",
    (
        "https://pagos.entidad.com/abc",
        "http://pagos.entidad.com",
        "daviplata://pagar/10948271",
        "nequi://pago?ref=123",
        "bancolombia://app/pagos",
    ),
)
def test_validar_url_acepta_web_y_deep_links(url: str) -> None:
    """Se aceptan pasarelas web y esquemas nativos de aplicaciones."""
    assert _validar_url(url) == url


@pytest.mark.parametrize(
    "url",
    ("javascript://alerta", "data://texto", "daviplata:pago", "ftp:/sin-barras"),
)
def test_validar_url_rechaza_esquemas_invalidos(url: str) -> None:
    """No se guardan enlaces que no sean web ni Deep Links con ://."""
    with pytest.raises(ValueError):
        _validar_url(url)


def test_formulario_acepta_deep_links() -> None:
    """Los dos campos de URL son texto, con teclado de URL y mismo placeholder."""
    chancucos = (RUTA / "templates/chancucos/index.html").read_text(encoding="utf-8")
    assert chancucos.count('type="text" inputmode="url" name="url_pago"') == 2
    assert chancucos.count('placeholder="https://... o daviplata://"') == 2
    assert chancucos.count("data-url-pago") == 2


def test_tarjeta_movil_sin_modal() -> None:
    """Mis Finanzas usa tarjetas directas en móvil y conserva la vista web."""
    finanzas = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    assert "atajo-tarjeta-movil__cabecera" in finanzas
    assert "atajo-tarjeta-movil__dias" in finanzas
    assert "Pagar los días:" in finanzas
    assert "atajo-tarjeta-movil__acciones" in finanzas
    assert 'data-pagar-atajo data-url="{{ item.url_pago }}"' in finanzas
    assert "atajo-web" in finanzas
    assert "data-atajo-fila" not in finanzas
    assert "atajo-finanzas-modal" not in finanzas


def test_scroll_horizontal_en_tabla_de_atajos() -> None:
    """La tabla móvil se desplaza y conserva las cabeceras en dos líneas."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index(".tabla-contenedor--atajos {", css.index("@media (max-width: 767px)"))
    bloque = css[inicio : css.index("}", inicio)]
    assert "overflow-x: auto" in bloque
    assert "min-width: 440px" in css
    chancucos = (RUTA / "templates/chancucos/index.html").read_text(encoding="utf-8")
    assert "Valor a<br />Pagar" in chancucos
    assert "Días de<br />Pago" in chancucos


def test_apertura_inteligente_en_js() -> None:
    """Web abre pestaña nueva; los Deep Links usan `location.href`."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    inicio = js.index("/* SRS v4.42: Deep Links nativos")
    bloque = js[inicio : js.index("// ------------------- Login", inicio)]
    assert "REGEX_URL_PAGO" in bloque
    assert 'window.open(url, "_blank", "noopener,noreferrer")' in bloque
    assert "window.location.href = url" in bloque
