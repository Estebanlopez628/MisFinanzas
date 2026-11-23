"""Pruebas de la SRS v4.13 (tarjetas limpias y Consejero sin intereses)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import consejero, deudas, perfiles, usuarios

DIRECCION = "F:/Nuevo Proyecto de trabajo/Fnanzas y OLB_BYTE/backend/app"


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


def test_tarjetas_solo_muestran_neto_y_gastos(cliente_admin: TestClient, bd) -> None:
    """Las tarjetas de corte no repiten ley ni deducciones fijas."""
    html = cliente_admin.get("/finanzas").text
    assert "data-deducciones-quincena" not in html
    assert "data-fijas-quincena" not in html
    assert "Deducciones fijas del salario" not in html.split("Resultado del periodo")[0]
    assert "Sueldo devengado" in html
    assert "Gastos fijos" in html


def test_sueldo_neto_corte_incluye_fijas(bd) -> None:
    """El neto visible del corte resta la ley y las deducciones fijas."""
    from app.servicios import deducciones_fijas, quincenas

    id_usuario = _id_admin(bd)
    perfiles.guardar_perfil(bd, id_usuario, "3.000.000", perfiles.MODALIDAD_MENSUAL)
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Libranza", "100.000", 1)

    fila = quincenas.resumen_quincenas(bd, id_usuario, perfiles.obtener_perfil(bd, id_usuario), 2026, 11)[0]
    assert fila.sueldo_neto_corte == fila.devengado_neto - Decimal("100000")
    assert fila.saldo_libre == fila.sueldo_neto_corte - fila.gastos


def test_json_de_quincenas_entrega_el_neto(cliente_admin: TestClient) -> None:
    """El recálculo reactivo usa el mismo neto que la tarjeta."""
    cuerpo = cliente_admin.post(
        "/finanzas/calcular", json={"sueldo_basico": "3.000.000"}
    ).json()
    fila = cuerpo["quincenas"][0]
    assert "deducciones_fijas" not in fila
    assert fila["ingreso"].startswith("$")


def test_consejero_sin_intereses_ficticios(bd) -> None:
    """Todas las cifras de cierre corresponden al saldo real registrado."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("900000"), date(2026, 11, 1)
    )
    cierre = resultado.cierre

    assert cierre["saldo_actual"] == cierre["deuda_inicial"]
    assert cierre["reduccion_capital_12m"] >= Decimal("0")
    assert cierre["costo_total_base"] == cierre["deuda_inicial"]
    assert cierre["ahorro_mostrado"] == cierre["reduccion_capital_12m"]
    assert "más de 12 meses" not in resultado.mensaje
    assert "meses" in resultado.mensaje


def test_meses_completos_y_desglose_de_deudas(bd) -> None:
    """Velocímetros y texto usan meses completos y Deuda + Saldo + Cuota."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "1.200.000", "100.000", 12)
    deudas.crear_deuda(bd, id_usuario, "Addi", "600.000", "50.000", 12)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("900000"), date(2026, 11, 1)
    )
    cierre = resultado.cierre

    assert cierre["fecha_cierre_base"].startswith(("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"))
    assert cierre["puntos"][0]["mes"] == "Noviembre"
    assert {d["nombre"] for d in cierre["deudas_detalle"]} == {"Alkomprar", "Addi"}
    assert all(
        {"nombre", "saldo", "cuota"} <= set(d) for d in cierre["deudas_detalle"]
    )
    assert "saldo:" in resultado.mensaje
    assert "cuota:" in resultado.mensaje
    assert any("saldo:" in paso and "cuota:" in paso for paso in resultado.pasos)
    assert any("liberarás" in paso and "(" in paso for paso in resultado.pasos)


def test_plantilla_y_js_con_los_nuevos_textos() -> None:
    """La plantilla y el JS muestran los textos y el detalle real."""
    from pathlib import Path

    base = Path(DIRECCION)
    html = (base / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert " saldo · Sin abono extra" in html
    assert " saldo ·" in html  # línea inferior del cockpit (v4.17)
    assert "Abonando +" in html
    assert "Reducción extra acumulada:" in html
    assert "data-reduccion" in html
    assert "Más de 12 meses" not in html
    assert "¡Ahorras" not in html

    js = (base / "static/js/consejero.js").read_text(encoding="utf-8")
    assert "Saldo Base:" in js
    assert "Saldo Optimizado:" in js
    assert "Reducción extra acumulada:" in js


def test_layout_de_escritorio_no_toca_movil() -> None:
    """Las reglas de ancho y píldoras viven solo en el media query de 768 px."""
    from pathlib import Path

    css = (Path(DIRECCION) / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("@media (min-width: 768px) {", css.index(".cierre-deuda__meses"))
    bloque = css[inicio : inicio + 2200]
    assert "max-width: none !important" in bloque
    assert "border: 1px solid rgba(255, 255, 255, 0.08) !important" in bloque
    assert "background: #10b981 !important" in bloque
    assert "border-radius: 999px !important" in bloque
