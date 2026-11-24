"""Pruebas de la SRS v4.30: atajos en dos filas y confirmación sobre dialog."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_atajos_web_dos_filas() -> None:
    """El atajo se reparte en dos filas solo desde 768 px."""
    html = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")

    assert "Valor a<br />Pagar:" in html
    inicio = css.index("SRS v4.30")
    bloque = css[inicio : inicio + 1800]
    assert "@media (min-width: 768px)" in bloque
    regla = bloque.split(".lista-atajos__item {", 1)[1].split("}", 1)[0]
    assert "grid-template-rows: auto auto" in regla
    assert ".lista-atajos__texto {" in bloque
    assert "display: contents" in bloque
    assert "grid-row: 2" in bloque


def test_confirmacion_se_eleva_sobre_dialog() -> None:
    """El modal propio se mueve al dialog abierto para heredar su capa superior."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    bloque = js.split("elevarSobreDialogo", 1)[1]

    assert 'document.querySelector("dialog[open]")' in bloque
    assert "dialogo.appendChild(modal)" in bloque
    assert "elevarSobreDialogo(modalConfirmacion)" in js
    assert "reposicionarModal(modalConfirmacion)" in js
    assert "elevarSobreDialogo(modalAviso)" in js
