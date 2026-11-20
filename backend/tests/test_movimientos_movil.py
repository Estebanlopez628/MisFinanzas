"""Pruebas de los movimientos con el proveedor en móvil (SRS v1.9).

En celular la lista muestra fecha sin hora, concepto, monto y saldo; el detalle
completo (con hora y tipo) se abre en un diálogo al tocar la fila. La tabla de
escritorio no cambia.
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


def test_movimientos_en_movil_muestran_fecha_concepto_monto_y_saldo(
    cliente_admin: TestClient, bd
) -> None:
    """La lista móvil usa fecha sin hora, concepto, monto y saldo, y abre el detalle."""
    comercial.registrar_venta(
        bd,
        "Ana",
        "3001111111",
        [comercial.LineaVenta(nombre="Cable", cantidad=1, precio_unitario="50000", costo_unitario="20000")],
    )

    html = _html(cliente_admin.get("/olb-byte/cartera"))

    assert 'aria-label="Movimientos con el proveedor"' in html
    assert "orden-movil--movimiento" in html
    assert 'data-abrir-dialogo="movimiento-' in html
    assert 'class="detalle-orden" id="movimiento-' in html
    assert "Fecha y hora" in html
    assert "Saldo después" in html


def test_la_tabla_de_escritorio_de_movimientos_se_conserva(
    cliente_admin: TestClient, bd
) -> None:
    """La tabla completa sigue existiendo para escritorio, oculta en móvil."""
    comercial.registrar_venta(
        bd,
        "Ana",
        "3001111111",
        [comercial.LineaVenta(nombre="Cable", cantidad=1, precio_unitario="50000", costo_unitario="20000")],
    )

    html = _html(cliente_admin.get("/olb-byte/cartera"))

    assert "tabla-contenedor tabla-escritorio" in html
    assert "Compra a crédito" in html
