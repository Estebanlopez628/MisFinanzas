"""Pruebas de la SRS v4.5, bloque 3 (velocímetros solo en escritorio)."""

from __future__ import annotations

from pathlib import Path

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def test_base_movil_permanece_intacta() -> None:
    """Los estilos en línea siguen siendo los de la línea base v4.4."""
    html = (RUTA_APP / "templates/presupuesto/index.html").read_text(encoding="utf-8")

    assert "max-width: 540px" in html
    assert html.count('style="width: 120px; height: 68px; flex-shrink: 0;"') == 2
    assert html.count('width="120" height="68"') == 2
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in html


def test_escritorio_amplia_velocimetros_sin_apilarlos() -> None:
    """El media query de 768 px usa 640 px y SVG de 156×88."""
    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("@media (min-width: 768px) {", css.index(".cierre-deuda"))
    bloque = css[inicio : inicio + 1000]

    assert "max-width: 640px !important" in bloque
    assert "gap: 20px !important" in bloque
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important" in bloque
    assert "width: 156px !important" in bloque
    assert "height: 88px !important" in bloque


def test_no_hay_regla_de_156px_fuera_del_media_query() -> None:
    """La ampliación no puede filtrarse a la vista móvil."""
    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("@media (min-width: 768px) {", css.index(".cierre-deuda"))
    assert "width: 156px !important" not in css[:inicio]
    assert "width: 156px !important" in css[inicio:]
