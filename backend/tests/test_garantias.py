"""Pruebas de la Fase 5 de OLB_BYTE: garantías en trámite y ranking de fallas (RF-05).

Cubren el flujo ABIERTA → EN_TRAMITE → RESUELTA/RECHAZADA, la vigencia del reclamo,
la exclusión de órdenes anuladas y el cálculo de la tasa de fallas.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.modelos import GarantiaProveedor, VentaDetalle
from app.servicios import comercial


def _venta(bd, nombre: str = "Ana Pérez", lineas=None, fecha: datetime | None = None):
    """Registra una venta con líneas por defecto de audífonos y cargador.

    Args:
        bd: Sesión de base de datos.
        nombre: Cliente.
        lineas: Líneas a vender; por defecto dos productos.
        fecha: Fecha de la venta.

    Returns:
        La orden persistida.
    """
    lineas = lineas or [
        comercial.LineaVenta(
            nombre="Audífonos BT", referencia="AB-1", cantidad=2, precio_unitario="50000", costo_unitario="30000"
        ),
        comercial.LineaVenta(nombre="Cargador 20W", cantidad=1, precio_unitario="25000", costo_unitario="15000"),
    ]
    return comercial.registrar_venta(bd, nombre, "3001234567", lineas, fecha)


def _linea(bd, venta, nombre: str) -> VentaDetalle:
    """Busca la línea de una orden por nombre de producto.

    Args:
        bd: Sesión de base de datos.
        venta: Orden consultada.
        nombre: Nombre del producto.

    Returns:
        La línea encontrada.
    """
    return bd.query(VentaDetalle).filter(
        VentaDetalle.id_venta == venta.id_venta, VentaDetalle.producto_nombre == nombre
    ).one()


def test_reclamo_nace_abierto_con_producto_y_referencia(bd) -> None:
    """Un reclamo copia el nombre y la referencia de la línea y empieza ABIERTA."""
    venta = _venta(bd)
    linea = _linea(bd, venta, "Audífonos BT")

    garantia = comercial.registrar_garantia(bd, linea.id_detalle, "No enciende")

    assert garantia.estado_tramite == "ABIERTA"
    assert garantia.producto_referencia == "Audífonos BT (AB-1)"
    assert garantia.observacion == "No enciende"
    assert garantia.fecha_resolucion is None


def test_reclamo_sobre_orden_anulada_o_linea_inexistente_falla(bd) -> None:
    """No se abre garantía sobre órdenes anuladas ni sobre líneas que no existen."""
    venta = _venta(bd)
    linea = _linea(bd, venta, "Cargador 20W")
    comercial.anular_venta(bd, venta.id_venta, "Error")

    with pytest.raises(ValueError, match="anulada"):
        comercial.registrar_garantia(bd, linea.id_detalle)
    with pytest.raises(ValueError, match="no existe"):
        comercial.registrar_garantia(bd, "no-existe")


def test_flujo_de_tramite_avanza_y_cierra(bd) -> None:
    """ABIERTA pasa a EN_TRAMITE y luego a RESUELTA con fecha de resolución."""
    venta = _venta(bd)
    garantia = comercial.registrar_garantia(bd, _linea(bd, venta, "Cargador 20W").id_detalle)

    tramite = comercial.actualizar_estado_garantia(bd, garantia.id_garantia, "en_tramite", "Enviado")
    assert tramite.estado_tramite == "EN_TRAMITE"
    assert tramite.observacion == "Enviado"
    assert tramite.fecha_resolucion is None

    cerrada = comercial.actualizar_estado_garantia(bd, garantia.id_garantia, "RESUELTA")
    assert cerrada.estado_tramite == "RESUELTA"
    assert cerrada.fecha_resolucion is not None


def test_reclamo_cerrado_no_se_reabre_y_no_vuelve_a_abierta(bd) -> None:
    """Un reclamo cerrado es final y ningún reclamo vuelve a ABIERTA."""
    venta = _venta(bd)
    garantia = comercial.registrar_garantia(bd, _linea(bd, venta, "Cargador 20W").id_detalle)

    with pytest.raises(ValueError, match="ABIERTA|abierto"):
        comercial.actualizar_estado_garantia(bd, garantia.id_garantia, "ABIERTA")

    comercial.actualizar_estado_garantia(bd, garantia.id_garantia, "RECHAZADA")
    with pytest.raises(ValueError, match="ya está cerrado"):
        comercial.actualizar_estado_garantia(bd, garantia.id_garantia, "EN_TRAMITE")


def test_estado_invalido_se_rechaza(bd) -> None:
    """Solo se aceptan los estados definidos en el diccionario de datos."""
    venta = _venta(bd)
    garantia = comercial.registrar_garantia(bd, _linea(bd, venta, "Cargador 20W").id_detalle)

    with pytest.raises(ValueError, match="no es válido"):
        comercial.actualizar_estado_garantia(bd, garantia.id_garantia, "PAGADA")


def test_vigencia_del_reclamo_depende_de_la_fecha_de_fin(bd) -> None:
    """Un reclamo dentro del plazo cuenta como vigente; uno posterior, no."""
    venta = _venta(bd, fecha=datetime(2026, 1, 10, 15, 0, tzinfo=comercial.ZONA_TIENDA))
    fin = venta.garantia_fecha_fin

    assert fin == date(2026, 4, 10)
    assert comercial.garantia_vigente_al_reclamo(venta, datetime(2026, 4, 10, 9, 0, tzinfo=comercial.ZONA_TIENDA))
    assert not comercial.garantia_vigente_al_reclamo(venta, datetime(2026, 4, 11, 9, 0, tzinfo=comercial.ZONA_TIENDA))


def test_ranking_calcula_tasa_sobre_unidades_vendidas(bd) -> None:
    """La tasa es reclamos ÷ unidades × 100 y el ranking va de mayor a menor tasa."""
    venta = _venta(bd)
    audifonos = _linea(bd, venta, "Audífonos BT")
    comercial.registrar_garantia(bd, audifonos.id_detalle)

    ranking = {fila["producto"]: fila for fila in comercial.ranking_fallas(bd)}

    assert ranking["Audífonos BT (AB-1)"]["unidades"] == 2
    assert ranking["Audífonos BT (AB-1)"]["fallas"] == 1
    assert ranking["Audífonos BT (AB-1)"]["tasa"] == Decimal("50.0")
    assert ranking["Cargador 20W"]["tasa"] == Decimal("0.0")
    assert comercial.ranking_fallas(bd)[0]["producto"] == "Audífonos BT (AB-1)"


def test_ranking_excluye_ordenes_anuladas(bd) -> None:
    """Una orden anulada no suma unidades ni reclamos al indicador."""
    venta = _venta(bd)
    comercial.registrar_garantia(bd, _linea(bd, venta, "Cargador 20W").id_detalle)
    comercial.anular_venta(bd, venta.id_venta, "Error")

    assert comercial.ranking_fallas(bd) == []


def test_opciones_solo_muestran_lineas_de_ordenes_activas(bd) -> None:
    """El formulario de reclamo ofrece solo líneas de órdenes activas."""
    _venta(bd, nombre="Ana")
    anulada = _venta(bd, nombre="Luis")
    comercial.anular_venta(bd, anulada.id_venta, "Error")

    opciones = comercial.opciones_garantia(bd)

    assert len(opciones) == 2
    assert all("Ana" in opcion["texto"] for opcion in opciones)


def test_panel_de_garantias_muestra_reclamos_y_ranking(cliente_admin: TestClient, bd) -> None:
    """La vista lista el reclamo, su vigencia y el ranking."""
    venta = _venta(bd)
    comercial.registrar_garantia(bd, _linea(bd, venta, "Audífonos BT").id_detalle, "Sin sonido")

    respuesta = cliente_admin.get("/olb-byte/garantias")

    assert respuesta.status_code == 200
    assert "Sin sonido" in respuesta.text
    assert "Dentro de garantía" in respuesta.text
    assert "Ranking de fallas" in respuesta.text


def test_registrar_reclamo_por_formulario_y_cambiar_estado(cliente_admin: TestClient, bd) -> None:
    """El formulario abre el reclamo y el cambio de estado queda guardado."""
    venta = _venta(bd)
    linea = _linea(bd, venta, "Cargador 20W")

    creado = cliente_admin.post(
        "/olb-byte/garantias",
        data={"id_detalle": linea.id_detalle, "observacion": "Cable quemado"},
        follow_redirects=False,
    )
    garantia = bd.query(GarantiaProveedor).one()
    cambio = cliente_admin.post(
        f"/olb-byte/garantias/{garantia.id_garantia}/estado",
        data={"estado": "RESUELTA", "observacion": "Cambio con proveedor"},
        follow_redirects=False,
    )

    assert creado.status_code == 303
    assert cambio.status_code == 303
    bd.expire_all()
    assert garantia.estado_tramite == "RESUELTA"
    assert garantia.observacion == "Cambio con proveedor"


def test_formulario_sin_producto_muestra_error(cliente_admin: TestClient, bd) -> None:
    """Abrir un reclamo sin elegir producto devuelve 400 y no crea registro."""
    respuesta = cliente_admin.post("/olb-byte/garantias", data={"id_detalle": ""})

    assert respuesta.status_code == 400
    assert "Elige el producto" in respuesta.text
    assert bd.query(GarantiaProveedor).count() == 0


def test_usuario_publico_no_ve_garantias(cliente_usuario: TestClient) -> None:
    """La vista de garantías exige administrador."""
    assert cliente_usuario.get("/olb-byte/garantias").status_code == 403


def test_fecha_de_hoy_se_usa_para_la_vigencia(bd) -> None:
    """Un reclamo de hoy sobre una venta de hoy está dentro de garantía."""
    hoy = comercial.ahora_tienda()
    venta = _venta(bd, fecha=hoy)
    assert comercial.garantia_vigente_al_reclamo(venta, hoy + timedelta(minutes=1))
