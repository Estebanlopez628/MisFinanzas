"""Pruebas de la interacción de las donas y del banner de apoyo (SRS v1.9).

Verifican que cada arco lleva sus datos para mostrarse al pasar el cursor, que el
centro guarda su texto por defecto, que la leyenda puede resaltar el arco y que la
página carga el script de la dona.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.servicios import comercial


def _html(respuesta) -> str:
    """Devuelve el HTML de una respuesta con espacios normalizados.

    Args:
        respuesta: Respuesta del cliente de pruebas.

    Returns:
        Texto HTML con los saltos de línea reducidos a espacios.
    """
    return " ".join(respuesta.text.split())


def test_la_dona_de_capacidad_muestra_el_detalle_del_arco(cliente_admin: TestClient) -> None:
    """Cada arco de la dona de capacidad trae etiqueta, porcentaje y valor."""
    html = _html(cliente_admin.get("/presupuesto"))

    assert 'data-dona-contenedor' in html
    assert 'class="dona__arco"' in html
    assert 'data-etiqueta="Gastos fijos"' in html
    assert "data-centro-valor" in html
    assert 'data-etiqueta-defecto="libre"' in html


def test_la_pagina_carga_el_script_de_la_dona(cliente_admin: TestClient) -> None:
    """Todas las páginas cargan `dona.js` junto con `app.js`."""
    html = _html(cliente_admin.get("/presupuesto"))

    assert "js/dona.js" in html
    assert "js/app.js" in html


def test_la_dona_de_cartera_tiene_arcos_con_detalle(cliente_admin: TestClient, bd) -> None:
    """La dona de cartera frente a deuda muestra el valor de cada arco al interactuar."""
    comercial.registrar_venta(
        bd,
        "Ana",
        "3001111111",
        [comercial.LineaVenta(nombre="Cable", cantidad=1, precio_unitario="50000", costo_unitario="20000")],
    )

    html = _html(cliente_admin.get("/olb-byte/cartera"))

    assert 'data-etiqueta="Cartera por cobrar"' in html
    assert 'data-etiqueta="Deuda con proveedor"' in html
    assert 'data-leyenda-etiqueta="Cartera por cobrar"' in html
    assert "data-centro-detalle" in html
