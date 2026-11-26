"""Pruebas del retorno a «Órdenes registradas» conservando la posición (SRS v4.44)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.base_datos import FabricaSesiones
from app.modelos import Venta
from app.servicios import comercial

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_acciones_de_orden_marcan_la_salida_hacia_factura_y_whatsapp() -> None:
    """Ambas acciones comparten el marcador que guarda la posición."""
    plantilla = (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")
    # La macro se define una sola vez y se invoca en escritorio y móvil.
    assert plantilla.count("data-volver-ventas") == 2
    pos = plantilla.index("data-volver-ventas")
    assert "ver_factura" in plantilla[max(0, pos - 250) : pos + 250]
    pos = plantilla.index("data-volver-ventas", pos + 1)
    assert "data-compartir-factura" in plantilla[pos : pos + 250]


def test_app_guarda_y_restaura_posicion_de_ventas() -> None:
    """El guardado usa claves propias y se consume solo en /olb-byte."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    bloque = js[js.index("var CLAVE_OLB_X") : js.index("// SRS (abonos)")]
    assert 'CLAVE_OLB_X = "misfinanzas_olb_ventas_scroll_x"' in bloque
    assert 'CLAVE_OLB_Y = "misfinanzas_olb_ventas_scroll_y"' in bloque
    assert 'CLAVE_OLB_DIALOGO = "misfinanzas_olb_ventas_dialogo"' in bloque
    assert "data-volver-ventas" in bloque
    assert 'window.location.pathname.replace(/\\/$/, "") !== "/olb-byte"' in bloque
    assert "dialogo.showModal()" in bloque
    assert 'behavior: "instant"' in bloque
    assert "15 * 60 * 1000" in bloque


def test_la_factura_mantiene_el_enlace_de_regreso(cliente_admin: TestClient) -> None:
    """La página intermedia sigue ofreciendo «Volver a Ventas»."""
    with FabricaSesiones() as bd:
        venta = comercial.registrar_venta(
            bd,
            "Cliente QA",
            "3001234567",
            [
                comercial.LineaVenta(
                    nombre="Producto QA",
                    cantidad=1,
                    precio_unitario="10000",
                    costo_unitario="6000",
                )
            ],
        )
        id_venta = venta.id_venta
    respuesta = cliente_admin.get(f"/olb-byte/factura/{id_venta}")
    assert respuesta.status_code == 200
    assert "← Volver a Ventas" in respuesta.text
    assert "volver-ventas-factura" in respuesta.text
    assert 'class="factura-cerrar"' in respuesta.text
    css = (RUTA / "static/css/factura-olb.css").read_text(encoding="utf-8")
    movil = css.split("@media (max-width: 767px) {", 1)[1].split("@media print", 1)[0]
    assert ".factura-cerrar" in movil
    assert "box-shadow: 0 4px 14px rgba(239, 68, 68, 0.55)" in movil
