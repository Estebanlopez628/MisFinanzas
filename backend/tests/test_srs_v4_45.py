"""Pruebas de la SRS v4.44, secciones 7 a 9: cartera y gastos operativos.

Cubre deudas anteriores al sistema (tipo `DEUDA_INICIAL`), el historial de
gastos operativos y su descuento inmediato de la ganancia real (neta).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import analitica, comercial


def _fecha(anio: int, mes: int, dia: int = 10) -> datetime:
    """Construye una fecha en la zona horaria de la tienda.

    Args:
        anio: Año de la venta.
        mes: Mes de la venta.
        dia: Día de la venta.

    Returns:
        Fecha con zona horaria de Colombia.
    """
    return datetime(anio, mes, dia, 12, 0, tzinfo=comercial.ZONA_TIENDA)


def _vender(bd, anio: int, mes: int) -> None:
    """Registra una venta simple para alimentar la analítica.

    Args:
        bd: Sesión de base de datos.
        anio: Año de la venta.
        mes: Mes de la venta.

    Returns:
        None.
    """
    comercial.registrar_venta(
        bd,
        "Ana Pérez",
        "3001234567",
        [
            comercial.LineaVenta(
                nombre="Audífonos BT",
                cantidad=1,
                precio_unitario="50000",
                costo_unitario="30000",
            )
        ],
        _fecha(anio, mes),
    )


def test_deuda_inicial_suma_al_saldo_y_se_registra_en_el_libro(bd) -> None:
    """La deuda anterior al sistema aumenta la deuda y se etiqueta bien."""
    antes = comercial.deuda_proveedor(bd)
    movimiento = comercial.registrar_deuda_inicial(bd, "1.250.000", "Deuda con importador")
    assert comercial.deuda_proveedor(bd) == antes + Decimal("1250000")
    filas = comercial.listar_movimientos_con_orden(bd)
    fila = next(f for f in filas if f["id_movimiento"] == movimiento.id_movimiento)
    assert fila["tipo"] == comercial.TIPO_DEUDA_INICIAL
    assert fila["etiqueta"] == "Deuda inicial"
    assert fila["cliente"] == "—" and fila["producto"] == "—"
    assert fila["saldo_resultante"] == antes + Decimal("1250000")


def test_deuda_inicial_rechaza_monto_cero_y_concepto_vacio(bd) -> None:
    """No se registran deudas sin descripción ni por cero pesos."""
    try:
        comercial.registrar_deuda_inicial(bd, "100000", "   ")
    except ValueError:
        pass
    else:
        raise AssertionError("El concepto vacío debió rechazarse")
    try:
        comercial.registrar_deuda_inicial(bd, "0", "Deuda")
    except ValueError:
        pass
    else:
        raise AssertionError("El monto cero debió rechazarse")


def test_gastos_operativos_no_tocan_la_deuda_del_proveedor(bd) -> None:
    """Un gasto operativo se contabiliza aparte del libro del proveedor."""
    antes = comercial.deuda_proveedor(bd)
    gasto = comercial.registrar_gasto_operativo(bd, "45000", "2026-03-15")
    assert gasto.fecha == date(2026, 3, 15)
    assert gasto.monto == Decimal("45000")
    assert comercial.deuda_proveedor(bd) == antes
    assert comercial.total_gastos_operativos(bd) == Decimal("45000")


def test_totales_de_gastos_por_mes_y_anio(bd) -> None:
    """El total respeta el mes y el año pedidos."""
    comercial.registrar_gasto_operativo(bd, "10000", "2026-02-05")
    comercial.registrar_gasto_operativo(bd, "20000", "2026-03-05")
    comercial.registrar_gasto_operativo(bd, "30000", "2025-03-05")
    assert comercial.total_gastos_operativos(bd, 2026, 2) == Decimal("10000")
    assert comercial.total_gastos_operativos(bd, 2026, 3) == Decimal("20000")
    assert comercial.total_gastos_operativos(bd, 2026) == Decimal("30000")
    assert comercial.total_gastos_operativos(bd, 2025, 12) == Decimal("0")


def test_editar_y_eliminar_gasto_operativo(bd) -> None:
    """Las correcciones se reflejan de inmediato en el total."""
    gasto = comercial.registrar_gasto_operativo(bd, "10000", "2026-04-01")
    comercial.actualizar_gasto_operativo(bd, gasto.id_gasto_operativo, "25000", "2026-04-20")
    actualizado = bd.get(type(gasto), gasto.id_gasto_operativo)
    assert actualizado.monto == Decimal("25000")
    assert actualizado.fecha == date(2026, 4, 20)
    assert comercial.total_gastos_operativos(bd, 2026, 4) == Decimal("25000")
    comercial.eliminar_gasto_operativo(bd, gasto.id_gasto_operativo)
    assert comercial.total_gastos_operativos(bd) == Decimal("0")


def test_ganancia_neta_mensual_y_anual(bd) -> None:
    """La ganancia neta resta los gastos operativos del mes y del año."""
    _vender(bd, 2026, 3)
    comercial.registrar_gasto_operativo(bd, "5000", "2026-03-15")
    mensual = analitica.reporte_mensual(bd, 2026)
    marzo = mensual[2]
    assert marzo["ganancia"] == Decimal("20000")
    assert marzo["gastos_operativos"] == Decimal("5000")
    assert marzo["ganancia_neta"] == Decimal("15000")
    anual = {fila["anio"]: fila for fila in analitica.reporte_anual(bd)}
    assert anual[2026]["gastos_operativos"] == Decimal("5000")
    assert anual[2026]["ganancia_neta"] == Decimal("15000")


def test_la_ganancia_neta_es_negativa_cuando_el_gasto_supera_la_ganancia(bd) -> None:
    """El resultado puede ser negativo y no se disfraza con cero."""
    _vender(bd, 2026, 3)
    comercial.registrar_gasto_operativo(bd, "90000", "2026-03-15")
    marzo = analitica.reporte_mensual(bd, 2026)[2]
    assert marzo["ganancia_neta"] == Decimal("-70000")


def test_csv_de_analitica_incluye_las_columnas_nuevas(bd) -> None:
    """Las descargas mensual y anual muestran gasto operativo y ganancia neta."""
    encabezados, filas = analitica.tabla_csv(bd, "mensual", analitica.Filtro(anio=2026), date(2026, 12, 1))
    assert "Gastos operativos" in encabezados
    assert "Ganancia neta" in encabezados
    assert len(filas[0]) == len(encabezados)
    encabezados, filas = analitica.tabla_csv(bd, "anual", analitica.Filtro(), date(2026, 12, 1))
    assert "Gastos operativos" in encabezados
    assert "Ganancia neta" in encabezados


def test_vista_cartera_muestra_las_tarjetas_y_el_historial(cliente_admin: TestClient, bd) -> None:
    """La cartera expone los formularios, las siete columnas y los diálogos."""
    # Las tablas solo se renderizan con datos: se siembra un movimiento y un gasto.
    comercial.registrar_deuda_inicial(bd, "100000", "Deuda anterior")
    comercial.registrar_gasto_operativo(bd, "20000", "2026-06-01")
    respuesta = cliente_admin.get("/olb-byte/cartera")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert 'action="/olb-byte/proveedor/deudas-iniciales"' not in html
    assert "Gastos operativos" in html
    assert "Historial de gastos operativos" in html
    assert 'name="concepto"' in html and 'name="monto"' in html
    cabeceras = ["Fecha", "Tipo", "Cliente", "Producto", "Concepto", "Monto", "Saldo"]
    posiciones = [html.index(f'>{etiqueta}</th>') for etiqueta in cabeceras]
    assert posiciones == sorted(posiciones)


def test_registro_de_deuda_inicial_por_http(cliente_admin: TestClient, bd) -> None:
    """El formulario de deuda anterior incrementa el saldo."""
    antes = comercial.deuda_proveedor(bd)
    respuesta = cliente_admin.post(
        "/olb-byte/proveedor/deudas-iniciales",
        data={"concepto": "Deuda con importador", "monto": "300.000"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert comercial.deuda_proveedor(bd) == antes + Decimal("300000")
    assert any(
        f["etiqueta"] == "Deuda inicial" for f in comercial.listar_movimientos_con_orden(bd)
    )


def test_registro_y_borrado_de_gasto_operativo_por_http(cliente_admin: TestClient, bd) -> None:
    """El alta y el borrado por HTTP recalculan el total."""
    respuesta = cliente_admin.post(
        "/olb-byte/cartera/gastos-operativos",
        data={"monto": "75.000", "fecha": "2026-05-12"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    bd.rollback()  # La petición usa otra sesión: se actualiza la instantánea.
    assert comercial.total_gastos_operativos(bd, 2026, 5) == Decimal("75000")
    gasto = comercial.listar_gastos_operativos(bd)[0]
    respuesta = cliente_admin.post(
        f"/olb-byte/cartera/gastos-operativos/{gasto.id_gasto_operativo}/editar",
        data={"monto": "80.000", "fecha": "2026-05-14"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    bd.rollback()
    assert comercial.total_gastos_operativos(bd, 2026, 5) == Decimal("80000")
    respuesta = cliente_admin.post(
        f"/olb-byte/cartera/gastos-operativos/{gasto.id_gasto_operativo}/eliminar",
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    bd.rollback()
    assert comercial.total_gastos_operativos(bd) == Decimal("0")


def test_usuario_estandar_no_puede_registrar_gastos_operativos(
    cliente_usuario: TestClient,
) -> None:
    """El módulo comercial sigue siendo exclusivo del administrador."""
    respuesta = cliente_usuario.post(
        "/olb-byte/cartera/gastos-operativos", data={"monto": "1000"}, follow_redirects=False
    )
    assert respuesta.status_code == 403


def test_vista_analitica_muestra_kpis_y_columnas(cliente_admin: TestClient, bd) -> None:
    """La analítica muestra el gasto operativo y la ganancia neta."""
    _vender(bd, 2026, 3)
    comercial.registrar_gasto_operativo(bd, "5000", "2026-03-15")
    respuesta = cliente_admin.get("/olb-byte/analitica?anio=2026")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Gastos operativos" in html
    assert "Ganancia neta" in html
    assert "Pago a Proveedor" in html
    assert "Ganancia real (neta) = ganancia bruta de ventas" not in html
    assert html.count("Gastos op.") >= 2
