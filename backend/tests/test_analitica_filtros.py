"""Pruebas de la analítica con filtros y descargas CSV (SRS v1.9, bloque 3).

Cubren el reparto de saldo y abonos entre productos (ADR-55), la garantía medida
por producto, los filtros de mes, cliente y producto aplicados a todas las tablas,
el contenido de los CSV y la tolerancia de la vista ante parámetros mal escritos.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import analitica, comercial

COLUMNAS_VENTAS = (
    "No. de orden;Cliente;Categoría;Producto;Costo;Total;Saldo pendiente;"
    "Abonos realizados;Ganancia;Garantía;Origen;Fecha de compra;Fecha de recaudo"
)


def _fecha(anio: int, mes: int, dia: int = 10) -> datetime:
    """Construye una fecha de venta en la zona de la tienda.

    Args:
        anio: Año.
        mes: Mes.
        dia: Día.

    Returns:
        Fecha y hora a mediodía en hora de la tienda.
    """
    return datetime(anio, mes, dia, 12, tzinfo=comercial.ZONA_TIENDA)


def _linea(
    nombre: str,
    precio: str,
    costo: str,
    *,
    cantidad: int = 1,
    garantia: int = comercial.GARANTIA_MESES_DEFECTO,
    categoria: str | None = None,
) -> comercial.LineaVenta:
    """Crea una línea de venta de prueba.

    Args:
        nombre: Producto.
        precio: Precio unitario.
        costo: Costo unitario.
        cantidad: Unidades.
        garantia: Meses de garantía de la línea.
        categoria: Categoría opcional.

    Returns:
        La línea lista para `registrar_venta`.
    """
    return comercial.LineaVenta(
        nombre=nombre,
        cantidad=cantidad,
        precio_unitario=precio,
        costo_unitario=costo,
        categoria=categoria,
        garantia_meses=garantia,
    )


def _orden(bd, cliente: str, telefono: str, lineas, fecha: datetime):
    """Registra una orden de prueba.

    Args:
        bd: Sesión de base de datos.
        cliente: Nombre del cliente.
        telefono: Celular del cliente.
        lineas: Líneas de la orden.
        fecha: Fecha de venta.

    Returns:
        La orden persistida.
    """
    return comercial.registrar_venta(bd, cliente, telefono, lineas, fecha)


def test_saldo_y_abonos_se_reparten_sin_perder_centavos(bd) -> None:
    """La suma de saldos y abonos por producto coincide con la orden (ADR-55)."""
    _orden(
        bd,
        "Ana Pérez",
        "3001111111",
        [_linea("Parlante", "100000", "60000"), _linea("Cargador", "50001", "30000")],
        _fecha(2026, 11),
    )
    orden = comercial.listar_ventas(bd)[0]
    comercial.registrar_abono(bd, orden.id_venta, "10000")
    orden = comercial.obtener_venta(bd, orden.id_venta)

    filas = analitica.tabla_ventas(bd, None, date(2026, 11, 20))

    assert sum(fila["saldo"] for fila in filas) == orden.saldo_pendiente
    assert sum(fila["abonado"] for fila in filas) == orden.total_abonado
    assert sum(fila["total"] for fila in filas) == orden.total


def test_la_garantia_se_mide_por_producto(bd) -> None:
    """Un producto con garantía de 12 meses sigue activo aunque otro ya venció."""
    _orden(
        bd,
        "Ana Pérez",
        "3001111111",
        [
            _linea("Cable", "20000", "10000", garantia=0),
            _linea("Audífonos", "80000", "50000", garantia=12),
        ],
        _fecha(2026, 11, 10),
    )

    filas = analitica.tabla_ventas(bd, None, date(2027, 5, 10))
    estados = {fila["producto"]: fila["garantia"] for fila in filas}

    assert estados == {"Cable": "Vencida", "Audífonos": "Activa"}


def test_estado_de_garantia_sin_fecha() -> None:
    """Una línea sin fecha de garantía se muestra como «Sin garantía»."""
    assert analitica.estado_garantia_fila(None, date(2026, 11, 20)) == "Sin garantía"


def test_el_filtro_de_mes_limita_las_ventas(bd) -> None:
    """Con mes elegido, la tabla de ventas solo lista ese mes."""
    _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "10000")], _fecha(2026, 10))
    _orden(bd, "Ana", "3001111111", [_linea("Parlante", "90000", "60000")], _fecha(2026, 11))

    filtro = analitica.Filtro(anio=2026, mes=11)
    filas = analitica.tabla_ventas(bd, filtro, date(2026, 12, 1))

    assert [fila["producto"] for fila in filas] == ["Parlante"]


def test_el_filtro_de_cliente_afecta_todas_las_tablas(bd) -> None:
    """Elegir un cliente recalcula el mensual, el VIP y el listado de ventas."""
    ana = _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "10000")], _fecha(2026, 11))
    _orden(bd, "Luis", "3002222222", [_linea("Cable", "50000", "10000")], _fecha(2026, 11))

    filtro = analitica.Filtro(anio=2026, id_cliente=ana.id_cliente)

    mensual = analitica.reporte_mensual(bd, 2026, filtro)
    vip = analitica.ranking_vip(bd, filtro=filtro)
    ventas = analitica.tabla_ventas(bd, filtro, date(2026, 12, 1))

    assert mensual[10]["ingresos"] == Decimal("20000.00")
    assert [fila["cliente"] for fila in vip] == ["Ana"]
    assert [fila["cliente"] for fila in ventas] == ["Ana"]


def test_el_filtro_de_producto_limita_las_alertas(bd) -> None:
    """Con un producto elegido, las alertas solo muestran ese producto."""
    for costo, dia in (("30000", 1), ("40000", 15)):
        _orden(bd, "Ana", "3001111111", [_linea("Parlante", "90000", costo)], _fecha(2026, 10, dia))
        _orden(bd, "Ana", "3001111111", [_linea("Cargador", "40000", costo)], _fecha(2026, 10, dia))

    alertas = analitica.alertas_costos(bd, analitica.Filtro(producto="Parlante"))

    assert [fila["producto"] for fila in alertas["subidas"]] == ["Parlante"]
    assert {fila["producto"] for fila in alertas["costos"]} == {"Parlante"}


def test_el_mes_usa_la_ultima_compra_hasta_ese_mes(bd) -> None:
    """Una alerta aparece en el mes de su última compra y no en los demás."""
    _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "30000")], _fecha(2026, 9))
    _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "40000")], _fecha(2026, 10))
    _orden(bd, "Ana", "3001111111", [_linea("Parlante", "90000", "30000")], _fecha(2026, 11))

    octubre = analitica.alertas_costos(bd, analitica.Filtro(anio=2026, mes=10))
    noviembre = analitica.alertas_costos(bd, analitica.Filtro(anio=2026, mes=11))

    assert [fila["producto"] for fila in octubre["subidas"]] == ["Cable"]
    assert [fila["producto"] for fila in noviembre["costos"]] == ["Parlante"]
    assert noviembre["subidas"] == []


def test_las_anuladas_no_aparecen_en_la_tabla_de_ventas(bd) -> None:
    """Una orden anulada sale de las ventas, aunque su compra siga en costos."""
    orden = _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "10000")], _fecha(2026, 11))
    comercial.anular_venta(bd, orden.id_venta, "Cliente desistió")

    assert analitica.tabla_ventas(bd, None, date(2026, 12, 1)) == []


def test_csv_de_ventas_tiene_las_columnas_en_orden(cliente_admin: TestClient, bd) -> None:
    """El CSV del mes trae las diez columnas pedidas, separadas por punto y coma."""
    _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "10000")], _fecha(2026, 11))

    respuesta = cliente_admin.get(
        "/olb-byte/analitica/exportar/ventas.csv", params={"anio": "2026", "mes": "11"}
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert respuesta.text.startswith("\ufeff")
    lineas = respuesta.text.lstrip("\ufeff").splitlines()
    assert lineas[0] == COLUMNAS_VENTAS
    assert lineas[1].startswith("1;Ana;")
    assert "20000,00" in lineas[1]


def test_csv_respeta_el_cliente_elegido(cliente_admin: TestClient, bd) -> None:
    """Lo que se descarga es lo que se ve: un cliente elegido deja solo sus filas."""
    ana = _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "10000")], _fecha(2026, 11))
    _orden(bd, "Luis", "3002222222", [_linea("Cable", "50000", "10000")], _fecha(2026, 11))

    respuesta = cliente_admin.get(
        "/olb-byte/analitica/exportar/ventas.csv",
        params={"anio": "2026", "cliente": ana.id_cliente},
    )

    assert "Ana" in respuesta.text
    assert "Luis" not in respuesta.text


def test_csv_de_tabla_desconocida_responde_404(cliente_admin: TestClient) -> None:
    """Un nombre de tabla que no existe no genera un archivo vacío."""
    assert cliente_admin.get("/olb-byte/analitica/exportar/inventada.csv").status_code == 404


def test_csv_no_se_descarga_sin_permiso(cliente_usuario: TestClient) -> None:
    """El usuario público no puede descargar la analítica."""
    assert cliente_usuario.get("/olb-byte/analitica/exportar/ventas.csv").status_code == 403


def test_parametros_mal_escritos_no_rompen_la_vista(cliente_admin: TestClient) -> None:
    """Letras o meses inexistentes en la URL se ignoran y la vista responde 200."""
    respuesta = cliente_admin.get(
        "/olb-byte/analitica",
        params={"anio": "xx", "mes": "13", "cliente": "   ", "producto": ""},
    )

    assert respuesta.status_code == 200


def test_la_vista_enlaza_filas_y_descargas(cliente_admin: TestClient, bd) -> None:
    """Cada tabla tiene su CSV y el mes de una fila lleva a un filtro enlazado."""
    _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "10000")], _fecha(2026, 11))

    html = cliente_admin.get("/olb-byte/analitica", params={"anio": "2026"}).text

    assert "exportar/ventas.csv" in html
    assert "exportar/mensual.csv" in html
    assert "mes=11" in html
    assert "Descargar CSV" in html


def test_un_mes_elegido_aparece_como_filtro_activo(cliente_admin: TestClient, bd) -> None:
    """Con mes elegido, la vista muestra el filtro y su forma de quitarlo."""
    _orden(bd, "Ana", "3001111111", [_linea("Cable", "20000", "10000")], _fecha(2026, 11))

    html = cliente_admin.get("/olb-byte/analitica", params={"anio": "2026", "mes": "11"}).text

    assert "Mes: Noviembre 2026" in html
    assert "Quitar todos los filtros" in html
