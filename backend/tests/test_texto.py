"""Pruebas de los helpers de entrada de datos (montos y periodos).

Cubren la conversión del formato colombiano usado en los formularios y evitan
que un texto mal escrito se convierta en un cálculo silenciosamente erróneo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.texto import (
    formatear_mes_anio,
    parsear_monto,
    parsear_periodo_mes,
)


def test_parsear_monto_con_puntos_de_miles() -> None:
    """'3.000.000' debe interpretarse como tres millones."""
    assert parsear_monto("3.000.000") == Decimal("3000000")


def test_parsear_monto_con_simbolo_y_coma_decimal() -> None:
    """'$ 3.000.000,50' combina símbolo, miles y decimales."""
    assert parsear_monto("$ 3.000.000,50") == Decimal("3000000.50")


def test_parsear_monto_con_punto_decimal() -> None:
    """'1500.50' no es formato de miles y se respeta como decimal."""
    assert parsear_monto("1500.50") == Decimal("1500.50")


def test_parsear_monto_negativo() -> None:
    """Se admite el signo menos para permitir ajustes explícitos."""
    assert parsear_monto("-250.000") == Decimal("-250000")


def test_parsear_monto_vacio() -> None:
    """Un monto vacío no puede convertirse en cero por accidente."""
    with pytest.raises(ValueError, match="obligatorio"):
        parsear_monto("   ")


def test_parsear_monto_con_letras() -> None:
    """Las letras se rechazan con un mensaje claro."""
    with pytest.raises(ValueError, match="no es un número válido"):
        parsear_monto("tres millones")


def test_parsear_periodo_valido() -> None:
    """El formato de <input type=month> se convierte en (año, mes)."""
    assert parsear_periodo_mes("2026-03") == (2026, 3)


def test_parsear_periodo_vacio() -> None:
    """Un periodo vacío significa 'usa el mes de la fecha de inicio'."""
    assert parsear_periodo_mes("") is None
    assert parsear_periodo_mes(None) is None


def test_parsear_periodo_invalido() -> None:
    """Formatos distintos a AAAA-MM y meses fuera de rango se rechazan."""
    with pytest.raises(ValueError, match="AAAA-MM"):
        parsear_periodo_mes("03-2026")
    with pytest.raises(ValueError, match="entre 01 y 12"):
        parsear_periodo_mes("2026-13")


def test_formatear_mes_anio() -> None:
    """El periodo se presenta con el mes capitalizado."""
    assert formatear_mes_anio(2026, 3) == "Marzo de 2026"


def test_formatear_mes_anio_invalido() -> None:
    """Un mes fuera de rango es un error de programación."""
    with pytest.raises(ValueError, match="entre 1 y 12"):
        formatear_mes_anio(2026, 0)
