"""Pruebas de la SRS v4.30: atajos en dos filas y confirmación sobre dialog."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_atajos_distribucion_v433() -> None:
    """La distribución de tres filas se comparte entre tarjeta y modal."""
    html = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")

    for texto in (
        "Fecha pago:", "REF:", "Valor a Pagar:", 'class="atajo-web"',
        'class="atajo-detalle--modal"',
    ):
        assert texto in html
    assert html.count("atajo_detalle(item)") >= 2
    assert "border-bottom: 2px solid var(--accent-blue)" in css
    assert ".atajo-web {" in css
    assert "display: block" in css


def test_confirmacion_se_eleva_sobre_dialog() -> None:
    """El modal propio se mueve al dialog abierto para heredar su capa superior."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    bloque = js.split("elevarSobreDialogo", 1)[1]

    assert 'document.querySelector("dialog[open]")' in bloque
    assert "dialogo.appendChild(modal)" in bloque
    assert "elevarSobreDialogo(modalConfirmacion)" in js
    assert "reposicionarModal(modalConfirmacion)" in js
    assert "elevarSobreDialogo(modalAviso)" in js
