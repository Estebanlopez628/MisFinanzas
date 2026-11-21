"""Pruebas de alineación y modal de deducciones fijas (SRS v1.9, 3.3)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deducciones_fijas, usuarios

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"


def test_las_acciones_de_deducciones_estan_a_la_derecha_y_el_modal_tiene_cierre(
    cliente_admin: TestClient, bd
) -> None:
    """Escritorio alinea los iconos; el modal ofrece Actualizar/Eliminar y cierre arriba."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    deduccion = deducciones_fijas.crear_deduccion(
        bd, cuenta.id_usuario, "Libranza", "120.000", 1
    )

    html = cliente_admin.get("/presupuesto").text

    assert f'data-deduccion-fila data-id-deduccion="{deduccion.id_deduccion}"' in html
    assert "edicion-gasto edicion-gasto--modal" in html
    assert ">Actualizar</button>" in html
    assert ">Eliminar</button>" in html
    assert 'formaction="' in html
    assert f"/deducciones/{deduccion.id_deduccion}/eliminar" in html
    assert "data-cancelar-edicion" in html
    assert "edicion-gasto__cerrar" in html
    assert ">Cancelar</button>" not in html
    assert html.index(">Actualizar</button>") < html.index(">Eliminar</button>")
    assert 'aria-label="Eliminar Libranza"' in html
    assert "js/deudas.js" in html


def test_el_css_oculta_los_iconos_en_movil_y_alinea_a_la_derecha() -> None:
    """La fila se vuelve táctil y los botones laterales desaparecen en móvil."""
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")

    regla = css.split(".lista-gastos__item[data-deduccion-fila] > .lista-gastos__acciones {", 1)[1]
    assert "justify-content: flex-end;" in regla.split("}", 1)[0]
    assert "text-align: right;" in regla.split("}", 1)[0]

    bloque_movil = css.split("@media (max-width: 640px)", 1)[1]
    assert ".lista-gastos__item[data-deduccion-fila]" in bloque_movil
    assert "> .lista-gastos__acciones > summary" in bloque_movil
    assert "> .lista-gastos__acciones > form" in bloque_movil
    assert "display: none !important;" in bloque_movil


def test_todos_los_modales_se_centran_y_las_alertas_tienen_espacio() -> None:
    """El modal se centra por sí mismo y los avisos no quedan pegados."""
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    modal = css.split("details.edicion-gasto--modal[open] > .edicion-gasto__formulario {", 1)[1]
    declaraciones = modal.split("}", 1)[0]
    for regla in (
        "position: fixed;",
        "top: 50%;",
        "left: 50%;",
        "transform: translate(-50%, -50%);",
    ):
        assert regla in declaraciones
    assert "margin-bottom: 12px;" in css.split(".alerta {", 1)[1].split("}", 1)[0]


def test_el_formulario_y_la_lista_de_deducciones_tienen_separacion(
    cliente_admin: TestClient, bd
) -> None:
    """El alta y el listado no quedan pegados."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    deducciones_fijas.crear_deduccion(bd, cuenta.id_usuario, "Libranza", "120.000", 1)

    html = cliente_admin.get("/presupuesto").text
    assert "formulario--deducciones" in html
    assert "lista-gastos--deducciones" in html


def test_el_javascript_abre_el_modal_al_tocar_la_fila_de_deduccion() -> None:
    """El mismo script de donas y deudas atiende las filas de deducciones."""
    javascript = (RAIZ_APP / "static" / "js" / "deudas.js").read_text(encoding="utf-8")

    assert 'conectarFilas("li[data-deduccion-fila]"' in javascript
    assert 'conectarFilas("tr[data-deuda-fila]"' in javascript
    assert "matchMedia" in javascript
