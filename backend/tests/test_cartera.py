"""Pruebas de la Fase 4 de OLB_BYTE: balance de cartera, signos, dona y deuda al proveedor.

Cubren RF-08 (pagos al proveedor), RF-09 (tabla de balance), RF-10 (signos y colores
solo en este módulo) y RF-11 (gráfica tipo dona calculada en el servidor).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import comercial


def _venta(bd, precio: str = "50000", costo: str = "20000"):
    """Registra una venta de una línea con precio y costo dados.

    Args:
        bd: Sesión de base de datos.
        precio: Precio de venta.
        costo: Costo al proveedor.

    Returns:
        La orden persistida.
    """
    return comercial.registrar_venta(
        bd,
        "Ana Pérez",
        "3001234567",
        [comercial.LineaVenta(nombre="Audífonos BT", cantidad=1, precio_unitario=precio, costo_unitario=costo)],
    )


def test_clasificar_saldo_usa_signo_y_color_solo_en_deficit_y_superavit() -> None:
    """Un déficit lleva signo menos y rojo; un superávit, verde; cero no lleva color."""
    assert comercial.clasificar_saldo(Decimal("-20000")) == ("−$20.000", "valor-negativo")
    assert comercial.clasificar_saldo(Decimal("10000")) == ("$10.000", "valor-positivo")
    assert comercial.clasificar_saldo(Decimal("0")) == ("$0", "")


def test_tabla_balance_calcula_balance_y_efectivo_libre() -> None:
    """Balance = cartera − deuda y efectivo libre = caja − deuda, con su signo."""
    resumen = {
        "cartera_clientes": Decimal("60000"),
        "deuda_proveedor": Decimal("50000"),
        "balance": Decimal("10000"),
        "caja_recaudada": Decimal("30000"),
        "efectivo_libre": Decimal("-20000"),
    }

    filas = {fila["etiqueta"]: fila for fila in comercial.tabla_balance(resumen)}

    assert filas["Balance de cartera"]["texto"] == "$10.000"
    assert filas["Balance de cartera"]["clase"] == "valor-positivo"
    assert filas["Efectivo libre real"]["texto"] == "−$20.000"
    assert filas["Efectivo libre real"]["clase"] == "valor-negativo"
    assert filas["Total adeudado al proveedor"]["clase"] == ""


def test_segmentos_dona_reparten_cien_unidades_entre_cartera_y_deuda() -> None:
    """Los arcos suman 100 y el segundo empieza donde termina el primero."""
    arcos = comercial.segmentos_dona(Decimal("60000"), Decimal("40000"))

    assert [arco["longitud"] for arco in arcos] == [60.0, 40.0]
    assert [arco["desplazamiento"] for arco in arcos] == [0.0, -60.0]
    assert arcos[0]["valor"] == "$60.000"


def test_segmentos_dona_sin_deuda_muestra_solo_cartera() -> None:
    """Sin deuda con el proveedor, la cartera ocupa todo el anillo."""
    arcos = comercial.segmentos_dona(Decimal("50000"), Decimal("0"))

    assert len(arcos) == 2
    assert arcos[0]["longitud"] == 100.0
    assert arcos[1]["longitud"] == 0.0


def test_segmentos_dona_vacios_sin_cartera_ni_deuda() -> None:
    """Sin datos no hay arcos que dibujar."""
    assert comercial.segmentos_dona(Decimal("0"), Decimal("0")) == []


def test_panel_de_cartera_muestra_balance_y_dona(cliente_admin: TestClient, bd) -> None:
    """La vista presenta el balance, la gráfica y el libro del proveedor."""
    _venta(bd, precio="50000", costo="20000")

    respuesta = cliente_admin.get("/olb-byte/cartera")

    assert respuesta.status_code == 200
    assert "Balance" in respuesta.text
    assert "dona__svg" in respuesta.text
    assert "Compra a crédito" in respuesta.text
    assert "$50.000" in respuesta.text


def test_deficit_se_muestra_en_rojo_con_signo_menos(cliente_admin: TestClient, bd) -> None:
    """Con deuda mayor que la caja, el efectivo libre aparece con «−» y en rojo."""
    _venta(bd, precio="30000", costo="25000")

    respuesta = cliente_admin.get("/olb-byte/cartera")

    assert "−$" in respuesta.text
    assert "valor-negativo" in respuesta.text


def test_pago_al_proveedor_reduce_la_deuda(cliente_admin: TestClient, bd) -> None:
    """Un pago registrado baja la deuda y redirige con confirmación (RF-08)."""
    _venta(bd, precio="50000", costo="20000")

    respuesta = cliente_admin.post(
        "/olb-byte/proveedor/abonos",
        data={"monto": "15.000", "concepto": "Pago de mayo"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/olb-byte/cartera?guardado=1"
    assert comercial.deuda_proveedor(bd) == Decimal("5000")


def test_pago_mayor_a_la_deuda_se_rechaza(cliente_admin: TestClient, bd) -> None:
    """Un pago por encima de la deuda devuelve 400 y no cambia el saldo."""
    _venta(bd, precio="50000", costo="20000")

    respuesta = cliente_admin.post("/olb-byte/proveedor/abonos", data={"monto": "25.000"})

    assert respuesta.status_code == 400
    assert "supera la deuda" in respuesta.text
    assert comercial.deuda_proveedor(bd) == Decimal("20000")


def test_pago_sin_monto_valido_muestra_error(cliente_admin: TestClient, bd) -> None:
    """Un monto cero o vacío no registra movimiento."""
    _venta(bd)

    respuesta = cliente_admin.post("/olb-byte/proveedor/abonos", data={"monto": "0"})

    assert respuesta.status_code == 400
    assert "mayor que cero" in respuesta.text


def test_usuario_publico_no_ve_la_cartera(cliente_usuario: TestClient) -> None:
    """La vista de cartera exige administrador."""
    assert cliente_usuario.get("/olb-byte/cartera").status_code == 403

