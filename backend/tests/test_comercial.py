"""Pruebas del servicio comercial OLB_BYTE sin inventario (ADR-35).

Cubren consecutivo, copia de datos en la venta, deuda con el proveedor, abonos
con fecha y hora, anulación con devolución, cartera y caja. Las rutas HTTP se
prueban en la fase del formulario de venta.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.modelos import MovimientoProveedor
from app.servicios import comercial

UTC = timezone.utc


def _linea(nombre: str = "Audífonos BT", cantidad: int = 1, precio: str = "50000", costo: str = "30000", meses: int = 3):
    """Crea una línea de venta con valores de prueba.

    Args:
        nombre: Nombre del producto.
        cantidad: Unidades.
        precio: Precio al cliente.
        costo: Precio del proveedor.
        meses: Meses de garantía.

    Returns:
        Línea lista para `registrar_venta`.
    """
    return comercial.LineaVenta(
        nombre=nombre,
        cantidad=cantidad,
        precio_unitario=precio,
        costo_unitario=costo,
        garantia_meses=meses,
    )


def _venta(bd, lineas=None, nombre="Ana Pérez", telefono="3001234567", fecha=None):
    """Registra una venta de prueba.

    Args:
        bd: Sesión de base de datos.
        lineas: Líneas; por defecto un producto.
        nombre: Nombre del cliente.
        telefono: Celular del cliente.
        fecha: Fecha de la venta.

    Returns:
        La orden persistida.
    """
    return comercial.registrar_venta(
        bd,
        nombre,
        telefono,
        lineas or [_linea()],
        fecha or datetime(2026, 11, 10, 15, 0, tzinfo=UTC),
    )


def test_normalizar_telefono_acepta_formatos_de_agenda() -> None:
    """Quita espacios, guiones e indicativo 57 y deja 10 dígitos."""
    assert comercial.normalizar_telefono("300 123 4567") == "3001234567"
    assert comercial.normalizar_telefono("+57 300-123-4567") == "3001234567"
    assert comercial.normalizar_telefono("573001234567") == "3001234567"
    assert comercial.normalizar_telefono("") is None
    assert comercial.normalizar_telefono(None) is None


def test_normalizar_telefono_rechaza_longitud_incorrecta() -> None:
    """Un número que no suma 10 dígitos se rechaza."""
    with pytest.raises(ValueError, match="10 dígitos"):
        comercial.normalizar_telefono("300123")


def test_consecutivo_empieza_en_uno_y_avanza(bd) -> None:
    """La primera orden es la 1 y la siguiente la 2."""
    primera = _venta(bd)
    segunda = _venta(bd, nombre="Luis")

    assert primera.numero_orden == 1
    assert segunda.numero_orden == 2


def test_venta_calcula_totales_ganancia_y_copia_datos(bd) -> None:
    """Totales, costo y ganancia salen de las líneas; el nombre se copia en la orden."""
    lineas = [
        _linea("Cargador", cantidad=2, precio="25000", costo="15000"),
        _linea("Cable", cantidad=1, precio="18000", costo="10000"),
    ]
    venta = _venta(bd, lineas=lineas)

    assert venta.total == Decimal("68000")
    assert venta.total_costo == Decimal("40000")
    assert venta.ganancia_neta == Decimal("28000")
    assert venta.saldo_pendiente == Decimal("68000")
    assert venta.estado_pago == comercial.ESTADO_PAGO_PENDIENTE
    assert venta.cliente_nombre == "Ana Pérez"
    assert venta.cliente_telefono == "3001234567"


def test_venta_genera_deuda_con_proveedor(bd) -> None:
    """Cada venta suma su costo a la deuda con el proveedor."""
    _venta(bd, lineas=[_linea(cantidad=2, costo="30000")])

    assert comercial.deuda_proveedor(bd) == Decimal("60000")
    movimiento = bd.query(MovimientoProveedor).one()
    assert movimiento.tipo == comercial.TIPO_COMPRA
    assert movimiento.saldo_resultante == Decimal("60000")


def test_garantia_vence_al_sumar_meses_con_ajuste_de_fin_de_mes(bd) -> None:
    """Enero 31 más tres meses vence el 30 de abril, no en un día inexistente."""
    venta = _venta(bd, fecha=datetime(2026, 1, 31, 12, 0, tzinfo=UTC))

    assert venta.garantia_fecha_fin == date(2026, 4, 30)
    assert venta.garantia_texto == "3 meses por defectos de fábrica"


def test_garantia_usa_la_hora_de_colombia(bd) -> None:
    """Una venta a las 11 p. m. del 28 de febrero (hora Colombia) cuenta ese día local.

    En UTC es 1 de marzo a las 04:00; si se usara UTC, la garantía de un mes vencería
    el 1 de abril en lugar del 28 de marzo.
    """
    venta = _venta(bd, lineas=[_linea(meses=1)], fecha=datetime(2026, 3, 1, 4, 0, tzinfo=UTC))

    assert venta.garantia_fecha_fin == date(2026, 3, 28)


def test_linea_sin_garantia_vence_el_mismo_dia(bd) -> None:
    """Con cero meses la garantía no sirve y el semáforo queda en rojo desde el primer día."""
    venta = _venta(bd, lineas=[_linea(meses=0)], fecha=datetime(2026, 5, 10, 15, 0, tzinfo=UTC))

    assert venta.garantia_texto == "Sin garantía"
    assert venta.garantia_fecha_fin == date(2026, 5, 10)


def test_cliente_se_reutiliza_por_celular(bd) -> None:
    """Dos ventas con el mismo celular comparten el cliente aunque el nombre cambie."""
    primera = _venta(bd, nombre="Ana Pérez", telefono="3001234567")
    segunda = _venta(bd, nombre="Ana P.", telefono="300 123 4567")

    assert primera.id_cliente == segunda.id_cliente
    assert len(comercial.listar_clientes(bd)) == 1


def test_mismo_nombre_con_otro_celular_crea_otro_cliente(bd) -> None:
    """Dos personas con el mismo nombre y distinto celular no se mezclan."""
    primera = _venta(bd, nombre="Juan", telefono="3001111111")
    segunda = _venta(bd, nombre="Juan", telefono="3002222222")

    assert primera.id_cliente != segunda.id_cliente


def test_venta_sin_nombre_o_sin_lineas_falla(bd) -> None:
    """Sin nombre de cliente o sin productos la venta no se registra."""
    with pytest.raises(ValueError, match="nombre del cliente"):
        comercial.registrar_venta(bd, "  ", None, [_linea()])
    with pytest.raises(ValueError, match="al menos un producto"):
        comercial.registrar_venta(bd, "Ana", None, [])


def test_linea_invalida_no_persiste_la_venta(bd) -> None:
    """Una cantidad cero deja la base limpia: no queda orden ni deuda."""
    with pytest.raises(ValueError, match="cantidad"):
        _venta(bd, lineas=[_linea(cantidad=0)])

    assert comercial.listar_ventas(bd) == []
    assert comercial.deuda_proveedor(bd) == Decimal("0")


def test_abonos_parciales_y_total_cambian_el_estado(bd) -> None:
    """Un abono parcial deja la orden en PARCIAL y el total la marca como PAGADA."""
    venta = _venta(bd)
    comercial.registrar_abono(bd, venta.id_venta, "20000", "EFECTIVO")

    assert venta.estado_pago == comercial.ESTADO_PAGO_PARCIAL
    assert venta.saldo_pendiente == Decimal("30000")

    comercial.registrar_abono(bd, venta.id_venta, "30.000", "TRANSFERENCIA")

    assert venta.estado_pago == comercial.ESTADO_PAGO_PAGADA
    assert venta.saldo_pendiente == Decimal("0")
    assert comercial.cartera(bd) == []


def test_abono_guarda_fecha_y_hora(bd) -> None:
    """El abono conserva la fecha y hora indicadas (RF-06)."""
    venta = _venta(bd)
    momento = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)

    abono = comercial.registrar_abono(bd, venta.id_venta, "10000", "EFECTIVO", momento)

    assert abono.fecha_abono.replace(tzinfo=None) == momento.replace(tzinfo=None)


def test_abono_rechaza_monto_excesivo_metodo_no_permitido_y_orden_anulada(bd) -> None:
    """Solo Efectivo o Transferencia, sin superar el saldo y sin abonar órdenes anuladas."""
    venta = _venta(bd)
    with pytest.raises(ValueError, match="superar el saldo"):
        comercial.registrar_abono(bd, venta.id_venta, "99999999")
    with pytest.raises(ValueError, match="Efectivo o Transferencia"):
        comercial.registrar_abono(bd, venta.id_venta, "1000", "NEQUI")

    comercial.anular_venta(bd, venta.id_venta, "Error de digitación")
    with pytest.raises(ValueError, match="anulada"):
        comercial.registrar_abono(bd, venta.id_venta, "1000")


def test_anular_conserva_consecutivo_y_no_revierte_deuda(bd) -> None:
    """Anular saca la orden de cartera, mantiene el número y la deuda con el proveedor."""
    anulada = _venta(bd, lineas=[_linea(costo="30000")])
    siguiente = _venta(bd)

    comercial.anular_venta(bd, anulada.id_venta, "Cliente desistió")

    assert anulada.estado_orden == comercial.ESTADO_ANULADA
    assert anulada.saldo_pendiente == Decimal("0")
    assert anulada.ganancia_neta == Decimal("0")
    assert anulada.numero_orden == 1
    assert siguiente.numero_orden == 2
    assert comercial.deuda_proveedor(bd) == Decimal("60000")
    assert comercial.cartera(bd) == [siguiente]


def test_anular_exige_motivo_y_no_se_hace_dos_veces(bd) -> None:
    """La anulación pide motivo y una orden anulada no se vuelve a anular."""
    venta = _venta(bd)
    with pytest.raises(ValueError, match="motivo"):
        comercial.anular_venta(bd, venta.id_venta, "   ")

    comercial.anular_venta(bd, venta.id_venta, "Duplicada")
    with pytest.raises(ValueError, match="ya está anulada"):
        comercial.anular_venta(bd, venta.id_venta, "Otra vez")


def test_anular_registra_devolucion_del_dinero_abonado(bd) -> None:
    """Si el cliente ya abonó, la anulación registra la devolución y calcula lo pendiente."""
    venta = _venta(bd)
    comercial.registrar_abono(bd, venta.id_venta, "40000", "EFECTIVO")

    comercial.anular_venta(bd, venta.id_venta, "Producto no disponible", "25000", "TRANSFERENCIA")

    assert comercial.pendiente_devolver(bd, venta) == Decimal("15000")
    assert comercial.resumen_cartera(bd)["caja_recaudada"] == Decimal("15000")


def test_devolucion_no_supera_lo_abonado(bd) -> None:
    """La devolución no puede superar lo abonado por el cliente."""
    venta = _venta(bd)
    comercial.registrar_abono(bd, venta.id_venta, "10000")

    with pytest.raises(ValueError, match="no puede superar"):
        comercial.anular_venta(bd, venta.id_venta, "Error", "20000")


def test_devolucion_pendiente_se_registra_despues(bd) -> None:
    """Lo que no se devolvió al anular se puede registrar después, hasta completar."""
    venta = _venta(bd)
    comercial.registrar_abono(bd, venta.id_venta, "40000")
    comercial.anular_venta(bd, venta.id_venta, "Cambio de planes")

    comercial.registrar_devolucion(bd, venta.id_venta, "15000", "EFECTIVO")
    assert comercial.pendiente_devolver(bd, venta) == Decimal("25000")

    with pytest.raises(ValueError, match="supera"):
        comercial.registrar_devolucion(bd, venta.id_venta, "30000")


def test_devolucion_solo_en_ordenes_anuladas(bd) -> None:
    """Una orden activa no admite devolución: primero debe anularse."""
    venta = _venta(bd)
    with pytest.raises(ValueError, match="anuladas"):
        comercial.registrar_devolucion(bd, venta.id_venta, "1000")


def test_abono_a_proveedor_reduce_la_deuda_y_no_la_supera(bd) -> None:
    """El abono al proveedor baja la deuda y no puede pagar más de lo que se debe."""
    _venta(bd, lineas=[_linea(costo="30000", cantidad=2)])

    comercial.registrar_abono_proveedor(bd, "20000", "Pago parcial local")
    assert comercial.deuda_proveedor(bd) == Decimal("40000")

    with pytest.raises(ValueError, match="supera la deuda"):
        comercial.registrar_abono_proveedor(bd, "50000")


def test_resumen_cartera_calcula_balance_y_efectivo_libre(bd) -> None:
    """Balance = cartera − deuda; efectivo libre = caja − deuda (RF-09)."""
    venta = _venta(bd, lineas=[_linea(precio="50000", costo="30000", cantidad=2)])
    comercial.registrar_abono(bd, venta.id_venta, "40000")
    comercial.registrar_abono_proveedor(bd, "10000")

    resumen = comercial.resumen_cartera(bd)

    assert resumen["cartera_clientes"] == Decimal("60000")
    assert resumen["deuda_proveedor"] == Decimal("50000")
    assert resumen["balance"] == Decimal("10000")
    assert resumen["caja_recaudada"] == Decimal("30000")
    assert resumen["efectivo_libre"] == Decimal("-20000")


def test_buscar_clientes_por_nombre_o_celular(bd) -> None:
    """El autocompletado encuentra clientes por nombre y por celular."""
    _venta(bd, nombre="María López", telefono="3001234567")
    _venta(bd, nombre="Carlos Ruiz", telefono="3109876543")

    assert [c.nombre for c in comercial.buscar_clientes(bd, "maría")] == ["María López"]
    assert [c.nombre for c in comercial.buscar_clientes(bd, "9876")] == ["Carlos Ruiz"]
    assert comercial.buscar_clientes(bd, "   ") == []


def test_enlace_whatsapp_usa_el_celular_guardado_con_indicativo(bd) -> None:
    """El enlace de factura y de cobro apunta al número con 57 y lleva el saldo."""
    venta = _venta(bd)

    factura = comercial.enlace_whatsapp_factura(
        venta, [{"nombre": "Audífonos BT", "cantidad": 1, "subtotal": Decimal("50000")}]
    )
    cobro = comercial.enlace_whatsapp_cobro(venta)

    assert factura.startswith("https://wa.me/573001234567?text=")
    assert "Factura%20No.%201" in factura
    assert "%2450.000" in factura or "%2450" in factura
    assert cobro.startswith("https://wa.me/573001234567?text=")
    assert "saldo%20pendiente" in cobro


def test_registrar_cliente_normaliza_celular_y_exige_nombre(bd) -> None:
    """La agenda guarda el celular limpio y rechaza nombres vacíos."""
    cliente = comercial.registrar_cliente(bd, "Pedro", "+57 310 987 6543")

    assert cliente.telefono_whatsapp == "3109876543"
    with pytest.raises(ValueError, match="nombre del cliente"):
        comercial.registrar_cliente(bd, "  ")
