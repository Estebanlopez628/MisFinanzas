"""Pruebas de la SRS v4.40: «Limpiar checks» visible y scroll tras eliminar."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_limpiar_checks_siempre_visible_con_gastos() -> None:
    """El botón no depende de que el servidor ya vea un ✔ pagado."""
    vista = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    inicio = vista.index("{% set gastos_visibles")
    fin = vista.index("</form>", inicio)
    bloque = vista[inicio:fin]
    assert "Limpiar checks" in bloque
    assert "selectattr('pagado')" not in bloque
    assert "selectattr('check_visible')" not in bloque


def test_eliminar_guarda_scroll_explicitamente() -> None:
    """`form.submit()` no dispara submit, así que se guarda antes de enviar."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    inicio = js.index("// Eliminar devuelve una redirección HTML")
    bloque = js[inicio : js.index("formulario.submit();", inicio)]
    assert "window.guardarScrollApp()" in bloque
