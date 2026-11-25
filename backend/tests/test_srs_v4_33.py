"""Pruebas de la SRS v4.33: distribución exacta del atajo de pago."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_macro_comparte_tarjeta_y_modal() -> None:
    """El mismo fragmento se usa en la tarjeta web y en el modal móvil."""
    html = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")

    inicio = html.index("{% macro atajo_detalle(item)")
    fin = html.index("{%- endmacro %}", inicio)
    macro = html[inicio:fin]

    for texto in ("Fecha pago:", "REF:", "Valor a Pagar:", "Copiar", "Pagar"):
        assert texto in macro
    assert macro.index("Fecha pago:") < macro.index("REF:")
    assert macro.index("REF:") < macro.index("Valor a Pagar:")
    assert macro.index("Valor a Pagar:") < macro.index("Copiar")
    # SRS v4.42: el fragmento sigue en la tarjeta web; el modal móvil desaparece.
    assert html.count("atajo_detalle(item)") >= 1


def test_vista_primaria_movil_se_mantiene() -> None:
    """SRS v4.42: la vista móvil es una tarjeta directa, sin modal."""
    html = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    assert 'class="atajo-tarjeta-movil__descripcion"' in html
    assert "atajo-tarjeta-movil__dias" in html
    assert "atajo-tarjeta-movil__acciones" in html
    assert "atajo-finanzas-modal" not in html


def test_css_tarjeta_solo_web_y_linea_azul() -> None:
    """La tarjeta completa aparece solo en web y la fecha lleva línea azul."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("SRS v4.33")
    bloque = css[inicio : inicio + 1800]

    assert ".atajo-detalle__fecha" in bloque
    assert "border-bottom: 2px solid var(--accent-blue)" in bloque
    base = css.split(".atajo-web {", 1)[1].split("}", 1)[0]
    assert "display: none" in base
    assert "@media (min-width: 768px)" in bloque
