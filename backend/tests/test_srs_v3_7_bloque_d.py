"""Pruebas de la SRS v3.7, bloque D (gráfica unificada del Consejero)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.servicios import consejero, deudas, usuarios

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_el_consejo_calcula_la_proyeccion_de_cierre(bd) -> None:
    """La proyección sale del motor, sin cálculos en la plantilla."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("900000"), date(2026, 11, 1)
    )

    assert resultado.activo is True
    cierre = resultado.cierre
    assert cierre
    assert cierre["deuda_inicial"] == Decimal("1200000.00")
    assert cierre["cuota_mensual"] == Decimal("100000.00")
    assert cierre["excedente_mensual"] > Decimal("0")
    assert len(cierre["puntos"]) == 12
    assert cierre["mes_libre_index"] is not None
    assert cierre["meses_ahorrados"] > 0
    assert cierre["ahorro_mostrado"] > Decimal("0")
    assert cierre["fecha_cierre_base"] == "Nov 2027"
    assert "202" in cierre["fecha_cierre_opt"]
    assert cierre["costo_total_opt"] == deuda.saldo_total


def test_saldo_optimizado_nunca_supera_al_base(bd) -> None:
    """La regla del enunciado se cumple mes a mes."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("900000"))
    for punto in resultado.cierre["puntos"]:
        assert punto["optimizado"] <= punto["base"]


def test_la_vista_renderiza_la_grafica_unificada(bd, cliente_admin) -> None:
    """Con deuda y excedente suficiente, /presupuesto pinta el SVG nuevo."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    respuesta = cliente_admin.get("/presupuesto")
    assert respuesta.status_code == 200
    assert "data-cierre-consejero" in respuesta.text
    assert "gradOptimizado" in respuesta.text
    assert "¡Libre de deuda!" in respuesta.text
    assert "data-cierre-tooltip" in respuesta.text


def test_plantilla_y_js_de_la_grafica() -> None:
    """El bloque SVG, el hito y el tooltip están cableados."""
    html = (RUTA_APP / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    for texto in (
        "data-cierre-consejero",
        "Comparativa de cierre de deuda",
        "gradOptimizado",
        "¡Libre de deuda!",
        "data-cierre-tooltip",
        "Base (Normal)",
        "Optimizado (Con tu excedente)",
    ):
        assert texto in html

    js = (RUTA_APP / "static/js/consejero.js").read_text(encoding="utf-8")
    assert "[data-cierre-tooltip]" in js
    assert "data-base" in js
    assert "data-optimo" in js
