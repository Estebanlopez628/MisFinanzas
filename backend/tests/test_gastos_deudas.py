"""Pruebas de gastos, presupuesto y deudas (bloque A)."""

from __future__ import annotations

from datetime import date
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


def test_deuda_abono_actualiza_saldo_y_estado(bd) -> None:
    """Un abono parcial deja PARCIAL; el total la marca PAGADA."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.000.000", cuota_mensual="100.000")

    deuda = deudas.abonar_deuda(bd, id_usuario, deuda.id_deuda, "400.000")
    assert deuda.saldo_total == Decimal("600000.00")
    assert deuda.estado == "ACTIVA"

    deuda = deudas.abonar_deuda(bd, id_usuario, deuda.id_deuda, "600.000")
    assert deuda.saldo_total == Decimal("0.00")
    assert deuda.estado == "PAGADA"


def test_deuda_rechaza_abono_mayor_al_saldo(bd) -> None:
    """No se puede abonar más de lo pendiente."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "500.000")

    try:
        deudas.abonar_deuda(bd, id_usuario, deuda.id_deuda, "600.000")
    except ValueError as error:
        assert "superar" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_resumen_deudas_suma_activas(bd) -> None:
    """El resumen excluye las deudas ya pagadas del saldo."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Uno", "500.000", cuota_mensual="50.000")
    pagada = deudas.crear_deuda(bd, id_usuario, "Dos", "200.000")
    deudas.abonar_deuda(bd, id_usuario, pagada.id_deuda, "200.000")

    resumen = deudas.resumen_deudas(bd, id_usuario)
    assert resumen["saldo_total"] == Decimal("500000.00")
    assert resumen["cuota_mensual"] == Decimal("50000.00")
    assert resumen["activas"] == 1
    assert resumen["pagadas"] == 1


def test_vista_deudas_registra_y_abona(cliente_admin: TestClient) -> None:
    """El formulario y el abono responden con redirección."""
    assert cliente_admin.post(
        "/deudas",
        data={"acreedor": "Banco", "saldo_total": "800.000", "cuota_mensual": "80.000"},
        follow_redirects=False,
    ).status_code == 303
    html = cliente_admin.get("/deudas").text
    assert "Banco" in html
    assert "800.000" in html
