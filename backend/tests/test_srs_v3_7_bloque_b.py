"""Pruebas de la SRS v3.7, bloque B (validación real de deuda)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def test_formularios_publican_los_ids_actuales() -> None:
    """Los tres orígenes llevan la lista actual de deudas para comparar."""
    for relativa in (
        "templates/finanzas/index.html",
        "templates/presupuesto/index.html",
        "templates/trabajos/index.html",
    ):
        html = (RUTA_APP / relativa).read_text(encoding="utf-8")
        assert "data-deudas-actuales=" in html, relativa


def test_comparacion_de_ids_al_regresar() -> None:
    """Solo se marca SI si aparece un ID nuevo o el backend lo confirmó."""
    js = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")
    assert "function idsDeudasActuales(formulario)" in js
    assert "existing_debt_ids: idsDeudasActuales(formulario)" in js
    assert "var nueva = actuales.find(function (id) {" in js
    assert "anteriores.indexOf(id) === -1" in js
    assert "actuales.indexOf(pendiente.created_debt_id) !== -1" in js
    assert "var creada =" in js
    assert "opcionNo.checked = true" in js


def test_confirmacion_tras_post_exitoso(cliente_usuario: TestClient) -> None:
    """El POST correcto marca debt_created y guarda el ID de la deuda nueva."""
    html = cliente_usuario.get("/deudas?guardado=1").text
    assert "pendiente.debt_created = true" in html
    assert "pendiente.created_debt_id" in html
