"""Buscador y orden de «Órdenes registradas» (SRS v1.8, bloque 6)."""

from __future__ import annotations

from datetime import datetime

from app.servicios import comercial


def _producto() -> list[comercial.LineaVenta]:
    """Devuelve un producto de prueba.

    Returns:
        Lista con una línea de venta.
    """
    return [
        comercial.LineaVenta(
            nombre="Audífonos", categoria="Audio", cantidad=1, precio_unitario="50000", costo_unitario="30000"
        )
    ]


def _venta(bd, cliente: str, fecha: datetime):
    """Registra una orden de prueba.

    Args:
        bd: Sesión de base de datos.
        cliente: Nombre del cliente.
        fecha: Fecha de la venta.

    Returns:
        La orden persistida.
    """
    return comercial.registrar_venta(bd, cliente, "3001234567", _producto(), fecha)


def test_busca_por_cliente_sin_tildes(cliente_admin, bd) -> None:
    """Buscar «ana» encuentra a «Ana Pérez» y no a otros clientes."""
    ana = _venta(bd, "Ana Pérez", datetime(2026, 11, 10, 15, tzinfo=comercial.ZONA_TIENDA))
    luis = _venta(bd, "Luis Gómez", datetime(2026, 11, 11, 15, tzinfo=comercial.ZONA_TIENDA))

    html = cliente_admin.get("/olb-byte", params={"q": "ana"}).text

    assert f'data-abrir-dialogo="orden-{ana.id_venta}"' in html
    assert f'data-abrir-dialogo="orden-{luis.id_venta}"' not in html


def test_busca_por_fecha_en_formato_corto(cliente_admin, bd) -> None:
    """La fecha se encuentra escrita como dd-mm-aaaa, dd/mm/aaaa o aaaa-mm-dd."""
    orden = _venta(bd, "Carla", datetime(2027, 1, 12, 15, tzinfo=comercial.ZONA_TIENDA))
    otra = _venta(bd, "Pedro", datetime(2027, 3, 1, 15, tzinfo=comercial.ZONA_TIENDA))

    for consulta in ("12-01-2027", "12/01/2027", "2027-01-12"):
        html = cliente_admin.get("/olb-byte", params={"q": consulta}).text
        assert f'data-abrir-dialogo="orden-{orden.id_venta}"' in html, consulta
        assert f'data-abrir-dialogo="orden-{otra.id_venta}"' not in html, consulta


def test_busca_por_numero_de_orden(cliente_admin, bd) -> None:
    """El número de orden también filtra la lista."""
    orden = _venta(bd, "Diego", datetime(2026, 11, 10, 15, tzinfo=comercial.ZONA_TIENDA))

    html = cliente_admin.get("/olb-byte", params={"q": str(orden.numero_orden)}).text

    assert f'data-abrir-dialogo="orden-{orden.id_venta}"' in html


def test_sin_coincidencias_muestra_el_mensaje(cliente_admin, bd) -> None:
    """Una búsqueda sin resultados explica que no hay órdenes que coincidan."""
    _venta(bd, "Elena", datetime(2026, 11, 10, 15, tzinfo=comercial.ZONA_TIENDA))

    html = cliente_admin.get("/olb-byte", params={"q": "zzz-no-existe"}).text

    assert "No hay órdenes que coincidan" in html


def test_ordenes_mas_recientes_primero(cliente_admin, bd) -> None:
    """La orden registrada después aparece antes en la lista."""
    antigua = _venta(bd, "Fabio", datetime(2026, 11, 1, 15, tzinfo=comercial.ZONA_TIENDA))
    reciente = _venta(bd, "Gina", datetime(2026, 11, 2, 15, tzinfo=comercial.ZONA_TIENDA))

    html = cliente_admin.get("/olb-byte").text

    assert html.index(f'data-abrir-dialogo="orden-{reciente.id_venta}"') < html.index(
        f'data-abrir-dialogo="orden-{antigua.id_venta}"'
    )


def test_totales_no_cambian_con_la_busqueda(cliente_admin, bd) -> None:
    """Filtrar la lista no altera las cifras del panel."""
    _venta(bd, "Hugo", datetime(2026, 11, 10, 15, tzinfo=comercial.ZONA_TIENDA))
    completo = cliente_admin.get("/olb-byte").text
    filtrado = cliente_admin.get("/olb-byte", params={"q": "nadie"}).text

    assert "orden(es) activa(s)." in completo
    assert completo.split("orden(es) activa(s).")[0][-200:] == filtrado.split("orden(es) activa(s).")[0][-200:]
