"""Pruebas del interés implícito simulado (SRS v1.9, sección 2.2).

El plan con `cuota × cuotas > total` se acepta, se cuadra en una amortización
interna que nunca se muestra, y solo se rechaza cuando las cuotas no cubren el
capital. Los pagos reales siguen sin intereses visibles.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app import esquemas
from app.servicios import deudas, usuarios

TOTAL = "30.000.000"
CUOTA = "300.000"
CUOTAS = 164
MENSAJE = deudas.MENSAJE_CUOTAS_INSUFICIENTES


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


def test_el_ejemplo_de_la_spec_se_acepta_sin_error() -> None:
    """30.000.000 en 164 cuotas de 300.000 es un plan válido."""
    total, pago, cuotas = deudas.validar_plan(TOTAL, CUOTA, CUOTAS)

    assert total == Decimal("30000000.00")
    assert pago == Decimal("300000.00")
    assert cuotas == CUOTAS
    assert pago * cuotas > total


def test_la_amortizacion_interna_cuadra_el_modelo_en_cero() -> None:
    """La simulación privada reparte interés ficticio y cierra en la última cuota."""
    tasa, filas = deudas.amortizacion_simulada(TOTAL, CUOTA, CUOTAS)

    assert tasa > 0
    assert len(filas) == CUOTAS
    assert filas[0]["numero"] == 1
    assert filas[-1]["numero"] == CUOTAS
    assert filas[-1]["saldo_despues"] == Decimal("0.00")
    assert sum((fila["interes"] for fila in filas), Decimal("0")) > 0
    assert sum((fila["abono_capital"] for fila in filas), Decimal("0")) == Decimal("30000000.00")


def test_los_pagos_reales_no_muestran_el_interes_ficticio(bd) -> None:
    """Aunque el plan implique interés, `pagos_deuda.interes` sigue en cero."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", TOTAL, CUOTA, CUOTAS)
    deuda.fecha_creacion = datetime(2020, 1, 1, 8, 0)
    bd.commit()

    assert deudas.aplicar_cuotas_vencidas(bd, id_usuario) > 0
    pagos = deudas.listar_pagos(bd, id_usuario)[deuda.id_deuda]
    assert all(pago.interes == Decimal("0.00") for pago in pagos)
    assert all(pago.abono_capital == Decimal("300000.00") for pago in pagos)


def test_el_esquema_rechaza_solo_las_cuotas_insuficientes() -> None:
    """El mensaje único aparece en la validación Pydantic del formulario."""
    valido = esquemas.validar_formulario(
        esquemas.DeudaNueva,
        acreedor="Banco",
        saldo_total=TOTAL,
        cuota=CUOTA,
        cuotas_pendientes=str(CUOTAS),
    )
    assert valido.acreedor == "Banco"
    assert valido.tasa_implicita is not None and valido.tasa_implicita > 0

    try:
        esquemas.validar_formulario(
            esquemas.DeudaNueva,
            acreedor="Banco",
            saldo_total=TOTAL,
            cuota="100.000",
            cuotas_pendientes="100",
        )
    except ValueError as error:
        assert MENSAJE in str(error)
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_alta_y_edicion_por_http_aceptan_el_interes_implicito(
    cliente_admin: TestClient, bd
) -> None:
    """Tanto el registro como la edición persisten el plan sin mostrar intereses."""
    respuesta = cliente_admin.post(
        "/deudas",
        data={
            "acreedor": "Banco",
            "descripcion": "Crédito de consumo",
            "saldo_total": TOTAL,
            "cuota": CUOTA,
            "cuotas_pendientes": str(CUOTAS),
            "periodicidad": "MENSUAL",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303

    id_usuario = _id_admin(bd)
    deuda = deudas.listar_deudas(bd, id_usuario)[0]
    assert deuda.saldo_total == Decimal("30000000.00")
    assert deuda.cuota_mensual == Decimal("300000.00")
    assert deuda.cuotas_pendientes == CUOTAS

    editada = cliente_admin.post(
        f"/deudas/{deuda.id_deuda}/editar",
        data={
            "acreedor": "Banco editorial",
            "descripcion": "Plan corregido",
            "saldo_total": "12.000.000",
            "cuota": "300.000",
            "cuotas_pendientes": "60",
            "periodicidad": "MENSUAL",
        },
        follow_redirects=False,
    )
    assert editada.status_code == 303
    bd.refresh(deuda)
    assert deuda.acreedor == "Banco editorial"
    assert deuda.cuotas_pendientes == 60
    assert deuda.saldo_total == Decimal("12000000.00")

    html = cliente_admin.get("/deudas").text
    assert 'name="tasa_interes"' not in html
    assert "Banco editorial" in html


def test_la_edicion_rechaza_cuotas_que_no_cubren_el_capital(
    cliente_admin: TestClient, bd
) -> None:
    """El error se muestra en la misma vista con el mensaje fijo."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", TOTAL, CUOTA, CUOTAS)

    respuesta = cliente_admin.post(
        f"/deudas/{deuda.id_deuda}/editar",
        data={
            "acreedor": "Banco",
            "saldo_total": TOTAL,
            "cuota": "100.000",
            "cuotas_pendientes": "100",
            "periodicidad": "MENSUAL",
        },
    )

    assert respuesta.status_code == 400
    assert MENSAJE in respuesta.text
