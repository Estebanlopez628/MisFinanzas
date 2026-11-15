"""Pruebas del módulo comercial OLB_BYTE (bloque B).

Cubren inventario, clientes, ventas multipartida con descuento de stock,
abonos, cartera, enlace de WhatsApp y la factura imprimible.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import comercial


def _producto(
    bd,
    sku: str = "OLB-001",
    precio: str = "50.000",
    stock: int = 10,
    costo: str = "30.000",
):
    """Crea un producto de apoyo para las pruebas.

    Args:
        bd: Sesión de base de datos.
        sku: Código único del producto.
        precio: Precio de venta en formato colombiano.
        stock: Unidades iniciales.
        costo: Costo de compra.

    Returns:
        El producto persistido.
    """
    return comercial.crear_producto(
        bd, sku, f"Producto {sku}", precio, costo, stock, garantia_meses=6
    )


def test_crear_producto_normaliza_sku_y_precio(bd) -> None:
    """El SKU se guarda en mayúsculas y el precio como `Decimal`."""
    producto = comercial.crear_producto(
        bd, " olb-100 ", "Cargador", "45.900", "20.000", 7, 12
    )

    assert producto.sku == "OLB-100"
    assert producto.precio_venta == Decimal("45900.00")
    assert producto.costo == Decimal("20000.00")
    assert producto.stock == 7
    assert producto.garantia_meses == 12
    assert comercial.listar_productos(bd) == [producto]


def test_producto_duplicado_o_invalido_se_rechaza(bd) -> None:
    """No se repite el SKU ni se aceptan stock o precios negativos."""
    _producto(bd, "OLB-001")

    try:
        _producto(bd, "olb-001")
    except ValueError as error:
        assert "SKU" in str(error)
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError por SKU duplicado")

    try:
        comercial.crear_producto(bd, "OLB-002", "Otro", "-1", "0", 1)
    except ValueError as error:
        assert "negativos" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError por precio negativo")

    try:
        comercial.crear_producto(bd, "OLB-003", "Otro", "1000", "0", -2)
    except ValueError as error:
        assert "stock" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError por stock negativo")


def test_cliente_exige_nombre(bd) -> None:
    """El nombre es obligatorio para registrar un cliente."""
    try:
        comercial.crear_cliente(bd, "   ")
    except ValueError as error:
        assert "nombre" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")

    cliente = comercial.crear_cliente(bd, "Cliente Demo", "3001234567")
    assert cliente.nombre == "Cliente Demo"
    assert comercial.listar_clientes(bd) == [cliente]


def test_venta_multipartida_descuenta_stock_y_suma(bd) -> None:
    """Dos líneas descuentan stock y el total es la suma de subtotales."""
    primero = _producto(bd, "OLB-001", "50.000", 10)
    segundo = _producto(bd, "OLB-002", "20.000", 5)
    cliente = comercial.crear_cliente(bd, "Cliente Demo")

    venta = comercial.registrar_venta(
        bd,
        cliente.id_cliente,
        [
            comercial.LineaVenta(primero.id_producto, 2),
            comercial.LineaVenta(segundo.id_producto, 1, Decimal("18000")),
        ],
    )

    assert venta.total == Decimal("118000.00")
    assert venta.saldo_pendiente == Decimal("118000.00")
    assert venta.estado == comercial.ESTADO_PENDIENTE
    assert bd.get(type(primero), primero.id_producto).stock == 8
    assert bd.get(type(segundo), segundo.id_producto).stock == 4


def test_venta_sin_stock_falla(bd) -> None:
    """No se puede vender más unidades de las disponibles."""
    producto = _producto(bd, "OLB-001", stock=1)
    cliente = comercial.crear_cliente(bd, "Cliente Demo")

    try:
        comercial.registrar_venta(
            bd, cliente.id_cliente, [comercial.LineaVenta(producto.id_producto, 2)]
        )
    except ValueError as error:
        assert "stock" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError por stock insuficiente")
    finally:
        bd.rollback()


def test_venta_sin_lineas_falla(bd) -> None:
    """Una venta vacía no se registra."""
    cliente = comercial.crear_cliente(bd, "Cliente Demo")

    try:
        comercial.registrar_venta(bd, cliente.id_cliente, [])
    except ValueError as error:
        assert "al menos un producto" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_abonos_parciales_y_totales_actualizan_estado(bd) -> None:
    """Un abono parcial deja PARCIAL y el total marca PAGADA."""
    producto = _producto(bd, "OLB-001", "100.000", 5)
    cliente = comercial.crear_cliente(bd, "Cliente Demo")
    venta = comercial.registrar_venta(
        bd, cliente.id_cliente, [comercial.LineaVenta(producto.id_producto, 1)]
    )

    comercial.registrar_abono(bd, venta.id_venta, "40.000", "NEQUI")
    bd.refresh(venta)
    assert venta.saldo_pendiente == Decimal("60000.00")
    assert venta.estado == comercial.ESTADO_PARCIAL
    assert comercial.cartera(bd) == [venta]

    comercial.registrar_abono(bd, venta.id_venta, "60.000", "TARJETA")
    bd.refresh(venta)
    assert venta.saldo_pendiente == Decimal("0.00")
    assert venta.estado == comercial.ESTADO_PAGADA
    assert comercial.cartera(bd) == []


def test_abono_invalido_se_rechaza(bd) -> None:
    """El monto debe ser positivo, no superar el saldo y usar un método válido."""
    producto = _producto(bd, "OLB-001", "100.000", 5)
    cliente = comercial.crear_cliente(bd, "Cliente Demo")
    venta = comercial.registrar_venta(
        bd, cliente.id_cliente, [comercial.LineaVenta(producto.id_producto, 1)]
    )

    for monto, fragmento in (
        ("0", "mayor que cero"),
        ("200.000", "superar"),
    ):
        try:
            comercial.registrar_abono(bd, venta.id_venta, monto)
        except ValueError as error:
            assert fragmento in str(error).lower()
        else:  # pragma: no cover - protección contra regresiones
            raise AssertionError(f"Se esperaba ValueError para {monto}")

    try:
        comercial.registrar_abono(bd, venta.id_venta, "10.000", "BITCOIN")
    except ValueError as error:
        assert "método de pago" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError por método inválido")


def test_resumen_comercial_agrega_ventas_y_stock(bd) -> None:
    """El resumen informa ventas, cartera, productos y stock bajo."""
    producto = _producto(bd, "OLB-001", "100.000", 2)
    cliente = comercial.crear_cliente(bd, "Cliente Demo")
    venta = comercial.registrar_venta(
        bd, cliente.id_cliente, [comercial.LineaVenta(producto.id_producto, 1)]
    )
    comercial.registrar_abono(bd, venta.id_venta, "25.000")

    resumen = comercial.resumen_comercial(bd)
    assert resumen["ventas_totales"] == Decimal("100000.00")
    assert resumen["cartera"] == Decimal("75000.00")
    assert resumen["numero_ventas"] == 1
    assert resumen["productos"] == 1
    assert resumen["stock_bajo"] == 1


def test_eliminar_producto_valida_ventas(bd) -> None:
    """Un producto vendido no se puede borrar; uno libre sí."""
    vendido = _producto(bd, "OLB-001", stock=2)
    libre = _producto(bd, "OLB-002", stock=2)
    cliente = comercial.crear_cliente(bd, "Cliente Demo")
    comercial.registrar_venta(
        bd, cliente.id_cliente, [comercial.LineaVenta(vendido.id_producto, 1)]
    )

    try:
        comercial.eliminar_producto(bd, vendido.id_producto)
    except ValueError as error:
        assert "ventas registradas" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")

    assert comercial.eliminar_producto(bd, libre.id_producto) is True
    assert comercial.eliminar_producto(bd, "no-existe") is False


def test_enlace_whatsapp_incluye_indicativo_y_detalle(bd) -> None:
    """El enlace usa el indicativo 57 y codifica el resumen de la factura."""
    producto = _producto(bd, "OLB-001", "50.000", 3)
    cliente = comercial.crear_cliente(bd, "Cliente Demo", "3001234567")
    venta = comercial.registrar_venta(
        bd, cliente.id_cliente, [comercial.LineaVenta(producto.id_producto, 1)]
    )
    lineas = [
        {"nombre": producto.nombre, "cantidad": 1, "subtotal": venta.total},
    ]

    enlace = comercial.enlace_whatsapp_factura(venta, cliente, lineas)
    assert enlace.startswith("https://wa.me/573001234567?text=")
    assert "OLB_BYTE" in enlace
    assert "Cargador" in enlace or "Producto" in enlace


def test_vista_comercial_registra_y_muestra_factura(cliente_admin: TestClient) -> None:
    """El flujo completo del panel: producto, cliente, venta y factura."""
    assert (
        cliente_admin.post(
            "/olb-byte/productos",
            data={
                "sku": "OLB-777",
                "nombre": "Cargador rápido",
                "costo": "10.000",
                "precio_venta": "45.000",
                "stock": "4",
                "garantia_meses": "6",
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        cliente_admin.post(
            "/olb-byte/clientes",
            data={"nombre": "Cliente Vista", "telefono_whatsapp": "3009998877"},
            follow_redirects=False,
        ).status_code
        == 303
    )

    panel = cliente_admin.get("/olb-byte").text
    assert "OLB-777" in panel
    assert "Cargador rápido" in panel
    assert "Cliente Vista" in panel

    from app.core.base_datos import FabricaSesiones

    with FabricaSesiones() as bd:
        producto = comercial.listar_productos(bd)[0]
        cliente = comercial.listar_clientes(bd)[0]
        id_producto = producto.id_producto
        id_cliente = cliente.id_cliente

    respuesta = cliente_admin.post(
        "/olb-byte/ventas",
        data={
            "id_cliente": id_cliente,
            "id_producto": id_producto,
            "cantidad": "2",
            "precio_unitario": "",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303

    with FabricaSesiones() as bd:
        venta = comercial.listar_ventas(bd)[0]
        assert venta.total == Decimal("90000.00")
        id_venta = venta.id_venta

    factura = cliente_admin.get(f"/olb-byte/factura/{id_venta}")
    assert factura.status_code == 200
    assert "Factura de venta" in factura.text
    assert "Cargador rápido" in factura.text
    assert "90.000" in factura.text

    assert cliente_admin.get("/olb-byte/factura/no-existe").status_code == 404


def test_vista_comercial_rechaza_venta_vacia(cliente_admin: TestClient) -> None:
    """Sin líneas seleccionadas el panel responde 400 con el motivo."""
    respuesta = cliente_admin.post(
        "/olb-byte/ventas",
        data={"id_cliente": "no-existe", "id_producto": "", "cantidad": "1"},
    )

    assert respuesta.status_code == 400
    assert "cliente" in respuesta.text.lower()


def test_usuario_publico_no_accede_al_modulo_comercial(
    cliente_usuario: TestClient,
) -> None:
    """El RBAC bloquea lectura y escritura del módulo OLB_BYTE."""
    assert cliente_usuario.get("/olb-byte").status_code == 403
    assert (
        cliente_usuario.post(
            "/olb-byte/productos",
            data={"sku": "X", "nombre": "X", "precio_venta": "1"},
        ).status_code
        == 403
    )
