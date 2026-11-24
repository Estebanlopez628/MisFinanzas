"""Prueba de regresión de la SRS v4.29: modales centrados también en web."""

from __future__ import annotations

from pathlib import Path

CSS = (
    Path(__file__).resolve().parent.parent / "app/static/css/estilos.css"
).read_text(encoding="utf-8")


def test_app_no_queda_dentro_de_un_media_query() -> None:
    """El bloque .app-modal está a nivel superior, no dentro de @media móvil."""
    indice = CSS.index(".app-modal {")
    profundidad = CSS[:indice].count("{") - CSS[:indice].count("}")
    assert profundidad == 0, f"quedan {profundidad} llaves abiertas antes de .app-modal"


def test_app_modal_centrado_y_al_frente() -> None:
    """El modal cubre el viewport y centra su tarjeta, con capa 9999."""
    bloque = CSS.split(".app-modal {", 1)[1].split("}", 1)[0]
    for declaracion in (
        "position: fixed;",
        "inset: 0;",
        "z-index: 9999;",
        "display: flex;",
        "align-items: center;",
        "justify-content: center;",
        "padding: 1rem;",
    ):
        assert declaracion in bloque
