"""Pruebas de los catálogos estándar de OLB BYTE.

Cubren las 12 categorías de producto de «Registrar venta», las 2 opciones de
«Pago al proveedor» y el orden y las 4 opciones de «Registrar falla».
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.servicios import comercial

CATEGORIAS_VENTA = (
    "Smartwatches",
    "Audífonos",
    "Parlantes",
    "Energía y carga",
    "Cables y adaptadores",
    "Accesorios celular",
    "Almacenamiento",
    "Periféricos PC",
    "Hogar y LED",
    "Gaming",
    "Combos",
    "Otros",
)

CONCEPTOS_PROVEEDOR = (
    "Compra de inventario",
    "Deudas al proveedor anteriores al sistema",
)

DESCRIPCIONES_FALLA = (
    "Rendimiento irregular",
    "Inconveniente de carga",
    "Defecto de fábrica",
    "Otros",
)


def _opciones(bloque: str) -> list[str]:
    """Extrae las opciones con valor de un fragmento de `<select>`.

    Args:
        bloque: HTML entre la apertura del select y su cierre.

    Returns:
        Valores no vacíos, en el orden en que aparecen.
    """
    return [valor for valor in re.findall(r'<option value="([^"]*)"', bloque) if valor]


def _select_tras(html: str, marca: str) -> str:
    """Devuelve el contenido del primer `<select>` que sigue a una marca.

    Args:
        html: Documento HTML.
        marca: Texto o atributo que identifica el selector.

    Returns:
        Contenido interno del `<select>`.
    """
    return html.split(marca, 1)[1].split("</select>", 1)[0]


def test_registrar_venta_ofrece_las_doce_categorias_exactas(
    cliente_admin: TestClient,
) -> None:
    """El panel y el cuadro de edición comparten las 12 categorías estándar."""
    html = cliente_admin.get("/olb-byte").text

    panel = _select_tras(html, 'data-campo-panel="categoria"')
    edicion = _select_tras(html, 'data-campo-edicion="categoria"')

    assert _opciones(panel) == list(CATEGORIAS_VENTA)
    assert _opciones(edicion) == list(CATEGORIAS_VENTA)


def test_pago_al_proveedor_usa_solo_dos_conceptos(cliente_admin: TestClient) -> None:
    """El campo Concepto es un selector cerrado con las dos opciones aprobadas."""
    html = cliente_admin.get("/olb-byte/cartera").text
    panel = html.split("Pago al proveedor", 1)[1].split("</form>", 1)[0]

    assert '<select class="campo__control" name="concepto" required>' in panel
    assert _opciones(_select_tras(panel, 'name="concepto"')) == list(CONCEPTOS_PROVEEDOR)


def test_registrar_falla_pone_descripcion_antes_del_producto(
    cliente_admin: TestClient, bd
) -> None:
    """La descripción va primero y ofrece las cuatro opciones definidas."""
    comercial.registrar_venta(
        bd,
        "Ana Pérez",
        "3001234567",
        [
            comercial.LineaVenta(
                nombre="Audífonos BT",
                categoria="Audífonos",
                cantidad=1,
                precio_unitario="50000",
                costo_unitario="30000",
            )
        ],
        comercial.ahora_tienda(),
    )

    html = cliente_admin.get("/olb-byte/garantias").text

    assert html.index("Descripción de la falla") < html.index("Producto con falla")
    descripcion = _select_tras(html, 'name="observacion"')
    assert _opciones(descripcion) == list(DESCRIPCIONES_FALLA)
    assert 'name="id_detalle"' in html
