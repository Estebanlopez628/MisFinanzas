"""Pruebas del bloque de deudas a proveedores en Analítica (SRS v4.44)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.base_datos import FabricaSesiones
from app.servicios import comercial

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_filtros_de_analitica_sin_linea_superior() -> None:
    """El selector de Año no lleva el divisor de formato compacto."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".formulario--filtros-analitica {", 1)[1].split("}", 1)[0]
    assert "border-top: 0" in bloque
    assert "padding-top: 0" in bloque


def test_x_uniforme_en_los_modales_de_olb_byte() -> None:
    """Cartera, pendientes y órdenes comparten la misma X roja."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    selector = css.split(".detalle-orden__cerrar,\n.pendiente-cerrar {", 1)[1].split("}", 1)[0]
    assert "background: rgba(127, 29, 29, 0.94)" in selector
    assert "box-shadow: 0 4px 14px rgba(239, 68, 68, 0.55)" in selector
    index = (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")
    assert "detalle-orden__volver" not in index
    assert 'class="detalle-orden__cerrar" data-cerrar-dialogo' in index


def test_analitica_muestra_bloque_propio_de_deudas(cliente_admin: TestClient) -> None:
    """El bloque de pasivos existe sin alterar las métricas de ventas."""
    respuesta = cliente_admin.get("/olb-byte/analitica")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Deudas con proveedores" in html
    assert "Total adeudado" in html
    assert "Compromisos pendientes con proveedores" in html
    assert 'name="proveedor"' in html and 'name="monto"' in html
    # Las métricas existentes siguen presentes.
    assert "Gastos operativos" in html and "Ganancia neta" in html
    assert "Mes a mes" in html


def test_registro_de_deuda_desde_analitica(cliente_admin: TestClient, bd) -> None:
    """El alta desde Analítica usa el libro de movimientos existente."""
    antes = comercial.deuda_proveedor(bd)
    respuesta = cliente_admin.post(
        "/olb-byte/analitica/deudas-proveedor",
        data={"proveedor": "Proveedor QA", "monto": "80.000"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert "/olb-byte/analitica?guardado=deuda" in respuesta.headers["location"]
    bd.rollback()
    assert comercial.deuda_proveedor(bd) == antes + Decimal("80000")
    movimientos = comercial.listar_movimientos_con_orden(bd)
    assert any(
        f["etiqueta"] == "Deuda inicial" and f["concepto"] == "Proveedor QA"
        for f in movimientos
    )


def test_registro_de_deuda_rechaza_monto_invalido(cliente_admin: TestClient) -> None:
    """Un monto inválido no modifica la deuda."""
    with FabricaSesiones() as bd:
        antes = comercial.deuda_proveedor(bd)
    respuesta = cliente_admin.post(
        "/olb-byte/analitica/deudas-proveedor",
        data={"proveedor": "Proveedor QA", "monto": "0"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert "error_deuda=1" in respuesta.headers["location"]
    with FabricaSesiones() as bd:
        assert comercial.deuda_proveedor(bd) == antes
