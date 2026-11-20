"""Pruebas de gastos, presupuesto y deudas (bloque A)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import deudas, gastos, usuarios


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de la cuenta `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_gasto_acepta_formato_colombiano(bd) -> None:
    """El servicio interpreta los puntos de miles del formulario."""
    gasto = gastos.crear_gasto(
        bd,
        _id_admin(bd),
        "Vivienda",
        "Arriendo",
        "1.250.000",
        date(2026, 11, 1),
        es_fijo=True,
    )

    assert gasto.valor == Decimal("1250000.00")
    assert gasto.es_fijo is True


def test_total_y_resumen_por_categoria(bd) -> None:
    """Se suman los gastos del mes y se agrupan por categoría."""
    id_usuario = _id_admin(bd)
    gastos.crear_gasto(bd, id_usuario, "Vivienda", "Arriendo", "1000000", date(2026, 11, 1))
    gastos.crear_gasto(bd, id_usuario, "Vivienda", "Servicios", "200000", date(2026, 11, 5))
    gastos.crear_gasto(bd, id_usuario, "Ocio", "Cine", "50000", date(2026, 11, 8))
    gastos.crear_gasto(bd, id_usuario, "Ocio", "Diciembre", "30000", date(2026, 12, 1))

    assert gastos.total_gastos_mes(bd, id_usuario, 2026, 11) == Decimal("1250000.00")
    resumen = gastos.resumen_por_categoria(bd, id_usuario)
    assert resumen[0]["categoria"] == "Vivienda"
    assert resumen[0]["total"] == Decimal("1200000.00")


def test_gasto_rechaza_valor_negativo(bd) -> None:
    """Los montos negativos se rechazan antes de persistir."""
    try:
        gastos.crear_gasto(bd, _id_admin(bd), "Ocio", "Error", "-10", date(2026, 11, 1))
    except ValueError as error:
        assert "negativo" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_vista_gastos_registra_y_elimina(bd, cliente_admin: TestClient) -> None:
    """El formulario crea el gasto y la acción de borrado lo quita."""
    respuesta = cliente_admin.post(
        "/gastos",
        data={
            "categoria": "Transporte",
            "descripcion": "Gasolina",
            "valor": "120.000",
            "fecha": "2026-11-10",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert "Gasolina" in cliente_admin.get("/gastos").text

    gasto = gastos.listar_gastos(bd, _id_admin(bd))[0]
    respuesta = cliente_admin.post(
        f"/gastos/{gasto.id_gasto}/eliminar", follow_redirects=False
    )
    assert respuesta.status_code == 303
    assert gastos.listar_gastos(bd, _id_admin(bd)) == []


def test_validar_plan_acepta_el_redondeo_de_la_cuota() -> None:
    """72.917 × 48 = 3.500.016: la diferencia de 16 pesos cabe en la tolerancia."""
    total, pago, cuotas = deudas.validar_plan("3.500.000", "72.917", 48)

    assert total == Decimal("3500000.00")
    assert pago == Decimal("72917.00")
    assert cuotas == 48


def test_validar_plan_rechaza_un_total_mayor_al_adeudado() -> None:
    """Cuota × cuotas mayor al total adeudado pide revisar los datos."""
    try:
        deudas.validar_plan("23.000.000", "433.000", 60)
    except ValueError as error:
        assert "más que el total adeudado" in str(error)
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_validar_plan_rechaza_un_total_menor_al_adeudado() -> None:
    """Cuota × cuotas menor al total adeudado también pide revisar los datos."""
    try:
        deudas.validar_plan("23.000.000", "300.000", 60)
    except ValueError as error:
        assert "menos que el total adeudado" in str(error)
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_deuda_rechaza_plan_que_no_cuadra(bd) -> None:
    """La cuota por el número de pagos debe coincidir con el total adeudado."""
    try:
        deudas.crear_deuda(bd, _id_admin(bd), "Banco", "1.000.000", "50.000", 10)
    except ValueError as error:
        assert "no cuadran" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_aplicar_cuotas_descuenta_solo_las_vencidas(bd) -> None:
    """Abrir el módulo aplica las cuotas cuyo vencimiento ya pasó."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    deuda.fecha_creacion = datetime(2026, 1, 31, 12, 0)
    bd.commit()

    assert deudas.aplicar_cuotas_vencidas(bd, id_usuario, date(2026, 3, 31)) == 2
    assert deudas.aplicar_cuotas_vencidas(bd, id_usuario, date(2026, 3, 31)) == 0
    assert deuda.cuotas_pendientes == 10
    assert deuda.saldo_total < Decimal("1200000")


