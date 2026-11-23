"""Pruebas del servicio de abonos a deudas (Bloque 1)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.modelos import AbonoDeuda, Deuda, Gasto, PagoDeuda
from app.servicios import deudas, usuarios


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


def test_abono_suelto_descuenta_saldo_y_cuotas(bd) -> None:
    """Un abono sin cuota solo baja saldo y número de cuotas."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    resultado = deudas.registrar_abono(
        bd, id_usuario, deuda.id_deuda, "100000", hoy=date(2026, 11, 23)
    )

    bd.refresh(deuda)
    assert resultado["saldo_total"] == Decimal("100000.00")
    assert resultado["cuotas_pendientes"] == 2
    assert deuda.cuota_mensual == Decimal("50000.00")
    assert deuda.estado == deudas.ESTADO_ACTIVA
    assert resultado["valor_cuota"] == Decimal("0.00")

    abonos = bd.query(AbonoDeuda).all()
    assert len(abonos) == 1
    assert abonos[0].valor == Decimal("100000.00")
    assert abonos[0].aplica_cuota is False
    assert bd.query(PagoDeuda).count() == 0


def test_abono_menor_que_la_cuota_ajusta_la_cuota(bd) -> None:
    """Si el resto no alcanza una cuota, la cuota se ajusta al saldo."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    deudas.registrar_abono(bd, id_usuario, deuda.id_deuda, "175000")

    bd.refresh(deuda)
    assert deuda.saldo_total == Decimal("25000.00")
    assert deuda.cuota_mensual == Decimal("25000.00")
    assert deuda.cuotas_pendientes == 1


def test_abono_mas_cuota_registra_pago(bd) -> None:
    """«Abono + cuota» descuenta ambas y deja constancia de la cuota."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    resultado = deudas.registrar_abono(
        bd, id_usuario, deuda.id_deuda, "50000", aplica_cuota=True,
        hoy=date(2026, 11, 23),
    )

    bd.refresh(deuda)
    assert resultado["valor_cuota"] == Decimal("50000.00")
    assert resultado["numero_cuota"] == 1
    assert deuda.saldo_total == Decimal("100000.00")
    assert deuda.cuotas_pendientes == 2
    pago = bd.query(PagoDeuda).one()
    assert pago.numero_cuota == 1
    assert pago.abono_capital == Decimal("50000.00")

    abono = bd.query(AbonoDeuda).one()
    assert abono.aplica_cuota is True
    assert abono.numero_cuota == 1


def test_abono_con_cuota_no_duplica_cuotas_al_abrir(bd) -> None:
    """La cuota del abono queda anclada en hoy; no se recobra al abrir."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)
    bd.commit()
    # La deuda se creó meses atrás: sin el ancla en hoy se cobrarían las cuotas
    # vencidas de golpe al abrir el módulo.
    deuda.fecha_creacion = datetime(2026, 1, 1, 12, 0, 0)
    bd.commit()

    deudas.registrar_abono(
        bd, id_usuario, deuda.id_deuda, "50000", aplica_cuota=True,
        hoy=date(2026, 11, 23),
    )
    assert bd.query(PagoDeuda).count() == 1

    # Al abrir el módulo en una fecha posterior no se agotan las cuotas pendientes.
    applies = deudas.aplicar_cuotas_vencidas(bd, id_usuario, date(2026, 11, 24))
    assert applies == 0
    assert bd.query(PagoDeuda).count() == 1


def test_abono_cierra_la_deuda(bd) -> None:
    """Llevar el saldo a cero marca la deuda como pagada."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    resultado = deudas.registrar_abono(bd, id_usuario, deuda.id_deuda, "200000")

    bd.refresh(deuda)
    assert deuda.saldo_total == Decimal("0.00")
    assert deuda.cuotas_pendientes == 0
    assert deuda.estado == deudas.ESTADO_PAGADA
    assert resultado["estado"] == deudas.ESTADO_PAGADA


@pytest.mark.parametrize("valor", ["0", "-100", "200001"])
def test_abono_rechaza_valores_invalidos(bd, valor: str) -> None:
    """No se aceptan abonos cero, negativos ni mayores al saldo."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    with pytest.raises(ValueError):
        deudas.registrar_abono(bd, id_usuario, deuda.id_deuda, valor)
    assert bd.query(AbonoDeuda).count() == 0
    assert bd.get(Deuda, deuda.id_deuda).saldo_total == Decimal("200000.00")


def test_abono_rechaza_deuda_ajena(bd) -> None:
    """Otro usuario no puede abonar una deuda que no es suya."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    with pytest.raises(ValueError, match="no pertenece"):
        deudas.registrar_abono(bd, "otro-usuario", deuda.id_deuda, "100000")


def test_endpoint_abono_devuelve_saldo(cliente_admin: TestClient, bd) -> None:
    """El POST /api devuelve el saldo y el plan ya actualizados."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    respuesta = cliente_admin.post(
        f"/api/deudas/{deuda.id_deuda}/abono",
        data={"valor": "100.000"},
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["ok"] is True
    assert datos["saldo_total"] == "100000.00"
    assert datos["cuotas_pendientes"] == 2
    assert bd.query(AbonoDeuda).count() == 1


def test_endpoint_abono_mas_cuota(cliente_admin: TestClient, bd) -> None:
    """El flag aplica_cuota descuenta también la cuota del corte."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    respuesta = cliente_admin.post(
        f"/api/deudas/{deuda.id_deuda}/abono",
        data={"valor": "50000", "aplica_cuota": "1"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["valor_cuota"] == "50000.00"
    assert bd.query(PagoDeuda).count() == 1


def test_endpoint_abono_valor_invalido(cliente_admin: TestClient, bd) -> None:
    """Un valor mayor al saldo responde 400 con mensaje limpio."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    respuesta = cliente_admin.post(
        f"/api/deudas/{deuda.id_deuda}/abono", data={"valor": "300000"}
    )

    assert respuesta.status_code == 400
    detalle = respuesta.json()["detail"]
    assert "saldo" in detalle.lower()
    assert "Value error" not in detalle


def test_abono_con_cuota_marca_gasto_pagado(bd) -> None:
    """«Abono + cuota» deja el gasto vinculado marcado como pagado."""
    from datetime import date

    from app.servicios import gastos

    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)
    gasto = gastos.crear_gasto(
        bd, id_usuario, "Créditos y Obligaciones", "Cuota", "50000", date.today(),
        es_fijo=True, quincena=1, id_deuda=deuda.id_deuda,
    )

    deudas.registrar_abono(
        bd, id_usuario, deuda.id_deuda, "50000", aplica_cuota=True
    )
    bd.refresh(gasto)
    assert gasto.pagado is True
    assert gasto.monto_pagado == Decimal("50000.00")


def test_deuda_pagada_deja_de_contar_su_gasto(bd) -> None:
    """Al pagar la deuda, su gasto vinculado sale de los totales."""
    from datetime import date

    from app.servicios import gastos

    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)
    gastos.crear_gasto(
        bd, id_usuario, "Créditos y Obligaciones", "Cuota", "50000", date.today(),
        es_fijo=True, quincena=1, id_deuda=deuda.id_deuda,
    )
    assert len(gastos.listar_gastos(bd, id_usuario)) == 1

    deudas.registrar_abono(bd, id_usuario, deuda.id_deuda, "200000")

    assert gastos.listar_gastos(bd, id_usuario) == []
