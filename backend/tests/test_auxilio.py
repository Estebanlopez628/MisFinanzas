"""Pruebas del validador de auxilio de transporte (Tarea 3).

Verifican la regla del SRS RF-07: el auxilio se conserva cuando el total
devengado es menor o igual a 2 SMMLV y se anula cuando lo supera, incluyendo el
mensaje exacto exigido y la diferencia restante hasta el tope.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import ParametrosNomina
from app.servicios.auxilio import (
    MENSAJE_SIN_AUXILIO,
    evaluar_auxilio_salarial,
    evaluar_auxilio_transporte,
)
from app.servicios.nomina import liquidar_periodo

PARAMETROS = ParametrosNomina()
TOPE = Decimal("3501810.00")


def test_conserva_auxilio_bajo_el_tope() -> None:
    """Con 2.100.000 de devengado aplica el auxilio y se informa la diferencia."""
    evaluacion = evaluar_auxilio_transporte(Decimal("2100000"))

    assert evaluacion.aplica is True
    assert evaluacion.valor == Decimal("200000.00")
    assert evaluacion.tope == TOPE
    assert evaluacion.diferencia_hasta_tope == Decimal("1401810.00")
    assert evaluacion.excedente == Decimal("0.00")
    assert "Aplica Auxilio de Transporte" in evaluacion.mensaje
    assert "1.401.810" in evaluacion.mensaje


def test_tope_exacto_conserva_el_auxilio() -> None:
    """La condición del SRS es 'mayor que'; igualar el tope no anula el auxilio."""
    evaluacion = evaluar_auxilio_transporte(TOPE)

    assert evaluacion.aplica is True
    assert evaluacion.valor == Decimal("200000.00")
    assert evaluacion.diferencia_hasta_tope == Decimal("0.00")
    assert "exactamente en el tope" in evaluacion.mensaje


def test_supera_el_tope_anula_el_auxilio() -> None:
    """Un peso por encima del tope elimina el auxilio y usa el mensaje del SRS."""
    evaluacion = evaluar_auxilio_transporte(Decimal("3501811"))

    assert evaluacion.aplica is False
    assert evaluacion.valor == Decimal("0.00")
    assert evaluacion.diferencia_hasta_tope == Decimal("0.00")
    assert evaluacion.excedente == Decimal("1.00")
    assert evaluacion.mensaje == MENSAJE_SIN_AUXILIO
    assert MENSAJE_SIN_AUXILIO == (
        "Supera los 2 salarios mínimos: No aplica Auxilio de Transporte"
    )


def test_parametros_parametricos_cambian_el_tope() -> None:
    """El tope se deriva del SMMLV configurado (2 × SMMLV)."""
    parametros = ParametrosNomina(
        smmlv=Decimal("1000000"),
        valor_auxilio_transporte=Decimal("150000"),
    )
    evaluacion = evaluar_auxilio_transporte(Decimal("2000000"), parametros)

    assert evaluacion.tope == Decimal("2000000.00")
    assert evaluacion.aplica is True
    assert evaluacion.valor == Decimal("150000.00")


def test_rechaza_devengado_negativo() -> None:
    """Un devengado negativo es un error de captura."""
    with pytest.raises(ValueError, match="total devengado"):
        evaluar_auxilio_transporte(Decimal("-1"))


def test_evaluacion_salarial_suma_sueldo_y_recargos() -> None:
    """La variante salarial aplica la suma del SRS: sueldo + recargos."""
    evaluacion = evaluar_auxilio_salarial(
        sueldo_basico=Decimal("2100000"),
        total_recargos=Decimal("1401810"),
    )

    assert evaluacion.total_devengado == TOPE
    assert evaluacion.aplica is True
    assert evaluacion.diferencia_hasta_tope == Decimal("0.00")


def test_recargos_pueden_hacer_perder_el_auxilio() -> None:
    """Con 3.400.000 de sueldo, 200.000 de recargos superan el tope."""
    evaluacion = evaluar_auxilio_salarial(
        sueldo_basico=Decimal("3400000"),
        total_recargos=Decimal("200000"),
    )

    assert evaluacion.aplica is False
    assert evaluacion.excedente == Decimal("98190.00")
    assert evaluacion.valor == Decimal("0.00")


def test_liquidacion_con_auxilio_legal() -> None:
    """La liquidación automática incorpora el auxilio y su evaluación."""
    liquidacion = liquidar_periodo(Decimal("2100000"), aplicar_auxilio_legal=True)

    assert liquidacion.auxilio_transporte == Decimal("200000.00")
    assert liquidacion.total_ingresos == Decimal("2300000.00")
    assert liquidacion.total_deducciones == Decimal("168000.00")
    assert liquidacion.saldo_bolsillo == Decimal("2132000.00")
    assert liquidacion.evaluacion_auxilio is not None
    assert liquidacion.evaluacion_auxilio.aplica is True


def test_liquidacion_sin_auxilio_por_superar_el_tope() -> None:
    """Con recargos que empujan el devengado sobre el tope, el auxilio es cero."""
    liquidacion = liquidar_periodo(
        sueldo_basico=Decimal("3400000"),
        horas_por_tipo={"EXTRA_DIURNA_NORMAL": Decimal("20")},
        aplicar_auxilio_legal=True,
    )

    assert liquidacion.total_devengado > TOPE
    assert liquidacion.auxilio_transporte == Decimal("0.00")
    assert liquidacion.evaluacion_auxilio is not None
    assert liquidacion.evaluacion_auxilio.aplica is False
    assert liquidacion.evaluacion_auxilio.mensaje == MENSAJE_SIN_AUXILIO


def test_no_permite_auxilio_explicito_y_legal_a_la_vez() -> None:
    """Enviar ambos valores sería ambiguo; el motor debe rechazarlo."""
    with pytest.raises(ValueError, match="auxilio explícito"):
        liquidar_periodo(
            Decimal("2100000"),
            auxilio_transporte=Decimal("200000"),
            aplicar_auxilio_legal=True,
        )


def test_serializacion_incluye_mensaje_del_auxilio() -> None:
    """El diccionario para la UI expone la evaluación cuando se aplicó la regla."""
    con_evaluacion = liquidar_periodo(Decimal("2100000"), aplicar_auxilio_legal=True)
    datos = con_evaluacion.como_diccionario()

    assert datos["aplica_auxilio"] == "si"
    assert "Aplica Auxilio de Transporte" in str(datos["mensaje_auxilio"])

    sin_evaluacion = liquidar_periodo(Decimal("2100000")).como_diccionario()
    assert "mensaje_auxilio" not in sin_evaluacion
