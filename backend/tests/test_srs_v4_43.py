"""Pruebas de la SRS v4.43: columnas móviles y portal del modal de atajos."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_solo_tres_columnas_en_movil() -> None:
    """Referencia y Acciones existen solo en Web; en móvil quedan tres columnas."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert (
        ".tabla--atajos thead th:nth-child(4),\n"
        "  .tabla--atajos thead th:nth-child(5),\n"
        "  .tabla--atajos tbody tr[data-chancuco-fila] > td:nth-child(4),\n"
        "  .tabla--atajos tbody tr[data-chancuco-fila] > td:nth-child(5)" in css
    )
    plantilla = (RUTA / "templates/chancucos/index.html").read_text(encoding="utf-8")
    assert "<th scope=\"col\">Descripción</th>" in plantilla
    assert "Valor a<br />Pagar" in plantilla
    assert "Días de<br />Pago" in plantilla
    assert "<th scope=\"col\">Acciones</th>" in plantilla


def test_scroll_solo_si_el_texto_no_cabe() -> None:
    """La tabla crece con el contenido en lugar de forzar un ancho fijo."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert "table-layout: auto !important" in css
    assert "width: max-content !important" in css
    assert "min-width: 100% !important" in css
    assert "min-width: 440px" not in css


def test_modal_de_atajo_sale_al_body() -> None:
    """El modal se saca del overflow de la tarjeta y vuelve al cerrarse."""
    js = (RUTA / "static/js/deudas.js").read_text(encoding="utf-8")
    inicio = js.index("function sacarAtajoDelContexto")
    bloque = js[inicio : js.index("function vigilarPortabilidad", inicio)]
    assert 'detalles.classList.contains("atajo-modal")' in bloque
    assert "document.body.appendChild(detalles)" in bloque
    assert "marcadores.set(detalles, marcador)" in bloque
    assert 'document.querySelectorAll("details.atajo-modal")' in js
