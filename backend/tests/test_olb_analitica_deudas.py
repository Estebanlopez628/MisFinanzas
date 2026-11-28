"""Pruebas del pasivo antiguo en Analítica (SRS v4.44, decisión final)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_analitica_sin_modulo_de_registro_y_con_pasivo_antiguo(
    cliente_admin: TestClient,
) -> None:
    """No hay formulario de deudas en Analítica; la columna es independiente."""
    respuesta = cliente_admin.get("/olb-byte/analitica")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Deudas con proveedores" not in html
    assert 'name="proveedor"' not in html
    assert "deudas-proveedor" not in html
    assert html.count("PASIVO ANTIGUO") >= 2
    assert "no incluido en Costos" in html
    # Métricas existentes intactas.
    assert "Gastos operativos" in html and "Ganancia neta" in html
    assert "Mes a mes" in html and "Año tras año" in html


def test_pasivo_antiguo_no_se_suma_a_costos(bd) -> None:
    """Costos sigue siendo el costo de ventas; el pasivo va aparte."""
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
    comercial.registrar_deuda_inicial(bd, "25000", "Pasivo viejo")

    mensual = analitica.reporte_mensual(bd, hoy.year)
    fila = mensual[hoy.month - 1]
    assert fila["costos"] == Decimal("30000")
    assert fila["pasivo_antiguo"] == Decimal("25000")
    assert fila["ganancia"] == Decimal("20000")

    anual = {f["anio"]: f for f in analitica.reporte_anual(bd)}
    assert anual[hoy.year]["costos"] == Decimal("30000")
    assert anual[hoy.year]["pasivo_antiguo"] == Decimal("25000")


def test_abono_paga_deuda_corriente_y_sobrante_baja_pasivo(bd) -> None:
    """Compra fiada 150.000 y abono 200.000: deuda actual 0, pasivo −50.000."""
    hoy = datetime.now(comercial.ZONA_TIENDA)
    comercial.registrar_deuda_inicial(bd, "100000", "Pasivo viejo")
    comercial.registrar_venta(
        bd,
        "Cliente Noviembre",
        "3003334444",
        [
            comercial.LineaVenta(
                nombre="Producto fiado",
                cantidad=1,
                precio_unitario="200000",
                costo_unitario="150000",
            )
        ],
        hoy,
    )
    comercial.registrar_abono_proveedor(bd, "200000")

    fila = analitica.reporte_mensual(bd, hoy.year)[hoy.month - 1]
    assert fila["costos"] == Decimal("150000")
    assert fila["pasivo_antiguo"] == Decimal("50000")
    assert comercial.deuda_proveedor(bd) == Decimal("50000")


def test_kpis_de_pago_proveedor_y_ganancia_global(cliente_admin: TestClient) -> None:
    """El panel muestra Pago a Proveedor y Ganancia global sin nota explicativa."""
    respuesta = cliente_admin.get("/olb-byte/analitica")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Pago a Proveedor" in html
    assert "Ganancia global" in html
    assert "Gastos operativos" in html
    assert "Ganancia neta" in html
    assert "muestra el compromiso total" not in html
    assert "kpi__nota" not in html
    assert "Gastos operativos 2026" not in html
    assert "Pago a Proveedor 2026" not in html
    assert "Ganancia neta 2026" not in html
    assert "Ganancia global 2026" not in html


def test_kpi_pago_proveedor_muestra_la_deuda_real(cliente_admin: TestClient, bd) -> None:
    """El KPI Pago a Proveedor es la deuda pendiente, no pasivo más costos."""
    deuda = comercial.deuda_proveedor(bd)
    esperado = f"${deuda:,.0f}".replace(",", ".")
    html = cliente_admin.get("/olb-byte/analitica").text
    bloque = html.split("Pago a Proveedor", 1)[1].split("</article>", 1)[0]
    assert esperado in bloque


def test_csv_incluye_la_denominacion_exacta(cliente_admin: TestClient, bd) -> None:
    """Los CSV mensual y anual conservan BOM, tildes y el rótulo PASIVO ANTIGUO."""
    encabezados, filas = analitica.tabla_csv(bd, "mensual", analitica.Filtro(), date.today())
    assert analitica.PASIVO_ANTIGUO_LABEL in encabezados
    assert all(len(fila) == len(encabezados) for fila in filas)
    encabezados, filas = analitica.tabla_csv(bd, "anual", analitica.Filtro(), date.today())
    assert analitica.PASIVO_ANTIGUO_LABEL in encabezados
    assert all(len(fila) == len(encabezados) for fila in filas)

    for tabla in ("mensual", "anual"):
        respuesta = cliente_admin.get(f"/olb-byte/analitica/exportar/{tabla}.csv")
        assert respuesta.status_code == 200
        texto = respuesta.text
        assert texto.startswith("\ufeff")
        assert analitica.PASIVO_ANTIGUO_LABEL in texto
        assert "Variación" in texto  # tildes conservadas
