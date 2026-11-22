"""Pruebas de la SRS v3.4, sección 1: paleta única de donas."""

from __future__ import annotations

from decimal import Decimal

from app.core import categorias as catalogo
from app.servicios import capacidad


def test_paleta_oficial_diez_colores_unicos() -> None:
    """Los diez HEX oficiales son distintos y están centralizados."""
    esperado = (
        "#10B981",  # Base mínima de liquidez
        "#F97316",  # Alimentación y Mercado
        "#3B82F6",  # Vivienda y Servicios
        "#EF4444",  # Créditos y Obligaciones
        "#EAB308",  # Transporte y Movilidad
        "#06B6D4",  # Salud y Bienestar
        "#8B5CF6",  # Educación y Desarrollo
        "#EC4899",  # Entretenimiento y Ocio
        "#64748B",  # Otros / Imprevistos
        "#84CC16",  # Dinero Libre / Excedente
    )
    assert catalogo.COLORES_DONA == esperado
    assert len(set(catalogo.COLORES_DONA)) == 10
    assert catalogo.paleta_es_unica()


def test_la_base_ya_no_choca_con_alimentacion() -> None:
    """Base mínima y Alimentación tienen colores distintos en la dona."""
    assert catalogo.COLOR_BASE_MINIMA == "#10B981"
    assert catalogo.color_de_categoria("Alimentación y Mercado") == "#F97316"
    assert catalogo.COLOR_BASE_MINIMA != catalogo.color_de_categoria("Alimentación y Mercado")


def test_arcos_de_categoria_usan_la_paleta_central() -> None:
    """Los arcos y la base leen del mismo diccionario, sin HEX duplicados."""
    totales = {
        categoria.nombre: Decimal("100") for categoria in catalogo.CATEGORIAS
    }
    arcos = capacidad._arcos_categoria(
        totales, Decimal("50"), Decimal("25"), Decimal("1000")
    )
    colores = [arco["color"] for arco in arcos]
    assert len(colores) == len(set(colores))
    assert catalogo.COLOR_BASE_MINIMA in colores
    assert catalogo.COLOR_DINERO_LIBRE in colores


def test_arcos_de_capacidad_no_repiten_color() -> None:
    """La dona clásica tampoco repite colores entre sus cuatro segmentos."""
    arcos = capacidad._repartir_arcos(
        Decimal("200"), Decimal("100"), Decimal("300"), Decimal("1000")
    )
    colores = [arco["color"] for arco in arcos]
    assert len(colores) == len(set(colores))
    assert set(colores) <= set(catalogo.COLORES_DONA)
