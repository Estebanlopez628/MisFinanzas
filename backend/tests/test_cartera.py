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


def test_barras_balance_muestran_saldos_con_signo_y_color() -> None:
    """Balance y efectivo libre llevan signo y color; los demás saldos, no."""
    resumen = {
        "cartera_clientes": Decimal("60000"),
        "deuda_proveedor": Decimal("50000"),
        "balance": Decimal("10000"),
        "caja_recaudada": Decimal("30000"),
        "efectivo_libre": Decimal("-20000"),
    }

    barras = {barra["etiqueta"]: barra for barra in comercial.barras_balance(resumen)}

    assert barras["Balance de cartera"]["texto"] == "$10.000"
    assert barras["Balance de cartera"]["clase"] == "valor-positivo"
    assert barras["Efectivo libre real"]["texto"] == "−$20.000"
    assert barras["Efectivo libre real"]["clase"] == "valor-negativo"
    assert barras["Efectivo libre real"]["color"] == "var(--accent-red)"
    assert barras["Total adeudado por clientes"]["clase"] == ""
    assert barras["Efectivo libre real"]["hay_negativos"] is True


def test_barras_con_deficit_salen_a_la_izquierda_del_cero() -> None:
    """Con un déficit el cero queda al centro: el negativo crece hacia la izquierda."""
    resumen = {
        "cartera_clientes": Decimal("60000"),
        "deuda_proveedor": Decimal("50000"),
        "balance": Decimal("10000"),
        "caja_recaudada": Decimal("30000"),
        "efectivo_libre": Decimal("-20000"),
    }

    barras = {barra["etiqueta"]: barra for barra in comercial.barras_balance(resumen)}

    assert barras["Total adeudado por clientes"]["izquierda"] == 50.0
    assert barras["Total adeudado por clientes"]["ancho"] == 50.0
    assert barras["Efectivo libre real"]["izquierda"] == 33.33
    assert barras["Efectivo libre real"]["ancho"] == 16.67


def test_barras_sin_deficit_crecen_desde_la_izquierda() -> None:
    """Sin valores negativos la escala empieza en cero y la barra mayor llena la pista."""
    resumen = {
        "cartera_clientes": Decimal("60000"),
        "deuda_proveedor": Decimal("30000"),
        "balance": Decimal("30000"),
        "caja_recaudada": Decimal("30000"),
        "efectivo_libre": Decimal("0"),
    }

    barras = {barra["etiqueta"]: barra for barra in comercial.barras_balance(resumen)}

    assert barras["Total adeudado por clientes"]["izquierda"] == 0.0
    assert barras["Total adeudado por clientes"]["ancho"] == 100.0
    assert barras["Total adeudado al proveedor"]["ancho"] == 50.0
    assert barras["Efectivo libre real"]["ancho"] == 0.0


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


def test_segmentos_dona_marcan_cartera_en_verde_y_deuda_en_rojo() -> None:
    """SRS v1.8: la leyenda de la dona usa verde a favor y rojo en contra."""
    arcos = comercial.segmentos_dona(Decimal("60000"), Decimal("40000"))

    assert arcos[0]["clase"] == "valor-positivo"
    assert arcos[1]["clase"] == "valor-negativo"


def test_desglose_de_deuda_separa_pasivo_anterior_de_ventas_del_sistema(bd) -> None:
    """El abono paga primero la deuda de ventas y solo luego el pasivo viejo."""
    comercial.registrar_deuda_inicial(bd, "100000", "Pasivo viejo")
    _venta(bd, precio="200000", costo="150000")
    comercial.registrar_abono_proveedor(bd, "50000")

    desglose = comercial.desglose_deuda_proveedor(bd)
    assert desglose["anteriores_valor"] == Decimal("100000")
    assert desglose["ventas_valor"] == Decimal("100000")
    assert desglose["total"] == Decimal("200000")
    assert desglose["total"] == comercial.deuda_proveedor(bd)
    assert desglose["anteriores_porcentaje"] == 50.0
    assert desglose["ventas_porcentaje"] == 50.0


def test_desglose_con_abono_excedente_reduce_el_pasivo(bd) -> None:
    """Si el abono supera la deuda de ventas, el sobrante baja el pasivo antiguo."""
    comercial.registrar_deuda_inicial(bd, "100000", "Pasivo viejo")
    _venta(bd, precio="200000", costo="50000")
    comercial.registrar_abono_proveedor(bd, "70000")

    desglose = comercial.desglose_deuda_proveedor(bd)
    assert desglose["ventas_valor"] == Decimal("0")
    assert desglose["anteriores_valor"] == Decimal("80000")
    assert desglose["total"] == Decimal("80000")
    assert desglose["ventas_porcentaje"] == 0.0
    assert desglose["anteriores_porcentaje"] == 100.0


def test_leyenda_de_la_dona_muestra_el_desglose(cliente_admin: TestClient, bd) -> None:
    """La leyenda de «Deuda con proveedor» incluye las dos partes con su porcentaje."""
    comercial.registrar_deuda_inicial(bd, "100000", "Pasivo viejo")
    _venta(bd, precio="200000", costo="50000")

    html = cliente_admin.get("/olb-byte/cartera").text
    assert "Deudas anteriores al sistema" in html
    assert "Deuda de ventas actuales" in html
    assert "% de la deuda" in html
    assert "dona__desglose" in html


def test_panel_de_cartera_muestra_balance_y_dona(cliente_admin: TestClient, bd) -> None:
    """La vista presenta el balance, la gráfica y el libro del proveedor."""
    _venta(bd, precio="50000", costo="20000")

    respuesta = cliente_admin.get("/olb-byte/cartera")

    assert respuesta.status_code == 200
    assert "Balance" in respuesta.text
    assert "dona__svg" in respuesta.text
    assert "Compra a crédito" in respuesta.text
    assert "$50.000" in respuesta.text
    # El balance del centro de la dona lleva clase de color según su signo.
    assert "dona__centro-valor" in respuesta.text


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

