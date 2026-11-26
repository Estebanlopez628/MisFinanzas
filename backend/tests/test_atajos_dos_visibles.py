"""Pruebas del límite de dos atajos visibles y la alineación inferior en Mis Finanzas."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def _css() -> str:
    """Lee la hoja principal.

    Returns:
        Contenido de `estilos.css`.
    """
    return (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")


def test_lista_de_atajos_muestra_dos_con_scroll_vertical() -> None:
    """El `<ul>` de atajos se limita a dos filas y permite desplazarse."""
    css = _css()
    bloque = css.split(".lista-atajos {", 1)[1].split("}", 1)[0]
    assert "max-height: 254px" in bloque
    assert "overflow-y: auto" in bloque
    assert "overscroll-behavior: contain" in bloque
    movil = css.split(".lista-atajos {\n    max-height: 290px;", 1)
    assert len(movil) == 2


def test_ultimos_paneles_se_alinean_por_abajo_en_web() -> None:
    """La rejilla estira las columnas y empuja los dos últimos paneles al fondo."""
    css = _css()
    rejilla = css.split(".rejilla-finanzas {", 1)[1].split("}", 1)[0]
    assert "align-items: stretch" in rejilla
    assert (
        "@media (min-width: 901px) {\n"
        "  .columna-finanzas--quincenas > .panel + .panel--atajos,\n"
        "  .columna-finanzas--liquidacion > .panel--resultado {\n"
        "    margin-top: auto;\n"
        "  }\n"
        "}" in css
    )
