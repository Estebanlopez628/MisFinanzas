"""Pruebas de la SRS v4.39: pie del modal Editar gasto sin Cancelar."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_editar_gasto_sin_cancelar_y_con_x() -> None:
    """El modal Editar gasto se cierra con la X de la cabecera, no con Cancelar."""
    fila = (RUTA / "templates/finanzas/_gasto_fijo.html").read_text(encoding="utf-8")
    assert 'data-cancelar-edicion' in fila
    assert 'edicion-gasto__cerrar' in fila
    assert ">Cancelar<" not in fila
    assert "acciones-formulario--gasto" in fila


def test_todos_los_modales_sin_cancelar_tienen_x() -> None:
    """Los modales de edición sin Cancelar conservan su X en la cabecera."""
    plantillas = (
        "finanzas/_gasto_fijo.html",
        "deudas/index.html",
        "presupuesto/index.html",
        "finanzas/index.html",
        "chancucos/index.html",
    )
    for nombre in plantillas:
        html = (RUTA / "templates" / nombre).read_text(encoding="utf-8")
        if ">Cancelar<" in html or "edicion-gasto--modal" not in html:
            # SRS v4.42: Mis Finanzas ya no abre modal de atajo en móvil.
            continue
        assert "data-cancelar-edicion" in html, nombre
        assert "edicion-gasto__cerrar" in html, nombre


def test_botones_restantes_centrados() -> None:
    """Con dos botones quedan juntos y centrados; con uno, centrado."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    pie = css.split(".edicion-gasto__formulario .acciones-formulario--gasto {", 1)[1]
    pie = pie.split("}", 1)[0]
    assert "display: flex" in pie
    assert "justify-content: center" in pie
    botones = css.split(".edicion-gasto__formulario .acciones-formulario--gasto > .boton {", 1)[1]
    botones = botones.split("}", 1)[0]
    assert "width: auto" in botones
    assert "min-width: 120px" in botones
