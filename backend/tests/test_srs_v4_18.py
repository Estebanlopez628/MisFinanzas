"""Pruebas de la SRS v4.18 (espaciado, Consejero y gráfica)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.servicios import consejero, deudas, usuarios

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


def test_espaciado_compacto_sin_tocar_resultado() -> None:
    """Las filas de corte y Trabajos Extras se compactan a 6 px."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert "padding: 6px 2px;" in css
    assert ".panel--quincena .lista-parametros--compacta li" in css
    assert ".bloque-gastos-quincena .lista-parametros li" in css
    bloque = css[css.index(".bloque-gastos-quincena {") :][:240]
    assert "margin-top: 8px" in bloque
    assert "padding-top: 8px" in bloque


def test_movil_apilado_y_grafica_ampliada() -> None:
    """El móvil apila velocímetros y amplía la gráfica; web queda igual."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert "grid-template-columns: 1fr !important" in css
    assert "min-height: 220px" in css
    assert "white-space: nowrap" in css
    assert "fill: #e2e8f0" in css
    assert "font-size: 14px" in css
    assert "cierre-deuda__mes--activo" in css

    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert "impacto-deuda__barra--base" in html
    assert "impacto-deuda__barra--optimo" in html
    assert "impacto-deuda__ahorro" in html
    assert "data-cierre-tooltip" not in html
    assert "Proyección de saldo (6 meses)" not in html


def test_plazo_de_la_deuda_recomendada(bd) -> None:
    """El mensaje distingue el plazo de la deuda objetivo del cierre global."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "82320", "16464", 5)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("645204"), date(2026, 11, 1)
    )
    assert "cancelarás esta deuda" in resultado.mensaje
    assert "realizando el pago mínimo" in resultado.mensaje
    assert "pagando solo lo mínimo" not in resultado.mensaje
    assert "por más tiempo" not in " ".join(resultado.pasos)
    assert "cuotas antes que realizando el pago mínimo de la cuota" in " ".join(
        resultado.pasos
    )
    assert "todas tus deudas recomendadas" in " ".join(resultado.pasos)


def test_no_nombrar_deudas_fuera_del_plan(bd) -> None:
    """La cuota liberada solo suma las deudas propuestas en el plan."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "82320", "16464", 5)
    deudas.crear_deuda(bd, id_usuario, "Addi", "300000", "25000", 12)
    deudas.crear_deuda(bd, id_usuario, "BBVA", "9000000", "90000", 100)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("700000"), date(2026, 11, 1)
    )
    pasos = " ".join(resultado.pasos)
    assert "deudas que te acabo de recomendar" in pasos
    assert "Alkomprar" in pasos and "Addi" in pasos
    paso_liberacion = next(paso for paso in resultado.pasos if "podrás liberar" in paso)
    assert "BBVA" not in paso_liberacion
    nombres = {fila["nombre"] for fila in resultado.cierre["cuotas_liberadas_detalle"]}
    assert "BBVA" not in nombres


def test_saldo_proyectado_del_escenario_verde(bd) -> None:
    """El velocímetro verde no repite el saldo inicial sin cambio."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "100000", 12)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("900000"), date(2026, 11, 1)
    )
    cierre = resultado.cierre
    assert cierre["saldo_proyectado_excedente"] < cierre["saldo_actual"]
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert "saldo_proyectado_excedente" in html
    assert "saldo proyectado" in html
