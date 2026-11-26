"""Pruebas del buscador y modal de «Pendientes de pago» (SRS v4.44)."""

from __future__ import annotations

from pathlib import Path

from app.core.base_datos import FabricaSesiones
from app.servicios import comercial

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_buscador_de_pendientes_sin_linea_superior() -> None:
    """El formato compacto no dibuja su divisor sobre el buscador."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".formulario--buscar {", 1)[1].split("}", 1)[0]
    assert "border-top: 0" in bloque
    assert "padding-top: 0" in bloque


def test_modal_de_pendientes_solo_ofrece_registrar_pago() -> None:
    """Se retira «Volver a pendientes de pago» y se añade la X rojiza."""
    plantilla = (RUTA / "templates/olb_byte/pendientes.html").read_text(encoding="utf-8")
    assert "Volver a pendientes de pago" not in plantilla
    assert 'class="pendiente-cerrar" data-cerrar-dialogo' in plantilla
    assert ">Registrar Pago</a>" in plantilla
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    cierre = css.split(".pendiente-cerrar {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in cierre
    assert "rgba(239, 68, 68, 0.14)" in cierre
    assert "color: #fecaca" in cierre


def test_vista_de_pendientes_con_orden_pendiente(cliente_admin) -> None:
    """La plantilla renderiza el buscador y el modal sin el botón de regreso."""
    with FabricaSesiones() as bd:
        comercial.registrar_venta(
            bd,
            "Cliente Pendiente",
            "3005554433",
            [
                comercial.LineaVenta(
                    nombre="Producto pendiente",
                    cantidad=1,
                    precio_unitario="20000",
                    costo_unitario="12000",
                )
            ],
        )
    respuesta = cliente_admin.get("/olb-byte/pendientes")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Buscar por cliente, celular o número de orden" in html
    assert 'class="pendiente-cerrar"' in html
    assert "Volver a pendientes de pago" not in html
