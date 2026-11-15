"""Pruebas del motor de nómina (Tarea 2).

Cubren las reglas de ley colombianas parametrizadas: jornada de 210 horas,
deducciones del 4% + 4%, matriz de recargos con decimales y liquidación del
periodo. Se usan valores exactos en `Decimal` para detectar errores de redondeo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import ParametrosNomina
from app.core.numeros import redondear_dinero
from app.servicios.nomina import (
    calcular_deducciones_ley,
    calcular_recargo,
    calcular_recargos,
    calcular_total_devengado,
    calcular_valor_hora_ordinaria,
    liquidar_periodo,
)

PARAMETROS = ParametrosNomina()


def test_hora_ordinaria_sobre_210_horas() -> None:
    """2.100.000 COP entre 210 horas debe dar exactamente 10.000 COP por hora."""
    assert calcular_valor_hora_ordinaria(Decimal("2100000")) == Decimal("10000.0000")


def test_hora_ordinaria_con_conversion_desde_texto() -> None:
    """La función acepta cadenas y enteros, no solo Decimal."""
    assert calcular_valor_hora_ordinaria("2100000") == Decimal("10000.0000")
    assert calcular_valor_hora_ordinaria(2100000) == Decimal("10000.0000")


def test_hora_ordinaria_con_decimales_de_precision() -> None:
    """El valor de la hora conserva 4 decimales cuando la división no es exacta."""
    resultado = calcular_valor_hora_ordinaria(Decimal("2100001"))
    assert resultado == Decimal("10000.0048")


def test_hora_ordinaria_rechaza_sueldo_negativo() -> None:
    """Un sueldo negativo es un error de captura y debe rechazarse."""
    with pytest.raises(ValueError, match="sueldo básico"):
        calcular_valor_hora_ordinaria(Decimal("-1"))


def test_hora_ordinaria_rechaza_jornada_cero() -> None:
    """Una jornada mensual inválida no puede producir una división por cero."""
    parametros = ParametrosNomina(horas_mensuales=Decimal("0"))
    with pytest.raises(ValueError, match="jornada mensual"):
        calcular_valor_hora_ordinaria(Decimal("2100000"), parametros)


def test_deducciones_ley_4_y_4_por_ciento() -> None:
    """Sobre 2.000.000 COP: salud 80.000, pensión 80.000 y total 160.000."""
    deducciones = calcular_deducciones_ley(Decimal("2000000"))

    assert deducciones.salud == Decimal("80000.00")
    assert deducciones.pension == Decimal("80000.00")
    assert deducciones.total == Decimal("160000.00")


def test_deducciones_ley_no_incluyen_recargos() -> None:
    """Las deducciones se calculan sólo sobre el sueldo básico, no sobre extras."""
    deducciones = calcular_deducciones_ley(Decimal("3000000"))
    assert deducciones.total == Decimal("240000.00")


def test_deducciones_ley_respetan_parametros_alternos() -> None:
    """Los porcentajes son parametrizables para auditoría o cambios normativos."""
    parametros = ParametrosNomina(
        porcentaje_salud=Decimal("0.05"),
        porcentaje_pension=Decimal("0.05"),
    )
    deducciones = calcular_deducciones_ley(Decimal("1000000"), parametros)

    assert deducciones.salud == Decimal("50000.00")
    assert deducciones.pension == Decimal("50000.00")
    assert deducciones.total == Decimal("100000.00")


def test_calcular_recargo_extra_diurna_normal() -> None:
    """10 horas extra diurnas a 10.000 COP × 1.25 = 125.000 COP."""
    recargo = calcular_recargo("EXTRA_DIURNA_NORMAL", Decimal("10"), Decimal("10000"))

    assert recargo.factor == Decimal("1.25")
    assert recargo.valor_total == Decimal("125000.00")
    assert recargo.cantidad_horas == Decimal("10")
    assert recargo.etiqueta == "Hora extra diurna normal"


def test_calcular_recargo_con_decimales() -> None:
    """Se admiten horas decimales: 10.4 × 10.000 × 1.25 = 130.000 COP."""
    recargo = calcular_recargo("EXTRA_DIURNA_NORMAL", Decimal("10.4"), Decimal("10000"))
    assert recargo.valor_total == Decimal("130000.00")


def test_calcular_recargo_nocturno_dominical() -> None:
    """1.5 horas nocturnas dominicales a 10.000 × 2.50 = 37.500 COP."""
    recargo = calcular_recargo(
        "EXTRA_NOCTURNA_DOMINICAL_FESTIVA", Decimal("1.5"), Decimal("10000")
    )
    assert recargo.valor_total == Decimal("37500.00")


def test_calcular_recargo_rechaza_tipo_desconocido() -> None:
    """Un tipo fuera de la matriz legal debe fallar con mensaje explícito."""
    with pytest.raises(ValueError, match="Tipo de hora no válido"):
        calcular_recargo("HORA_MAGICA", Decimal("1"), Decimal("10000"))


def test_calcular_recargo_rechaza_horas_negativas() -> None:
    """No se pueden registrar horas negativas."""
    with pytest.raises(ValueError, match="cantidad de horas"):
        calcular_recargo("EXTRA_DIURNA_NORMAL", Decimal("-1"), Decimal("10000"))


def test_matriz_completa_de_recargos() -> None:
    """La matriz liquida cada factor y totaliza horas y dinero en orden canónico."""
    horas = {
        "EXTRA_DIURNA_NORMAL": Decimal("10"),
        "EXTRA_NOCTURNA": Decimal("4"),
        "EXTRA_DIURNA_DOMINICAL_FESTIVA": Decimal("2"),
        "EXTRA_NOCTURNA_DOMINICAL_FESTIVA": Decimal("1.5"),
        "RECARGO_NOCTURNO": Decimal("20"),
        "RECARGO_DOMINICAL_FESTIVO": Decimal("10"),
    }

    resultado = calcular_recargos(horas, Decimal("10000"))

    valores = {item.tipo_hora: item.valor_total for item in resultado.detalle}
    assert valores == {
        "EXTRA_DIURNA_NORMAL": Decimal("125000.00"),
        "EXTRA_NOCTURNA": Decimal("70000.00"),
        "EXTRA_DIURNA_DOMINICAL_FESTIVA": Decimal("40000.00"),
        "EXTRA_NOCTURNA_DOMINICAL_FESTIVA": Decimal("37500.00"),
        "RECARGO_NOCTURNO": Decimal("70000.00"),
        "RECARGO_DOMINICAL_FESTIVO": Decimal("190000.00"),
    }
    assert resultado.total_horas == Decimal("47.50")
    assert resultado.total_valor == Decimal("532500.00")
    # El orden del desglose debe ser el canónico, no el del diccionario recibido.
    assert [item.tipo_hora for item in resultado.detalle][0] == "EXTRA_DIURNA_NORMAL"
    assert [item.tipo_hora for item in resultado.detalle][-1] == "RECARGO_DOMINICAL_FESTIVO"


def test_matriz_ignora_tipos_en_cero() -> None:
    """Un tipo declarado en cero no debe ensuciar el desglose."""
    resultado = calcular_recargos({"EXTRA_DIURNA_NORMAL": Decimal("0")}, Decimal("10000"))

    assert resultado.detalle == ()
    assert resultado.total_valor == Decimal("0.00")
    assert resultado.total_horas == Decimal("0.00")


def test_matriz_sin_horas() -> None:
    """Sin registros la matriz devuelve totales en cero, sin errores."""
    resultado = calcular_recargos(None, Decimal("10000"))
    assert resultado.total_valor == Decimal("0.00")


def test_total_devengado_suma_sueldo_y_recargos() -> None:
    """Definición del SRS: devengado = sueldo + recargos (sin auxilio)."""
    assert calcular_total_devengado(Decimal("2100000"), Decimal("125000")) == Decimal("2225000.00")


def test_liquidacion_completa_con_auxilio_e_incapacidad() -> None:
    """La liquidación integra recargos, deducciones, auxilio e incapacidad."""
    liquidacion = liquidar_periodo(
        sueldo_basico=Decimal("2100000"),
        horas_por_tipo={"EXTRA_DIURNA_NORMAL": Decimal("10")},
        auxilio_transporte=Decimal("200000"),
        deduccion_incapacidad=Decimal("50000"),
    )

    assert liquidacion.valor_hora_ordinaria == Decimal("10000.0000")
    assert liquidacion.total_recargos == Decimal("125000.00")
    assert liquidacion.total_devengado == Decimal("2225000.00")
    assert liquidacion.total_ingresos == Decimal("2425000.00")
    assert liquidacion.deducciones_ley.total == Decimal("168000.00")
    assert liquidacion.total_deducciones == Decimal("218000.00")
    assert liquidacion.saldo_bolsillo == Decimal("2207000.00")


def test_liquidacion_cumple_la_invariante_contable() -> None:
    """Invariante: saldo de bolsillo = ingresos totales − deducciones totales."""
    liquidacion = liquidar_periodo(
        sueldo_basico=Decimal("1750905"),
        horas_por_tipo={
            "EXTRA_NOCTURNA": Decimal("3.5"),
            "RECARGO_DOMINICAL_FESTIVO": Decimal("6"),
        },
        auxilio_transporte=Decimal("200000"),
        deduccion_incapacidad=Decimal("0"),
    )

    assert liquidacion.saldo_bolsillo == redondear_dinero(
        liquidacion.total_ingresos - liquidacion.total_deducciones
    )


def test_liquidacion_permite_saldo_negativo() -> None:
    """Si las deducciones superan los ingresos, el saldo debe ser negativo y visible."""
    liquidacion = liquidar_periodo(
        sueldo_basico=Decimal("1000000"),
        deduccion_incapacidad=Decimal("1200000"),
    )

    assert liquidacion.saldo_bolsillo < 0
    assert liquidacion.saldo_bolsillo == Decimal("-280000.00")


def test_liquidacion_rechaza_incapacidad_negativa() -> None:
    """El descuento por incapacidad no puede ser negativo."""
    with pytest.raises(ValueError, match="deducción por incapacidad"):
        liquidar_periodo(Decimal("2100000"), deduccion_incapacidad=Decimal("-1"))


def test_serializacion_para_vistas() -> None:
    """`como_diccionario` devuelve cadenas para conservar precisión en JSON."""
    liquidacion = liquidar_periodo(Decimal("2100000"))
    datos = liquidacion.como_diccionario()

    assert datos["sueldo_basico"] == "2100000.00"
    assert datos["saldo_bolsillo"] == "1932000.00"
    assert all(isinstance(valor, str) for valor in datos.values())
