"""Pruebas de los dos atajos y medio y la alineación inferior en Mis Finanzas."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def _css() -> str:
    """Lee la hoja principal.

    Returns:
        Contenido de `estilos.css`.
    """
    return (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")


def test_lista_de_atajos_muestra_dos_y_medio_con_scroll_vertical() -> None:
    """El `<ul>` deja ver dos filas completas y parte de la tercera."""
    css = _css()
    bloque = css.split(".lista-atajos {", 1)[1].split("}", 1)[0]
    assert "max-height: 325px" in bloque
    assert "overflow-y: auto" in bloque
    assert "overscroll-behavior: contain" in bloque
    movil = css.split(".lista-atajos {\n    max-height: 370px;", 1)
    assert len(movil) == 2


def test_panel_de_atajos_se_estira_sin_perder_la_separacion() -> None:
    """En web el panel conserva los 18 px y crece para igualar el pie derecho."""
    css = _css()
    rejilla = css.split(".rejilla-finanzas {", 1)[1].split("}", 1)[0]
    assert "align-items: stretch" in rejilla
    media = css.split("@media (min-width: 901px) {", 1)[1].split("}", 3)
    atajos = media[0]
    resultado = media[1]
    assert ".columna-finanzas--quincenas > .panel + .panel--atajos" in atajos
    assert "margin-top: 0" in atajos
    assert "flex-grow: 1" in atajos
    assert ".columna-finanzas--liquidacion > .panel--resultado" in resultado
    assert "margin-top: auto" in resultado
