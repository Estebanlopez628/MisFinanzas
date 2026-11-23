"""Pruebas de la SRS v4.17 (velocímetros cockpit conservando tamaños)."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_tamanos_vigentes_no_cambian() -> None:
    """El SVG sigue con 120x68 en la plantilla y 156x88 en escritorio."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert html.count('width="120" height="68"') == 2
    assert html.count("width: 120px; height: 68px; flex-shrink: 0;") == 2
    assert "max-width: 540px" in html

    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("@media (min-width: 768px) {", css.index(".cierre-deuda__meses"))
    bloque = css[inicio : inicio + 1200]
    assert "width: 156px !important" in bloque
    assert "height: 88px !important" in bloque


def test_dial_cockpit_y_variantes() -> None:
    """El dial radial, las marcas y el resplandor están en la plantilla."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert html.count('class="mf-cockpit-dial"') == 2
    assert html.count('viewBox="0 0 240 138"') == 2
    assert html.count('class="mf-dial-ticks"') == 2
    assert html.count('class="mf-dial-progress"') == 2
    assert html.count('class="mf-needle-blade"') == 2
    assert html.count('class="mf-needle-hub-outer"') == 2
    assert 'data-variant="minimo"' in html
    assert 'data-variant="excedente"' in html
    assert "mfArcBlue" in html and "mfGlowBlue" in html
    assert "mfArcGreen" in html and "mfGlowGreen" in html


def test_jerarquia_de_texto_centrado() -> None:
    """Título, fecha, meses, píldora y línea inferior en cada velocímetro."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert html.count('class="mf-gauge-meta"') == 2
    assert html.count('class="mf-gauge-title"') == 2
    assert html.count('class="mf-gauge-date"') == 2
    assert html.count('class="mf-gauge-months"') == 2
    assert html.count('class="mf-gauge-badge"') == 1
    assert html.count('class="mf-gauge-sub"') == 2
    assert "Pago mínimo" in html and "Con excedente" in html
    assert "Sin abono extra" in html
    assert "Abonando +" in html
    assert "meses antes" in html


def test_estilos_por_variante() -> None:
    """Azul en mínimo, esmeralda en excedente, sin reglas de tamaño nuevas."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert 'data-variant="minimo"] .mf-dial-progress' in css
    assert 'data-variant="excedente"] .mf-dial-progress' in css
    assert "stroke: url(#mfArcBlue)" in css
    assert "stroke: url(#mfArcGreen)" in css
    assert "filter: url(#mfGlowBlue)" in css
    assert "filter: url(#mfGlowGreen)" in css
    assert ".mf-gauge-badge" in css
    assert ".mf-gauge-sub" in css


def test_js_genera_las_marcas() -> None:
    """Las 41 micro-marcas se generan una sola vez por dial."""
    js = (RUTA / "static/js/consejero.js").read_text(encoding="utf-8")
    assert ".mf-cockpit-dial" in js
    assert ".mf-dial-ticks" in js
    assert "childElementCount > 0" in js
    assert "createElementNS" in js
    assert "var total = 41" in js
