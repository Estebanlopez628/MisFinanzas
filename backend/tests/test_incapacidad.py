"""Pruebas de incapacidades y rollover (Tarea 4).

Verifican la regla del 100% en los días 1–2, el descuento del 33.33% desde el
día 3, el reparto por mes calendario, el cruce de año y la generación del saldo
arrastrado para el periodo siguiente.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core.config import ParametrosNomina
from app.servicios.incapacidad import (
    calcular_incapacidad,
    liquidar_mes_incapacidad,
)
from app.servicios.nomina import liquidar_periodo

SUELDO = Decimal("3000000")  # valor día = 100.000


def test_dias_uno_y_dos_sin_descuento() -> None:
    """Una incapacidad de 2 días no genera descuento al trabajador."""
    resultado = calcular_incapacidad(date(2026, 3, 2), date(2026, 3, 3), SUELDO)

    assert resultado.dias_totales == 2
    assert resultado.dias_al_100 == 2
    assert resultado.dias_al_66 == 0
    assert resultado.valor_descontado == Decimal("0.00")


def test_desde_el_tercer_dia_descuenta_33_33() -> None:
    """3 días: los dos primeros al 100% y el tercero con descuento."""
    resultado = calcular_incapacidad(date(2026, 3, 2), date(2026, 3, 4), SUELDO)

    assert resultado.dias_totales == 3
    assert resultado.dias_al_100 == 2
    assert resultado.dias_al_66 == 1
    assert resultado.valor_dia == Decimal("100000.0000")
    assert resultado.valor_descontado == Decimal("33330.00")


def test_incapacidad_de_cinco_dias() -> None:
    """5 días: 2 sin descuento y 3 al 33.33% (3 × 33.330)."""
    resultado = calcular_incapacidad(date(2026, 3, 2), date(2026, 3, 6), SUELDO)

    assert resultado.dias_al_66 == 3
    assert resultado.valor_descontado == Decimal("99990.00")


def test_rango_de_un_solo_dia() -> None:
    """El primer día está cubierto al 100%: descuento cero."""
    resultado = calcular_incapacidad(date(2026, 1, 15), date(2026, 1, 15), SUELDO)

    assert resultado.dias_totales == 1
    assert resultado.valor_descontado == Decimal("0.00")
    assert len(resultado.tramos) == 1


def test_sueldo_parametrico_cambia_el_valor_dia() -> None:
    """Con 2.100.000 el día vale 70.000 y el descuento del día 3 es 23.331."""
    resultado = calcular_incapacidad(
        date(2026, 5, 4), date(2026, 5, 6), Decimal("2100000")
    )

    assert resultado.valor_dia == Decimal("70000.0000")
    assert resultado.valor_descontado == Decimal("23331.00")


def test_porcentaje_de_pago_parametrico() -> None:
    """Si la EPS cubriera el 50%, el descuento por día también sería del 50%."""
    parametros = ParametrosNomina(porcentaje_pago_desde_dia_tres=Decimal("50"))
    resultado = calcular_incapacidad(
        date(2026, 5, 4), date(2026, 5, 6), Decimal("1000000"), parametros
    )

    # Día 3: 33.333,33 de valor día × 50% = 16.666,67.
    assert resultado.valor_descontado == Decimal("16666.67")


def test_dias_de_empleador_parametricos() -> None:
    """Si el empleador cubriera sólo el primer día, el segundo ya se descuenta."""
    parametros = ParametrosNomina(dias_incapacidad_empleador=1)
    resultado = calcular_incapacidad(
        date(2026, 5, 4), date(2026, 5, 5), Decimal("3000000"), parametros
    )

    assert resultado.dias_al_100 == 1
    assert resultado.dias_al_66 == 1
    assert resultado.valor_descontado == Decimal("33330.00")


def test_cruce_de_mes_genera_tramos_separados() -> None:
    """Del 28 de marzo al 1 de abril: 4 días de marzo y 1 de abril."""
    resultado = calcular_incapacidad(date(2026, 3, 28), date(2026, 4, 1), SUELDO)

    assert resultado.dias_totales == 5
    marzo, abril = resultado.tramos
    assert (marzo.anio, marzo.mes, marzo.dias) == (2026, 3, 4)
    assert (abril.anio, abril.mes, abril.dias) == (2026, 4, 1)
    # Marzo: días 1 y 2 sin descuento; días 3 y 4 con descuento.
    assert marzo.dias_al_66 == 2
    assert marzo.valor_descontado == Decimal("66660.00")
    # Abril continúa en el día 5 de la incapacidad.
    assert abril.dias_al_66 == 1
    assert abril.valor_descontado == Decimal("33330.00")
    assert resultado.valor_descontado == Decimal("99990.00")


def test_cruce_de_anio() -> None:
    """Una incapacidad que pasa de diciembre a enero conserva la continuidad."""
    resultado = calcular_incapacidad(date(2026, 12, 30), date(2027, 1, 2), SUELDO)

    assert resultado.dias_totales == 4
    assert [tramo.mes for tramo in resultado.tramos] == [12, 1]
    # Días 1 y 2 (30 y 31 de diciembre) sin descuento; 1 y 2 de enero al 66.67%.
    assert resultado.valor_descontado == Decimal("66660.00")


def test_liquidar_mes_activo_y_arrastrar_el_resto() -> None:
    """Al liquidar marzo se descuenta su parte y se arrastra abril."""
    resultado = liquidar_mes_incapacidad(
        date(2026, 3, 30), date(2026, 4, 2), SUELDO, anio=2026, mes=3
    )

    assert resultado.dias_liquidados == 2
    assert resultado.dias_al_100 == 2
    assert resultado.valor_descontado == Decimal("0.00")
    assert resultado.dias_arrastrados == 2
    assert resultado.valor_arrastrado == Decimal("66660.00")

    assert len(resultado.saldos_pendientes) == 1
    saldo = resultado.saldos_pendientes[0]
    assert (saldo.anio, saldo.mes) == (2026, 4)
    assert saldo.dias_pendientes == 2
    assert saldo.valor_pendiente == Decimal("66660.00")
    assert saldo.fecha_inicio == date(2026, 4, 1)
    assert saldo.fecha_fin == date(2026, 4, 2)
    assert saldo.dias_liquidados_previos == 2


def test_liquidar_un_mes_sin_dias_de_incapacidad() -> None:
    """Un mes anterior al rango no liquida días, pero arrastra todo el saldo."""
    resultado = liquidar_mes_incapacidad(
        date(2026, 5, 4), date(2026, 5, 6), SUELDO, anio=2026, mes=4
    )

    assert resultado.dias_liquidados == 0
    assert resultado.valor_descontado == Decimal("0.00")
    assert resultado.dias_arrastrados == 3
    assert resultado.saldos_pendientes[0].mes == 5


def test_incapacidad_de_tres_meses_genera_dos_saldos() -> None:
    """Enero a marzo: enero liquida, febrero y marzo quedan como saldos."""
    resultado = liquidar_mes_incapacidad(
        date(2026, 1, 30), date(2026, 3, 2), SUELDO, anio=2026, mes=1
    )

    assert resultado.dias_liquidados == 2
    assert resultado.dias_arrastrados == 30
    assert [saldo.mes for saldo in resultado.saldos_pendientes] == [2, 3]
    assert resultado.saldos_pendientes[1].dias_liquidados_previos == 30


def test_mes_invalido() -> None:
    """El mes debe estar entre 1 y 12."""
    with pytest.raises(ValueError, match="mes debe estar"):
        liquidar_mes_incapacidad(date(2026, 5, 4), date(2026, 5, 6), SUELDO, mes=13)


def test_rango_invertido() -> None:
    """La fecha final no puede ser anterior a la inicial."""
    with pytest.raises(ValueError, match="no puede ser anterior"):
        calcular_incapacidad(date(2026, 5, 10), date(2026, 5, 1), SUELDO)


def test_fechas_invalidas() -> None:
    """Se exige el tipo `date` para evitar cadenas mal formadas."""
    with pytest.raises(TypeError, match="objetos 'date'"):
        calcular_incapacidad("2026-05-01", date(2026, 5, 2), SUELDO)  # type: ignore[arg-type]


def test_sueldo_negativo() -> None:
    """Un sueldo negativo es un error de captura."""
    with pytest.raises(ValueError, match="sueldo básico"):
        calcular_incapacidad(date(2026, 5, 1), date(2026, 5, 2), Decimal("-1"))


def test_integracion_con_la_liquidacion_del_periodo() -> None:
    """El descuento del mes se resta del saldo del bolsillo en la liquidación."""
    incapacidad = liquidar_mes_incapacidad(
        date(2026, 5, 4), date(2026, 5, 6), SUELDO, anio=2026, mes=5
    )
    liquidacion = liquidar_periodo(
        sueldo_basico=SUELDO,
        deduccion_incapacidad=incapacidad.valor_descontado,
        aplicar_auxilio_legal=True,
    )

    # Descuento de ley 240.000 + incapacidad 33.330.
    assert liquidacion.total_deducciones == Decimal("273330.00")
    # 3.000.000 no supera el tope de 2 SMMLV: conserva el auxilio.
    assert liquidacion.auxilio_transporte == Decimal("200000.00")
    assert liquidacion.saldo_bolsillo == Decimal("2926670.00")
