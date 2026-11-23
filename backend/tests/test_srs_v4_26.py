"""Pruebas de la SRS v4.26: grilla de modales y checks optimistas."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.modelos import Gasto
from app.servicios import gastos, usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


def _id_admin(bd) -> str:
    """Devuelve el identificador del administrador sembrado.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador del administrador de pruebas.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_modales_usan_grilla_de_dos_botones_y_cancelar() -> None:
    """Editar deuda y editar deducción comparten la misma grilla 2 + 1."""
    deudas_html = (RUTA / "templates/deudas/index.html").read_text(encoding="utf-8")
    presupuesto_html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")

    for html in (deudas_html, presupuesto_html):
        assert "acciones-formulario--grilla" in html
        assert "boton--ancho-completo" in html
        assert ">Cancelar</button>" in html

    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".acciones-formulario--grilla {", 1)[1].split("}", 1)[0]
    assert "display: grid" in bloque
    assert "grid-template-columns: 1fr 1fr" in bloque
    assert "gap: 12px" in bloque
    assert "grid-column: 1 / -1" in css


def test_api_pagado_y_no_pagado(cliente_admin: TestClient, bd) -> None:
    """Los endpoints JSON llaman al mismo servicio de metas y créditos."""
    id_usuario = _id_admin(bd)
    gasto = gastos.crear_gasto(
        bd, id_usuario, "Vivienda", "Arriendo", "800000", date.today(), es_fijo=True
    )

    marcado = cliente_admin.post(f"/api/gastos/{gasto.id_gasto}/pagado")
    assert marcado.status_code == 200
    assert marcado.json()["ok"] is True
    assert marcado.json()["pagado"] is True
    bd.refresh(gasto)
    assert gasto.pagado is True

    desmarcado = cliente_admin.post(f"/api/gastos/{gasto.id_gasto}/no-pagado")
    assert desmarcado.status_code == 200
    assert desmarcado.json()["pagado"] is False
    bd.refresh(gasto)
    assert gasto.pagado is False


def test_api_inexistente_devuelve_404(cliente_admin: TestClient) -> None:
    """Un gasto ajeno o inexistente responde 404 con mensaje limpio."""
    respuesta = cliente_admin.post("/api/gastos/no-existe/pagado")
    assert respuesta.status_code == 404
    assert respuesta.json()["ok"] is False


def test_js_check_optimista_sin_recarga() -> None:
    """El JavaScript cambia el check al instante y guarda en segundo plano."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    bloque = js.split("SRS v4.26: checks de gastos fijos", 1)[1]

    assert "form[data-check-gasto]" in bloque
    assert "evento.preventDefault()" in bloque
    assert "fetch(ruta" in bloque
    assert "boton.style.pointerEvents = \"none\"" in bloque
    assert "window.mostrarAvisoApp" in bloque
    assert "location.reload" not in bloque