def test_deuda_quincenal_aplica_cada_quince_dias(bd) -> None:
    """La periodicidad quincenal genera dos vencimientos por mes."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(
        bd, id_usuario, "Tienda", "600.000", "50.000", 12, "QUINCENAL"
    )
    deuda.fecha_creacion = datetime(2026, 1, 1, 9, 0)
    bd.commit()

    assert deudas.aplicar_cuotas_vencidas(bd, id_usuario, date(2026, 1, 31)) == 2


def test_ultima_cuota_deja_el_saldo_exacto_en_cero(bd) -> None:
    """El plan termina en cero y la última cuota absorbe el redondeo."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.000.000", "333.333", 3)
    deuda.fecha_creacion = datetime(2026, 1, 1, 8, 0)
    bd.commit()

    assert deudas.aplicar_cuotas_vencidas(bd, id_usuario, date(2027, 6, 30)) == 3
    bd.refresh(deuda)

    pagos = deudas.listar_pagos(bd, id_usuario)[deuda.id_deuda]
    assert deuda.estado == "PAGADA"
    assert deuda.saldo_total == Decimal("0.00")
    assert deuda.cuotas_pendientes == 0
    assert pagos[-1].saldo_despues == Decimal("0.00")
    assert sum(pago.abono_capital for pago in pagos) == Decimal("1000000.00")


def test_sin_intereses_la_cuota_abona_capital_completo(bd) -> None:
    """Cada cuota reduce el capital por su valor; no hay porción de interés."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "3.500.000", "72.917", 48)
    deuda.fecha_creacion = datetime(2026, 1, 1, 8, 0)
    bd.commit()

    assert deudas.aplicar_cuotas_vencidas(bd, id_usuario, date(2026, 3, 1)) == 2
    pagos = deudas.listar_pagos(bd, id_usuario)[deuda.id_deuda]

    assert pagos[0].valor_cuota == Decimal("72917.00")
    assert pagos[0].abono_capital == Decimal("72917.00")
    assert pagos[0].interes == Decimal("0.00")
    assert sum(pago.interes for pago in pagos) == Decimal("0.00")


def test_resumen_deudas_suma_activas(bd) -> None:
    """El resumen excluye las deudas pagadas y mensualiza la cuota quincenal."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Uno", "500.000", "50.000", 10)
    pagada = deudas.crear_deuda(bd, id_usuario, "Dos", "200.000", "200.000", 1)
    pagada.fecha_creacion = datetime(2026, 1, 1, 8, 0)
    bd.commit()
    deudas.aplicar_cuotas_vencidas(bd, id_usuario, date(2026, 2, 1))

    resumen = deudas.resumen_deudas(bd, id_usuario)
    assert resumen["saldo_total"] == Decimal("500000.00")
    assert resumen["cuota_mensual"] == Decimal("50000.00")
    assert resumen["cuotas_pendientes"] == 10
    assert resumen["activas"] == 1
    assert resumen["pagadas"] == 1

    quincenal = deudas.crear_deuda(
        bd, id_usuario, "Tres", "300.000", "25.000", 12, "QUINCENAL"
    )
    assert deudas.cuota_mensual_equivalente(quincenal) == Decimal("50000.00")


def test_vista_deudas_registra_y_muestra_amortizacion(
    cliente_admin: TestClient, bd
) -> None:
    """El formulario de seis campos guarda la deuda y muestra su plan."""
    assert cliente_admin.post(
        "/deudas",
        data={
            "acreedor": "Banco",
            "descripcion": "Tarjeta",
            "saldo_total": "3.500.000",
            "cuota": "72.917",
            "cuotas_pendientes": "48",
            "periodicidad": "MENSUAL",
        },
        follow_redirects=False,
    ).status_code == 303

    html = " ".join(cliente_admin.get("/deudas").text.split())
    assert "Banco" in html
    assert "3.500.000" in html
    # SRS v1.9: las cuotas se muestran directamente en la tabla, sin botón que las oculte.
    assert "Ver cuotas" not in html
    assert "Próximas cuotas" in html
    # SRS v1.8: sin intereses, sin abonos manuales y sin tasa capturada.
    assert "Abonar" not in html
    assert 'name="tasa_interes"' not in html
    assert 'name="fecha_limite"' not in html


def test_ruta_de_abono_manual_ya_no_existe(cliente_admin: TestClient, bd) -> None:
    """El abono manual se retiró: la amortización es automática."""
    deuda = deudas.crear_deuda(
        bd, _id_admin(bd), "Banco", "1.000.000", "100.000", 10
    )

    respuesta = cliente_admin.post(
        f"/deudas/{deuda.id_deuda}/abonar", data={"monto": "100.000"}
    )
    assert respuesta.status_code == 404

