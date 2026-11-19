"""Pruebas de la Fase 3 de OLB_BYTE: pendientes de pago, recibos y cobro por WhatsApp.

Cubren RF-06 (vista filtrada de pendientes y abonos con fecha y hora) y RF-07
(recibo compacto y enlace de WhatsApp), además de la hora de la tienda.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.servicios import comercial


def _venta(bd, nombre: str = "Ana Pérez", telefono: str = "3001234567", precio: str = "50000"):
    """Registra una venta de una línea para los cobros.

    Args:
        bd: Sesión de base de datos.
        nombre: Nombre del cliente.
        telefono: Celular del cliente.
        precio: Precio de la línea.

    Returns:
        La orden persistida.
    """
    return comercial.registrar_venta(
        bd,
        nombre,
        telefono,
        [comercial.LineaVenta(nombre="Audífonos BT", cantidad=1, precio_unitario=precio, costo_unitario="20000")],
    )


def test_hora_de_la_tienda_es_utc_menos_cinco() -> None:
    """Las fechas comerciales usan la hora de Colombia, sin horario de verano."""
    assert comercial.ahora_tienda().utcoffset() == timedelta(hours=-5)


def test_buscar_cartera_por_nombre_celular_y_numero(bd) -> None:
    """El filtro encuentra pendientes por cliente, celular o número de orden."""
    ana = _venta(bd, "Ana Pérez", "3001234567")
    luis = _venta(bd, "Luis Ruiz", "3109876543")

    assert [v.id_venta for v in comercial.buscar_cartera(bd, "ana")] == [ana.id_venta]
    assert [v.id_venta for v in comercial.buscar_cartera(bd, "9876")] == [luis.id_venta]
    assert luis.id_venta in [v.id_venta for v in comercial.buscar_cartera(bd, str(luis.numero_orden))]
    assert len(comercial.buscar_cartera(bd, "")) == 2


def test_pendientes_muestra_saldo_y_enlace_de_cobro(cliente_admin: TestClient, bd) -> None:
    """La vista lista el saldo y un enlace de WhatsApp con el cobro prellenado."""
    _venta(bd)

    respuesta = cliente_admin.get("/olb-byte/pendientes")

    assert respuesta.status_code == 200
    assert "Pendientes de pago" in respuesta.text
    assert "Ana Pérez" in respuesta.text
    assert "Añadir pago o gestionar cobro" in respuesta.text
    assert "https://wa.me/" not in respuesta.text


def test_pendientes_filtra_y_avisa_cuando_no_hay_coincidencias(cliente_admin: TestClient, bd) -> None:
    """El filtro reduce la lista y, sin resultados, lo indica con el texto buscado."""
    _venta(bd, "Ana Pérez")
    _venta(bd, "Luis Ruiz", "3109876543")

    filtrada = cliente_admin.get("/olb-byte/pendientes", params={"q": "luis"})
    vacia = cliente_admin.get("/olb-byte/pendientes", params={"q": "zzz"})

    assert "Luis Ruiz" in filtrada.text
    assert "Ana Pérez" not in filtrada.text
    assert "No hay pendientes que coincidan con «zzz»" in vacia.text


def test_abono_redirige_al_recibo_del_abono(cliente_admin: TestClient, bd) -> None:
    """Cobrar genera el recibo y redirige a él (RF-07)."""
    venta = _venta(bd)

    respuesta = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/abonos",
        data={"monto": "20.000", "metodo_pago": "EFECTIVO", "fecha_abono": "2026-11-16T10:30"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    abono = comercial.abonos_de_venta(bd, venta.id_venta)[0]
    assert respuesta.headers["location"] == f"/olb-byte/recibos/{abono.id_abono}"


def test_abono_con_error_conserva_el_filtro(cliente_admin: TestClient, bd) -> None:
    """Un error al cobrar vuelve a la vista de pendientes con el filtro activo."""
    venta = _venta(bd)

    respuesta = cliente_admin.post(
        f"/olb-byte/ventas/{venta.id_venta}/abonos",
        data={"monto": "999999", "metodo_pago": "EFECTIVO", "q": "ana"},
    )

    assert respuesta.status_code == 400
    assert "no puede superar el saldo pendiente" in respuesta.text
    assert 'value="ana"' in respuesta.text


def test_recibo_muestra_monto_medio_y_fecha_hora(cliente_admin: TestClient, bd) -> None:
    """El recibo muestra el monto, el medio y la fecha y hora del pago."""
    venta = _venta(bd)
    abono = comercial.registrar_abono(
        bd, venta.id_venta, "20000", "TRANSFERENCIA", _fecha(2026, 11, 16, 14, 5)
    )

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}")

    assert respuesta.status_code == 200
    assert "16/11/2026 02:05 PM" in respuesta.text
    assert "Transferencia" in respuesta.text
    assert "$20.000" in respuesta.text
    assert "Saldo pendiente" in respuesta.text


def test_recibo_con_saldo_total_muestra_insignia(cliente_admin: TestClient, bd) -> None:
    """Un recibo del último pago muestra la insignia de saldo total."""
    venta = _venta(bd, precio="50000")
    abono = comercial.registrar_abono(bd, venta.id_venta, "50000")

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}")

    assert "¡Saldo total cancelado!" in respuesta.text
    assert "Saldo pendiente" not in respuesta.text


def test_recibo_desglosa_los_abonos_de_la_orden(cliente_admin: TestClient, bd) -> None:
    """Con varios abonos el recibo muestra el desglose completo."""
    venta = _venta(bd, precio="50000")
    comercial.registrar_abono(bd, venta.id_venta, "10000")
    segundo = comercial.registrar_abono(bd, venta.id_venta, "15000")

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{segundo.id_abono}")

    assert "Desglose de abonos" in respuesta.text
    assert "recibo__desglose--actual" in respuesta.text


def test_recibo_comparte_por_whatsapp_con_el_mensaje(cliente_admin: TestClient, bd) -> None:
    """El enlace del recibo abre WhatsApp al número del cliente con el mensaje."""
    venta = _venta(bd)
    abono = comercial.registrar_abono(bd, venta.id_venta, "20000")

    respuesta = cliente_admin.get(f"/olb-byte/recibos/{abono.id_abono}")

    assert "https://wa.me/573001234567?text=Recibo%20de%20abono" in respuesta.text


def test_recibo_inexistente_devuelve_404(cliente_admin: TestClient) -> None:
    """Un recibo que no existe responde 404."""
    assert cliente_admin.get("/olb-byte/recibos/no-existe").status_code == 404


def test_usuario_publico_no_ve_pendientes_ni_recibos(cliente_usuario: TestClient, bd) -> None:
    """Las vistas de cobro exigen administrador: el usuario público recibe 403."""
    venta = _venta(bd)
    abono = comercial.registrar_abono(bd, venta.id_venta, "10000")

    assert cliente_usuario.get("/olb-byte/pendientes").status_code == 403
    assert cliente_usuario.get(f"/olb-byte/recibos/{abono.id_abono}").status_code == 403


def _fecha(anio: int, mes: int, dia: int, hora: int, minuto: int) -> datetime:
    """Construye una fecha con la zona de la tienda para fijar el abono.

    Args:
        anio: Año.
        mes: Mes.
        dia: Día.
        hora: Hora en 24 horas.
        minuto: Minuto.

    Returns:
        Fecha con zona horaria de la tienda.
    """
    return datetime(anio, mes, dia, hora, minuto, tzinfo=comercial.ZONA_TIENDA)


def test_abono_mayor_al_saldo_se_rechaza_sin_cambiar_la_cartera(bd) -> None:
    """Un abono por encima del saldo falla y la cartera queda igual."""
    venta = _venta(bd, precio="50000")

    with pytest.raises(ValueError, match="superar el saldo"):
        comercial.registrar_abono(bd, venta.id_venta, "60000")

    assert comercial.resumen_cartera(bd)["cartera_clientes"] == Decimal("50000")
