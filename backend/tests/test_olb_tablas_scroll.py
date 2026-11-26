"""Pruebas de límites de filas y cabecera opaca en OLB_BYTE."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.base_datos import FabricaSesiones
from app.servicios import comercial

RUTA = Path(__file__).resolve().parent.parent / "app"


def _css() -> str:
    """Lee la hoja principal.

    Returns:
        Contenido de `estilos.css`.
    """
    return (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")


def test_ranking_muestra_siete_filas_con_cabecera_opaca() -> None:
    """Ranking: siete filas y fondo sólido en la cabecera sticky."""
    css = _css()
    bloque = css.split(".tabla-contenedor--ranking {", 1)[1].split("}", 1)[0]
    assert "max-height: 336px" in bloque
    assert "overflow-y: auto" in bloque
    cabecera = css.split(".tabla-contenedor--ranking .tabla thead th {", 1)[1].split("}", 1)[0]
    assert "position: sticky" in cabecera
    assert "background: var(--bg-primary)" in cabecera
    plantilla = (RUTA / "templates/olb_byte/garantias.html").read_text(encoding="utf-8")
    assert "tabla-contenedor--ranking" in plantilla


def test_historial_gastos_muestra_cinco_filas_con_cabecera_opaca() -> None:
    """Historial: cinco filas en web y móvil, cabecera sin transparencia."""
    css = _css()
    bloque = css.split(".tabla-contenedor--gastos {", 1)[1].split("}", 1)[0]
    assert "max-height: 252px" in bloque
    cabecera = css.split(".tabla-contenedor--gastos .tabla thead th {", 1)[1].split("}", 1)[0]
    assert "background: var(--bg-primary)" in cabecera
    movil = css.split(".ordenes-moviles--gastos {", 1)[1].split("}", 1)[0]
    assert "max-height: 210px" in movil
    plantilla = (RUTA / "templates/olb_byte/cartera.html").read_text(encoding="utf-8")
    assert "tabla-contenedor--gastos" in plantilla
    assert "ordenes-moviles--gastos" in plantilla


def test_analitica_muestra_seis_productos_con_cabecera_opaca() -> None:
    """Ventas por producto: seis filas y cabecera sin transparencia."""
    css = _css()
    bloque = css.split(".tabla-contenedor--productos {", 1)[1].split("}", 1)[0]
    assert "max-height: 294px" in bloque
    cabecera = css.split(".tabla-contenedor--productos .tabla thead th {", 1)[1].split("}", 1)[0]
    assert "background: var(--bg-primary)" in cabecera
    plantilla = (RUTA / "templates/olb_byte/analitica.html").read_text(encoding="utf-8")
    assert "tabla-contenedor--productos" in plantilla


def test_ventas_muestra_cinco_ordenes_con_cabecera_opaca() -> None:
    """Órdenes registradas: cinco filas y cabecera sin transparencia."""
    css = _css()
    bloque = css.split(".tabla-contenedor--ordenes {", 1)[1].split("}", 1)[0]
    assert "max-height: 252px" in bloque
    cabecera = css.split(".tabla-contenedor--ordenes .tabla thead th {", 1)[1].split("}", 1)[0]
    assert "background: var(--bg-primary)" in cabecera
    plantilla = plantilla_ventas()
    assert "tabla-contenedor--ordenes" in plantilla


def plantilla_ventas() -> str:
    """Lee la plantilla de ventas.

    Returns:
        Contenido de `index.html`.
    """
    return (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")


def test_modal_de_gasto_en_movil_tiene_guardar_y_x(cliente_admin: TestClient) -> None:
    """El modal solo ofrece Guardar/Eliminar y cierra con la X roja uniforme."""
    with FabricaSesiones() as bd:
        comercial.registrar_gasto_operativo(bd, "10000", "2026-11-01")
    respuesta = cliente_admin.get("/olb-byte/cartera")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert ">Guardar</button>" in html
    assert ">Actualizar</button>" not in html
    # Fila móvil con etiquetas y fecha DD/MM/AA.
    assert "Fecha: 01/11/26" in html
    assert "Valor del gasto:" in html
    assert 'class="detalle-orden__cerrar" data-cerrar-dialogo' in html


def test_garantias_y_cartera_renderizan_las_tablas(cliente_admin: TestClient) -> None:
    """Ambas vistas siguen sirviendo sus tablas sin errores."""
    garantias = cliente_admin.get("/olb-byte/garantias")
    assert garantias.status_code == 200
    assert "Ranking de fallas" in garantias.text
    cartera = cliente_admin.get("/olb-byte/cartera")
    assert cartera.status_code == 200
    assert "Historial de gastos operativos" in cartera.text
