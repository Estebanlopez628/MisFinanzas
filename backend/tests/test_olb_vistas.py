"""Pruebas HTTP del panel OLB_BYTE: formulario de venta, cobros, anulación y factura.

Usan el cliente autenticado como `ADMIN_OLB` y verifican la persistencia real con
la sesión de base de datos de cada prueba.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.modelos import Abono, VentaDetalle
from app.servicios import comercial


def _datos_venta(**extra: object) -> dict[str, object]:
    """Arma un formulario de venta con dos productos.

    Args:
        **extra: Campos adicionales o sobrescritos.

    Returns:
        Diccionario con listas paralelas, como lo envía el navegador.
    """
    datos: dict[str, object] = {
        "cliente_nombre": "Ana Pérez",
        "cliente_telefono": "300 123 4567",
        "producto_nombre": ["Audífonos BT", "Cargador 20W"],
        "categoria": ["Audio", ""],
        "cantidad": ["2", "1"],
        "costo_unitario": ["30000", "15000"],
        "precio_unitario": ["50.000", "25000"],
        "garantia_meses": ["3", ""],
        "forma_pago": "CONTADO",
        "metodo_pago": "EFECTIVO",
    }
    datos.update(extra)
    return datos


def test_panel_muestra_formulario_de_venta_sin_inventario(cliente_admin: TestClient) -> None:
    """El panel ofrece la mini-tabla y ya no muestra el inventario ni el stock."""
    respuesta = cliente_admin.get("/olb-byte")

    assert respuesta.status_code == 200
    assert "Registrar venta" in respuesta.text
    assert "+ Agregar otro producto" in respuesta.text
    # SRS v4.44: un solo rótulo en el DOM; JS lo cambia a «Pegar número» en web.
    assert "Agregar Numero" in respuesta.text
    assert "data-rotulo-numero" in respuesta.text
    assert "Inventario" not in respuesta.text
    assert "stock" not in respuesta.text.lower()


def test_venta_con_varias_lineas_se_registra_y_redirige(cliente_admin: TestClient, bd) -> None:
    """Dos productos crean una orden con consecutivo 1 y totales calculados."""
    respuesta = cliente_admin.post("/olb-byte/ventas", data=_datos_venta(), follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/olb-byte?guardado=1"
    venta = comercial.listar_ventas(bd)[0]
    assert venta.numero_orden == 1
    assert venta.total == Decimal("125000")
    assert venta.total_costo == Decimal("75000")
    assert venta.ganancia_neta == Decimal("50000")
    assert venta.cliente_telefono == "3001234567"


def test_venta_ignora_filas_vacias_del_formulario(cliente_admin: TestClient, bd) -> None:
    """Una fila en blanco que dejó el usuario no se convierte en producto."""
    datos = _datos_venta(
        producto_nombre=["Audífonos BT", ""],
        categoria=["", ""],
        cantidad=["1", "1"],
        costo_unitario=["30000", ""],
        precio_unitario=["50000", ""],
        garantia_meses=["3", ""],
    )

    respuesta = cliente_admin.post("/olb-byte/ventas", data=datos, follow_redirects=False)

    assert respuesta.status_code == 303
    venta = comercial.listar_ventas(bd)[0]
    assert venta.total == Decimal("50000")
    assert bd.query(VentaDetalle).filter(VentaDetalle.id_venta == venta.id_venta).count() == 1


def test_venta_con_error_repuebla_el_formulario(cliente_admin: TestClient, bd) -> None:
    """Un precio faltante devuelve 400 con el mensaje y conserva lo escrito."""
    datos = _datos_venta(precio_unitario=["", "25000"])

    respuesta = cliente_admin.post("/olb-byte/ventas", data=datos)

    assert respuesta.status_code == 400
    assert "Escribe el precio de venta de Audífonos BT" in respuesta.text
    assert "Ana Pérez" in respuesta.text
    assert "Cargador 20W" in respuesta.text
    assert comercial.listar_ventas(bd) == []


def test_cantidad_no_numerica_devuelve_error_claro(cliente_admin: TestClient, bd) -> None:
    """Una cantidad con letras se rechaza sin crear la orden."""
    respuesta = cliente_admin.post(
        "/olb-byte/ventas", data=_datos_venta(cantidad=["dos", "1"])
    )

    assert respuesta.status_code == 400
    assert "debe ser un número entero" in respuesta.text
    assert comercial.listar_ventas(bd) == []


def test_abono_con_fecha_y_hora_y_metodo_invalido(cliente_admin: TestClient, bd) -> None:
    """El abono acepta fecha y hora del formulario y rechaza medios no permitidos."""
    cliente_admin.post(
        "/olb-byte/ventas", data=_datos_venta(forma_pago="CREDITO"), follow_redirects=False
    )
    venta = comercial.listar_ventas(bd)[0]

    ok = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/abonos",
        data={"monto": "40.000", "metodo_pago": "TRANSFERENCIA", "fecha_abono": "2026-11-16T10:30"},
        follow_redirects=False,
    )
    malo = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/abonos",
        data={"monto": "1000", "metodo_pago": "NEQUI"},
    )

    assert ok.status_code == 303
    assert malo.status_code == 400
    assert "Efectivo o Transferencia" in malo.text
    abono = bd.query(Abono).one()
    assert abono.fecha_abono.replace(tzinfo=None).isoformat() == "2026-11-16T10:30:00"
    bd.expire_all()
    assert comercial.resumen_cartera(bd)["cartera_clientes"] == Decimal("85000")


def test_anulacion_con_motivo_y_devolucion(cliente_admin: TestClient, bd) -> None:
    """Anular exige motivo, registra la devolución y saca la orden de la cartera."""
    cliente_admin.post(
        "/olb-byte/ventas", data=_datos_venta(forma_pago="CREDITO"), follow_redirects=False
    )
    venta = comercial.listar_ventas(bd)[0]
    comercial.registrar_abono(bd, venta.id_venta, "50000")

    sin_motivo = cliente_admin.post(f"/olb-byte/ventas/{venta.id_venta}/anular", data={"motivo": " "})
    ok = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/anular",
        data={"motivo": "Cliente desistió", "monto_devuelto": "30.000", "metodo_devolucion": "EFECTIVO"},
        follow_redirects=False,
    )

    assert sin_motivo.status_code == 400
    assert ok.status_code == 303
    bd.refresh(venta)
    assert venta.estado_orden == comercial.ESTADO_ANULADA
    assert comercial.pendiente_devolver(bd, venta) == Decimal("20000")
    assert comercial.cartera(bd) == []


def test_devolucion_pendiente_desde_el_panel(cliente_admin: TestClient, bd) -> None:
    """La devolución que quedó pendiente se registra desde la orden anulada."""
    cliente_admin.post(
        "/olb-byte/ventas", data=_datos_venta(forma_pago="CREDITO"), follow_redirects=False
    )
    venta = comercial.listar_ventas(bd)[0]
    comercial.registrar_abono(bd, venta.id_venta, "50000")
    comercial.anular_venta(bd, venta.id_venta, "Error")

    excesiva = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/devolucion",
        data={"monto": "60000", "metodo_pago": "TRANSFERENCIA"},
    )

    assert excesiva.status_code == 400
    assert "supera" in excesiva.text
    ok = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/devolucion",
        data={"monto": "50000", "metodo_pago": "TRANSFERENCIA"},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert comercial.pendiente_devolver(bd, venta) == Decimal("0")


def test_no_hay_ruta_de_nuevo_cliente(cliente_admin: TestClient) -> None:
    """El alta manual de clientes se retiró: el cliente se guarda al vender."""
    respuesta = cliente_admin.post("/olb-byte/clientes", data={"nombre": "Pedro"})

    assert respuesta.status_code in (404, 405)


def test_factura_muestra_consecutivo_garantia_y_detalle(cliente_admin: TestClient, bd) -> None:
    """La factura usa el número de orden y la garantía de cada línea."""
    cliente_admin.post(
        "/olb-byte/ventas", data=_datos_venta(garantia_meses=["3", "0"]), follow_redirects=False
    )
    venta = comercial.listar_ventas(bd)[0]

    respuesta = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}")

    assert respuesta.status_code == 200
    assert "Orden No." in respuesta.text
    assert "3 meses por defectos de fábrica" in respuesta.text
    assert "Sin garantía" in respuesta.text
    assert cliente_admin.get("/olb-byte/factura/no-existe").status_code == 404


def test_venta_sin_lineas_muestra_error(cliente_admin: TestClient, bd) -> None:
    """Enviar el formulario sin productos devuelve error y no crea orden."""
    respuesta = cliente_admin.post(
        "/olb-byte/ventas", data={"cliente_nombre": "Ana", "cliente_telefono": ""}
    )

    assert respuesta.status_code == 400
    assert "al menos un producto" in respuesta.text
    assert comercial.listar_ventas(bd) == []


def test_semaforo_de_garantia_vigente_y_vencida() -> None:
    """Verde mientras la fecha de fin no pasó; rojo cuando ya venció."""
    hoy = date(2026, 11, 17)

    class _Venta:
        garantia_fecha_fin = hoy + timedelta(days=10)

    vigente = _Venta()
    assert comercial.estado_garantia(vigente, hoy) == ("VERDE", 10)

    vencida = _Venta()
    vencida.garantia_fecha_fin = hoy - timedelta(days=2)
    assert comercial.estado_garantia(vencida, hoy) == ("ROJO", -2)

    sin_fecha = _Venta()
    sin_fecha.garantia_fecha_fin = None
    assert comercial.estado_garantia(sin_fecha, hoy) == ("ROJO", 0)


def test_venta_muestra_semaforo_en_el_panel(cliente_admin: TestClient, bd) -> None:
    """El panel indica garantía vigente para una venta reciente."""
    cliente_admin.post("/olb-byte/ventas", data=_datos_venta(), follow_redirects=False)

    respuesta = cliente_admin.get("/olb-byte")

    assert "semaforo--verde" in respuesta.text
    assert "Vigente" in respuesta.text
