"""Pruebas del bloque de deudas a proveedores en Analítica (SRS v4.44)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.base_datos import FabricaSesiones
from app.servicios import analitica, comercial

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
    assert "background: rgba(239, 68, 68, 0.14)" in selector
    assert "border: 1px solid rgba(239, 68, 68, 0.5)" in selector
    assert "color: #fecaca" in selector
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


def test_deudas_se_suman_a_los_costos_en_mensual_y_anual(bd) -> None:
    """Costos incluye la deuda del periodo; ganancia sigue siendo de ventas."""
    hoy = datetime.now(comercial.ZONA_TIENDA)
    comercial.registrar_venta(
        bd,
        "Cliente Costos",
        "3002221111",
        [
            comercial.LineaVenta(
                nombre="Producto con costo",
                cantidad=1,
                precio_unitario="50000",
                costo_unitario="30000",
            )
        ],
        hoy,
    )
    comercial.registrar_deuda_inicial(bd, "25000", "Deuda del mes")

    mensual = analitica.reporte_mensual(bd, hoy.year)
    fila = mensual[hoy.month - 1]
    assert fila["deudas_proveedor"] == Decimal("25000")
    assert fila["costos"] == Decimal("55000")  # 30000 de venta + 25000 de deuda
    assert fila["ganancia"] == Decimal("20000")  # métrica de ventas intacta

    anual = {f["anio"]: f for f in analitica.reporte_anual(bd)}
    assert anual[hoy.year]["deudas_proveedor"] == Decimal("25000")
    assert anual[hoy.year]["costos"] == Decimal("55000")


def test_csv_incluye_la_denominacion_exacta(cliente_admin: TestClient, bd) -> None:
    """Los CSV mensual y anual conservan BOM, tildes y la etiqueta exacta."""
    encabezados, filas = analitica.tabla_csv(bd, "mensual", analitica.Filtro(), date.today())
    assert analitica.DEUDAS_PROVEEDOR_LABEL in encabezados
    assert all(len(fila) == len(encabezados) for fila in filas)
    encabezados, filas = analitica.tabla_csv(bd, "anual", analitica.Filtro(), date.today())
    assert analitica.DEUDAS_PROVEEDOR_LABEL in encabezados
    assert all(len(fila) == len(encabezados) for fila in filas)

    for tabla in ("mensual", "anual"):
        respuesta = cliente_admin.get(f"/olb-byte/analitica/exportar/{tabla}.csv")
        assert respuesta.status_code == 200
        texto = respuesta.text
        assert texto.startswith("\ufeff")
        assert analitica.DEUDAS_PROVEEDOR_LABEL in texto
        assert "Variación" in texto  # tildes conservadas


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
