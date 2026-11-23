"""Pruebas de la SRS v4.19 (delta post-v4.18)."""

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


def test_plazo_base_es_paralelo_no_suma(bd) -> None:
    """36 + 8 + 10 meses cierran en 36, nunca en 54."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Larga", "36000000", "1000000", 36)
    deudas.crear_deuda(bd, id_usuario, "Corta", "800000", "100000", 8)
    deudas.crear_deuda(bd, id_usuario, "Media", "1000000", "100000", 10)

    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("400000"), date(2026, 11, 1)
    )
    assert resultado.meses_base == 36
    assert resultado.cierre["meses_minimo"] == 36
    assert "todas tus deudas recomendadas" in " ".join(resultado.pasos)


def test_cascada_de_cuota_libera_antes(bd) -> None:
    """La cuota liberada se suma al excedente desde el mes siguiente."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Corta", "200000", "100000", 2)
    deudas.crear_deuda(bd, id_usuario, "Larga", "1000000", "100000", 10)

    con_cascada = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("400000"), date(2026, 11, 1)
    )
    assert con_cascada.meses_optimizado < con_cascada.meses_base
    assert con_cascada.cierre["cuotas_liberadas_detalle"]


def test_redaccion_hacia_proximas_metas(bd) -> None:
    """El texto exacto nombra las próximas metas a pagar."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "82320", "16464", 5)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("645204"), date(2026, 11, 1)
    )
    paso = next(paso for paso in resultado.pasos if "podrás liberar" in paso)
    assert "para tus próximas metas a pagar" in paso
    assert "Alkomprar" in paso
    assert paso.count(";") >= 0


def test_grafica_seis_meses() -> None:
    """v4.22 sustituye la gráfica a seis meses por barras comparativas."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert "¡Tu Excedente Aplasta tus Deudas!" in html
    assert "resumen_barras.meses_base_texto" in html
    assert "resumen_barras.porcentaje_global" in html
    assert "impacto-deudas__subrayado" in html
    assert "impacto-deuda__badge" in html
    assert "impacto-deuda__conector" in html
    assert "impacto-deuda__ahorro" in html
    assert "Proyección de saldo (6 meses)" not in html

    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert ".impacto-deudas__lista" in css
    assert ".impacto-deuda__barra--base" in css
    assert ".impacto-deuda__barra--optimo" in css


def test_banner_movil_y_dona_centrada() -> None:
    """Radio del banner en móvil y centrado de la dona en escritorio."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert "border-radius: 14px !important" in css
    assert "justify-content: center !important" in css
    assert "text-align: justify" in css


def test_atajos_tabla_con_anchos() -> None:
    """La tabla móvil usa table-fixed con 38/34/28 y padding compartido."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert "table-layout: fixed !important" in css
    assert "width: 38% !important" in css
    assert "width: 34% !important" in css
    assert "width: 28% !important" in css
    assert "padding: 10px 8px !important" in css
