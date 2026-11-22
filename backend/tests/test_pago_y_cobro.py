"""Pruebas de la forma de pago, el anticipo, la gestión de cobro y la tabla de órdenes.

Cubren los ajustes de validación 3: pago de contado o a crédito con anticipo que entra
en la factura, la página de cobro con sus dos opciones, y que la tabla de órdenes solo
muestre el total (la ganancia y el saldo quedan ocultos).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.modelos import Abono
from app.servicios import comercial


def _datos(**extra: object) -> dict[str, object]:
    """Formulario de venta con un producto de 50.000 y costo 30.000.

    Args:
        **extra: Campos a sobrescribir o agregar.

    Returns:
        Datos listos para enviar con `TestClient.post`.
    """
    datos: dict[str, object] = {
        "cliente_nombre": "Ana Pérez",
        "cliente_telefono": "3001234567",
        "producto_nombre": ["Audífonos BT"],
        "categoria": ["Audio"],
        "cantidad": ["1"],
        "costo_unitario": ["30000"],
        "precio_unitario": ["50000"],
        "garantia_meses": ["3"],
        "forma_pago": "CONTADO",
        "metodo_pago": "EFECTIVO",
    }
    datos.update(extra)
    return datos


def _ultima_venta(bd):
    """Devuelve la orden más reciente.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Orden con el consecutivo más alto.
    """
    return comercial.listar_ventas(bd)[0]


def test_contado_cobra_el_total_al_registrar(cliente_admin: TestClient, bd) -> None:
    """Un pago de contado queda cobrado: abono por el total y saldo en cero."""
    respuesta = cliente_admin.post("/olb-byte/ventas", data=_datos(), follow_redirects=False)

    assert respuesta.status_code == 303
    venta = _ultima_venta(bd)
    abono = bd.query(Abono).one()
    assert abono.monto == Decimal("50000")
    assert abono.metodo_pago == "EFECTIVO"
    assert venta.saldo_pendiente == Decimal("0")
    assert venta.estado_pago == comercial.ESTADO_PAGO_PAGADA


def test_credito_sin_anticipo_no_registra_pago(cliente_admin: TestClient, bd) -> None:
    """Un pago a crédito sin anticipo deja toda la venta pendiente."""
    cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(forma_pago="CREDITO", anticipo="NO"),
        follow_redirects=False,
    )

    venta = _ultima_venta(bd)
    assert bd.query(Abono).count() == 0
    assert venta.saldo_pendiente == Decimal("50000")
    assert venta.estado_pago == comercial.ESTADO_PAGO_PENDIENTE


def test_anticipo_entra_en_la_venta_con_su_metodo(cliente_admin: TestClient, bd) -> None:
    """El anticipo se registra con la venta y descuenta el saldo."""
    cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(
            forma_pago="CREDITO",
            anticipo="SI",
            monto_anticipo="20.000",
            metodo_anticipo="TRANSFERENCIA",
        ),
        follow_redirects=False,
    )

    venta = _ultima_venta(bd)
    abono = bd.query(Abono).one()
    assert abono.monto == Decimal("20000")
    assert abono.metodo_pago == "TRANSFERENCIA"
    assert venta.total_abonado == Decimal("20000")
    assert venta.saldo_pendiente == Decimal("30000")
    assert venta.estado_pago == comercial.ESTADO_PAGO_PARCIAL


def test_anticipo_mayor_que_el_total_se_rechaza_sin_crear_la_venta(cliente_admin: TestClient, bd) -> None:
    """Un anticipo por encima del total devuelve error y no deja ninguna orden."""
    respuesta = cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(forma_pago="CREDITO", anticipo="SI", monto_anticipo="60000", metodo_anticipo="EFECTIVO"),
    )

    assert respuesta.status_code == 400
    assert "no puede superar el total" in respuesta.text
    assert comercial.listar_ventas(bd) == []


def test_anticipo_sin_valor_pide_el_monto(cliente_admin: TestClient, bd) -> None:
    """Si el cliente hace anticipo, el valor es obligatorio."""
    respuesta = cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(forma_pago="CREDITO", anticipo="SI", monto_anticipo="", metodo_anticipo="EFECTIVO"),
    )

    assert respuesta.status_code == 400
    assert "Escribe el valor del anticipo" in respuesta.text


def test_contado_sin_metodo_de_pago_muestra_error(cliente_admin: TestClient, bd) -> None:
    """Un pago de contado necesita Transferencia o Efectivo."""
    respuesta = cliente_admin.post("/olb-byte/ventas", data=_datos(metodo_pago=""))

    assert respuesta.status_code == 400
    assert "Transferencia o Efectivo" in respuesta.text
    assert comercial.listar_ventas(bd) == []


def test_forma_de_pago_invalida_se_rechaza(cliente_admin: TestClient, bd) -> None:
    """Solo se acepta pago de contado o a crédito."""
    respuesta = cliente_admin.post("/olb-byte/ventas", data=_datos(forma_pago="TARJETA"))

    assert respuesta.status_code == 400
    assert "de contado o a crédito" in respuesta.text


def test_pago_a_credito_con_anticipo_muestra_el_formulario_de_cobro(cliente_admin: TestClient, bd) -> None:
    """La página de cobro muestra saldo, abonado y las dos opciones."""
    cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(forma_pago="CREDITO", anticipo="SI", monto_anticipo="10.000", metodo_anticipo="EFECTIVO"),
        follow_redirects=False,
    )
    venta = _ultima_venta(bd)

    respuesta = cliente_admin.get(f"/olb-byte/ventas/{venta.id_venta}/cobro")

    assert respuesta.status_code == 200
    assert "Registrar Abono / Pago Total" in respuesta.text
    assert "Opción 2 · Recordatorio por WhatsApp" in respuesta.text
    assert "Registrar Pago" in respuesta.text
    assert "Enviar recordatorio por WhatsApp" in respuesta.text
    assert "$40.000" in respuesta.text
    assert "Saldo por pagar" in respuesta.text


def test_cobro_cancelar_vuelve_a_pendientes(cliente_admin: TestClient, bd) -> None:
    """El botón Cancelar de la gestión de cobro regresa a pendientes de pago."""
    cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(forma_pago="CREDITO", anticipo="NO"),
        follow_redirects=False,
    )
    venta = _ultima_venta(bd)

    texto = cliente_admin.get(f"/olb-byte/ventas/{venta.id_venta}/cobro").text

    assert 'class="boton boton--cancelar"' in texto
    assert "/olb-byte/pendientes" in texto


def test_pago_registrado_desde_el_cobro_abre_el_recibo(cliente_admin: TestClient, bd) -> None:
    """Registrar el pago desde la gestión de cobro lleva al recibo del abono."""
    cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(forma_pago="CREDITO", anticipo="NO"),
        follow_redirects=False,
    )
    venta = _ultima_venta(bd)

    respuesta = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/abonos",
        data={"monto": "50.000", "metodo_pago": "TRANSFERENCIA", "desde_cobro": "1"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    abono = bd.query(Abono).one()
    assert respuesta.headers["location"] == f"/olb-byte/recibos/{abono.id_abono}"


def test_error_al_cobrar_se_muestra_en_la_gestion_de_cobro(cliente_admin: TestClient, bd) -> None:
    """Un monto mayor al saldo vuelve a la página de cobro, no a la lista."""
    cliente_admin.post(
        "/olb-byte/ventas",
        data=_datos(forma_pago="CREDITO", anticipo="NO"),
        follow_redirects=False,
    )
    venta = _ultima_venta(bd)

    respuesta = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/abonos",
        data={"monto": "99.000", "metodo_pago": "EFECTIVO", "desde_cobro": "1"},
    )

    assert respuesta.status_code == 400
    assert "Registrar Abono / Pago Total" in respuesta.text
    assert "no puede superar el saldo pendiente" in respuesta.text


def test_factura_saldada_no_ofrece_formulario_de_pago(cliente_admin: TestClient, bd) -> None:
    """Una venta de contado ya cobrada no muestra el formulario de pago."""
    cliente_admin.post("/olb-byte/ventas", data=_datos(), follow_redirects=False)
    venta = _ultima_venta(bd)

    texto = cliente_admin.get(f"/olb-byte/ventas/{venta.id_venta}/cobro").text

    assert "ya está pagada" in texto
    assert 'name="monto"' not in texto


def test_tabla_de_ordenes_muestra_solo_el_total(cliente_admin: TestClient, bd) -> None:
    """La ganancia y el saldo no aparecen en la tabla de órdenes."""
    cliente_admin.post("/olb-byte/ventas", data=_datos(forma_pago="CREDITO", anticipo="NO"), follow_redirects=False)

    texto = cliente_admin.get("/olb-byte").text

    assert '<th scope="col">Ganancia</th>' not in texto
    assert '<th scope="col">Saldo</th>' not in texto
    assert '<th scope="col">Total</th>' in texto


def test_acciones_de_orden_van_en_fila_con_whatsapp_adjunto(cliente_admin: TestClient, bd) -> None:
    """Factura, WhatsApp y Anular van en una misma fila y WhatsApp envía el PDF."""
    cliente_admin.post("/olb-byte/ventas", data=_datos(), follow_redirects=False)

    texto = cliente_admin.get("/olb-byte").text

    assert 'class="acciones-orden"' in texto
    assert "data-compartir-factura" in texto
    assert 'data-texto="Hola Ana Pérez, adjunto tu factura de compra."' in texto
    assert "Factura_OLB_BYTE_No_1_Ana_Perez.png" in texto


def test_formulario_muestra_categoria_antes_del_nombre_y_pago(cliente_admin: TestClient) -> None:
    """Categoría va a la izquierda del nombre; la forma de pago aparece en el formulario."""
    texto = cliente_admin.get("/olb-byte").text

    assert texto.index('campo__etiqueta">Categoría') < texto.index('campo__etiqueta">Nombre del producto')
    assert 'name="forma_pago"' in texto
    assert 'name="metodo_pago"' in texto
    assert 'name="anticipo"' in texto
    assert 'name="metodo_anticipo"' in texto


def test_agregar_y_registrar_tienen_el_mismo_tamano(cliente_admin: TestClient) -> None:
    """«+ Agregar otro producto» y «Registrar venta» comparten la clase de tamaño."""
    texto = cliente_admin.get("/olb-byte").text

    assert texto.count('class="boton boton--primario boton--venta"') == 2
    assert "+ Agregar otro producto" in texto
    assert 'data-guardar-producto' in texto


def test_no_hay_formulario_de_nuevo_cliente(cliente_admin: TestClient) -> None:
    """El alta manual de clientes ya no aparece en el panel."""
    assert "Nuevo cliente" not in cliente_admin.get("/olb-byte").text
