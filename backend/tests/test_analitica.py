"""Pruebas de la Fase 6 de OLB_BYTE: reportes, clientes VIP y alertas de costo.

Cubren RF-12 (mensual, anual y rentabilidad), RF-13 (ranking VIP) y RF-14 (subidas
de costo y margen). Las órdenes anuladas no cuentan en ingresos ni rankings, pero sí
en el historial de costos porque la mercancía ya se compró (ADR-35).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import analitica, comercial


def _vender(
    bd,
    *,
    fecha: datetime,
    precio: str = "50000",
    costo: str = "30000",
    cantidad: int = 1,
    nombre: str = "Audífonos BT",
    cliente: str = "Ana Pérez",
    telefono: str = "3001234567",
):
    """Registra una venta de una línea con datos de prueba.

    Args:
        bd: Sesión de base de datos.
        fecha: Fecha de la venta.
        precio: Precio unitario.
        costo: Costo unitario.
        cantidad: Unidades.
        nombre: Producto.
        cliente: Nombre del cliente.
        telefono: Celular del cliente.

    Returns:
        La orden persistida.
    """
    return comercial.registrar_venta(
        bd,
        cliente,
        telefono,
        [
            comercial.LineaVenta(
                nombre=nombre, cantidad=cantidad, precio_unitario=precio, costo_unitario=costo
            )
        ],
        fecha,
    )


def _fecha(anio: int, mes: int, dia: int = 10) -> datetime:
    """Construye una fecha de venta con la zona de la tienda.

    Args:
        anio: Año.
        mes: Mes.
        dia: Día.

    Returns:
        Fecha con zona horaria de la tienda.
    """
    return datetime(anio, mes, dia, 12, 0, tzinfo=comercial.ZONA_TIENDA)


def test_reporte_mensual_compara_con_el_mes_anterior(bd) -> None:
    """Enero y febrero se comparan: la variación de la ganancia es la de febrero frente a enero."""
    _vender(bd, fecha=_fecha(2026, 1), precio="50000", costo="30000")
    _vender(bd, fecha=_fecha(2026, 2), precio="60000", costo="30000", cantidad=2)

    filas = analitica.reporte_mensual(bd, 2026)

    enero, febrero = filas[0], filas[1]
    assert enero["ventas"] == 1
    assert enero["ganancia"] == Decimal("20000")
    assert enero["variacion"] is None
    assert febrero["ingresos"] == Decimal("120000")
    assert febrero["variacion"] == Decimal("200.0")
    assert febrero["barra"] == 100
    assert len(filas) == 12


def test_reporte_mensual_no_cuenta_ordenes_anuladas(bd) -> None:
    """Una orden anulada no suma ventas ni ingresos al mes."""
    activa = _vender(bd, fecha=_fecha(2026, 3))
    anulada = _vender(bd, fecha=_fecha(2026, 3), precio="90000")
    comercial.anular_venta(bd, anulada.id_venta, "Error")

    marzo = analitica.reporte_mensual(bd, 2026)[2]

    assert marzo["ventas"] == 1
    assert marzo["ingresos"] == activa.total


def test_reporte_anual_calcula_rentabilidad_y_variacion(bd) -> None:
    """Rentabilidad = ganancia ÷ costo × 100; la variación compara con el año anterior."""
    _vender(bd, fecha=_fecha(2025, 6), precio="50000", costo="25000")
    _vender(bd, fecha=_fecha(2026, 6), precio="50000", costo="20000")

    anios = {fila["anio"]: fila for fila in analitica.reporte_anual(bd)}

    assert anios[2025]["rentabilidad"] == Decimal("100.0")
    assert anios[2026]["ganancia"] == Decimal("30000")
    assert anios[2026]["rentabilidad"] == Decimal("150.0")
    assert anios[2026]["variacion"] == Decimal("20.0")
    assert anios[2025]["variacion"] is None


def test_rentabilidad_sin_costo_no_se_calcula(bd) -> None:
    """Sin costo registrado no hay rentabilidad que dividir."""
    _vender(bd, fecha=_fecha(2026, 4), precio="50000", costo="0")

    fila = analitica.reporte_anual(bd)[0]

    assert fila["rentabilidad"] is None


def test_ranking_vip_ordena_por_monto_y_luego_frecuencia(bd) -> None:
    """El cliente que más compra va primero; con el mismo monto gana quien compra más veces."""
    _vender(bd, fecha=_fecha(2026, 5), precio="100000", costo="50000", cliente="Ana", telefono="3001111111")
    _vender(bd, fecha=_fecha(2026, 5), precio="50000", costo="20000", cliente="Luis", telefono="3002222222")
    _vender(bd, fecha=_fecha(2026, 6), precio="50000", costo="20000", cliente="Luis", telefono="3002222222")

    ranking = analitica.ranking_vip(bd)

    assert [fila["cliente"] for fila in ranking] == ["Luis", "Ana"]
    assert ranking[0]["compras"] == 2
    assert ranking[0]["monto"] == Decimal("100000")
    assert ranking[1]["monto"] == Decimal("100000")


def test_ranking_vip_excluye_anuladas(bd) -> None:
    """Una orden anulada no cuenta para el ranking de fidelidad."""
    anulada = _vender(bd, fecha=_fecha(2026, 7), precio="200000", costo="50000", cliente="Pedro", telefono="3003333333")
    comercial.anular_venta(bd, anulada.id_venta, "Error")

    assert analitica.ranking_vip(bd) == []


def test_alerta_detecta_subida_de_costo_y_margen(bd) -> None:
    """Si el costo sube frente a la compra anterior se genera una alerta con el margen actual."""
    _vender(bd, fecha=_fecha(2026, 8), precio="50000", costo="30000")
    _vender(bd, fecha=_fecha(2026, 9), precio="50000", costo="36000")

    alertas = analitica.alertas_costos(bd)

    subida = alertas["subidas"][0]
    assert subida["producto"] == "Audífonos BT"
    assert subida["costo_anterior"] == Decimal("30000")
    assert subida["costo_actual"] == Decimal("36000")
    assert subida["variacion"] == Decimal("20.0")
    assert subida["margen"] == Decimal("28.0")
    assert subida["margen_bajo"] is False


def test_margen_bajo_se_marca_con_umbral(bd) -> None:
    """Un margen menor al umbral de negocio se marca para revisión."""
    _vender(bd, fecha=_fecha(2026, 8), precio="50000", costo="40000")
    _vender(bd, fecha=_fecha(2026, 9), precio="50000", costo="45000")

    subida = analitica.alertas_costos(bd)["subidas"][0]

    assert subida["margen"] == Decimal("10.0")
    assert subida["margen_bajo"] is True


def test_bajada_de_costo_y_producto_comprado_una_vez_no_generan_alerta(bd) -> None:
    """Solo las subidas generan alerta; un producto con una sola compra tampoco."""
    _vender(bd, fecha=_fecha(2026, 8), precio="50000", costo="36000")
    _vender(bd, fecha=_fecha(2026, 9), precio="50000", costo="30000")
    _vender(bd, fecha=_fecha(2026, 9), nombre="Cargador 20W", precio="25000", costo="15000")

    alertas = analitica.alertas_costos(bd)

    assert alertas["subidas"] == []
    assert len(alertas["costos"]) == 2


def test_compra_de_orden_anulada_sigue_en_el_historial_de_costos(bd) -> None:
    """La compra de una orden anulada cuenta para el costo: la mercancía ya se compró."""
    anulada = _vender(bd, fecha=_fecha(2026, 8), precio="50000", costo="30000")
    comercial.anular_venta(bd, anulada.id_venta, "Error")
    _vender(bd, fecha=_fecha(2026, 9), precio="50000", costo="36000")

    alertas = analitica.alertas_costos(bd)

    assert len(alertas["subidas"]) == 1


def test_panel_de_analitica_muestra_reportes(cliente_admin: TestClient, bd) -> None:
    """La vista presenta los cuatro reportes y acepta un año por parámetro."""
    _vender(bd, fecha=_fecha(2026, 2), precio="50000", costo="30000")

    respuesta = cliente_admin.get("/olb-byte/analitica", params={"anio": 2026})

    assert respuesta.status_code == 200
    assert "Mes a mes · 2026" in respuesta.text
    assert "Año tras año" in respuesta.text
    assert "Clientes VIP" in respuesta.text
    assert "Alertas de costo" in respuesta.text


def test_usuario_publico_no_ve_la_analitica(cliente_usuario: TestClient) -> None:
    """La analítica exige administrador."""
    assert cliente_usuario.get("/olb-byte/analitica").status_code == 403

def test_mismo_celular_con_otro_nombre_son_clientes_distintos(bd) -> None:
    """Un número compartido por dos personas no las une: cada una aparece en el ranking."""
    _vender(bd, fecha=_fecha(2026, 3), precio="50000", costo="30000", cliente="Ana", telefono="3001111111")
    _vender(bd, fecha=_fecha(2026, 4), precio="80000", costo="30000", cliente="Luis", telefono="3001111111")

    ranking = analitica.ranking_vip(bd)

    assert [fila["cliente"] for fila in ranking] == ["Luis", "Ana"]
    assert ranking[0]["monto"] == Decimal("80000")
    assert ranking[1]["monto"] == Decimal("50000")


def test_mismo_celular_y_mismo_nombre_es_un_solo_cliente(bd) -> None:
    """Dos compras de la misma persona con el mismo celular suman en un solo cliente."""
    _vender(bd, fecha=_fecha(2026, 5), precio="50000", costo="30000", cliente="Ana", telefono="3002222222")
    _vender(bd, fecha=_fecha(2026, 6), precio="50000", costo="30000", cliente="Ana", telefono="3002222222")

    ranking = analitica.ranking_vip(bd)

    assert len(ranking) == 1
    assert ranking[0]["compras"] == 2
