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


def test_historial_gastos_muestra_diez_filas_en_web_y_seis_en_movil() -> None:
    """Historial: diez filas en web y seis en móvil, cabecera azul oscurecido."""
    css = _css()
    bloque = css.split(".tabla-contenedor--gastos {", 1)[1].split("}", 1)[0]
    assert "max-height: 412px" in bloque
    cabecera = css.split(".tabla-contenedor--gastos .tabla thead th {", 1)[1].split("}", 1)[0]
    assert "background-color: rgba(4, 18, 42, 0.68)" in cabecera
    movil = css.split(".ordenes-moviles--gastos {", 1)[1].split("}", 1)[0]
    assert "max-height: 264px" in movil
    grilla = css.split(".rejilla-paneles--cartera {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in grilla
    plantilla = (RUTA / "templates/olb_byte/cartera.html").read_text(encoding="utf-8")
    assert "tabla-contenedor--gastos" in plantilla
    assert "historial-gastos-table" in plantilla
    assert "col-acciones" in plantilla
    assert 'action="/olb-byte/proveedor/deudas-iniciales"' not in plantilla
    assert 'action="/olb-byte/migracion/deudas-iniciales"' not in plantilla


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
    bloque = css.split(".tabla-contenedor--ordenes,\n.tabla-contenedor--migracion {", 1)[1].split("}", 1)[0]
    assert "max-height: 252px" in bloque
    cabecera = css.split(".tabla-contenedor--ordenes .tabla thead th {", 1)[1].split("}", 1)[0]
    assert "background-color: rgba(4, 18, 42, 0.68)" in cabecera
    ancho = css.split(".tabla-contenedor--ordenes .tabla {", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in ancho
    assert "table-layout: fixed" in ancho
    sin_scroll = css.split("/* La tabla de órdenes cabe completa", 1)[1].split("}", 1)[0]
    assert "overflow-x: hidden" in sin_scroll
    plantilla = plantilla_ventas()
    assert "tabla-contenedor--ordenes" in plantilla


def plantilla_ventas() -> str:
    """Lee la plantilla de ventas.

    Returns:
        Contenido de `index.html`.
    """
    return (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")


def test_color_de_cabeceras_y_buscardor_igual_al_de_campos() -> None:
    """Todas las cabeceras y el buscador usan el azul de los cuadros de texto."""
    css = _css()
    for selector in (
        ".tabla-contenedor--gastos .tabla thead th {",
        ".tabla-contenedor--ordenes .tabla thead th {",
        ".ordenes-moviles--ordenes .orden-movil--cabecera,",
        ".formulario--buscar .campo__etiqueta {",
    ):
        bloque = css.split(selector, 1)[1].split("}", 1)[0]
        assert "rgba(4, 18, 42, 0.68)" in bloque


def test_ajustes_finales_de_fechas_botones_y_movil() -> None:
    """Fecha DD/MM/AAAA, botones a la derecha y cinco órdenes en móvil."""
    css = _css()
    cartera = (RUTA / "templates/olb_byte/cartera.html").read_text(encoding="utf-8")
    ventas = plantilla_ventas()
    assert "%d/%m/%Y" in cartera
    assert "%m/%d/%Y" not in cartera
    acciones = css.split(".tabla.historial-gastos-table thead th.col-acciones,", 1)[1].split("}", 1)[0]
    assert "width: 34%" in acciones
    assert "ordenes-moviles--ordenes" in ventas
    movil = css.split(".ordenes-moviles--ordenes {", 1)[1].split("}", 1)[0]
    assert "max-height: 280px" in movil
    assert "overflow-y: auto" in movil


def test_modal_de_gasto_conserva_el_scroll(cliente_admin: TestClient) -> None:
    """Al abrir el modal se guarda la posición y se restaura tras la recarga."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    bloque = js.split('var abrir = objetivo.closest("[data-abrir-dialogo]");', 1)[1].split("return;", 1)[0]
    assert "guardarScroll()" in bloque
    assert "}, 1000);" in js


def test_historial_movil_es_tabla_limpia_de_tres_columnas() -> None:
    """La fila móvil lleva FECHA | DESCRIPCIÓN | VALOR, alineados y sin prefijos."""
    css = _css()
    rejilla = css.split(".ordenes-moviles--gastos .orden-movil {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 1fr 1.6fr 1fr" in rejilla
    limpio = css.split(".ordenes-moviles--gastos .orden-movil span {", 1)[1].split("}", 1)[0]
    assert "overflow: visible" in limpio
    assert "text-overflow: clip" in limpio
    assert "white-space: normal" in limpio
    valor = css.split(".ordenes-moviles--gastos .orden-movil__valor {", 1)[1].split("}", 1)[0]
    assert "var(--accent-green)" in valor
    assert "text-align: left" in valor
    corte = css.split("@media (min-width: 641px) and (max-width: 767px) {", 1)[1][:300]
    assert ".tabla-contenedor--gastos" in corte and "display: none" in corte
    plantilla = (RUTA / "templates/olb_byte/cartera.html").read_text(encoding="utf-8")
    lista = plantilla.split('<ul class="ordenes-moviles ordenes-moviles--gastos"', 1)[1].split("</ul>", 1)[0]
    assert "<span>Fecha</span><span>Descripción</span><span>Valor</span>" in lista
    assert "orden-movil__fecha" in lista and "orden-movil__valor" in lista
    assert "Fecha:" not in lista and "Valor del gasto:" not in lista


def test_modal_de_gasto_en_movil_tiene_actualizar_y_x(cliente_admin: TestClient) -> None:
    """El modal ofrece Actualizar/Eliminar, cierra con la X y queda sobre todo."""
    with FabricaSesiones() as bd:
        comercial.registrar_gasto_operativo(bd, "10000", "2026-11-01")
    respuesta = cliente_admin.get("/olb-byte/cartera")
    assert respuesta.status_code == 200
    html = respuesta.text
    assert ">Actualizar</button>" in html
    assert ">Guardar</button>" not in html
    # Fila móvil limpia: fecha MM/DD/YYYY a la izquierda y monto a la derecha.
    assert "01/11/2026" in html
    assert "orden-movil__fecha" in html
    assert "Fecha:" not in html
    assert "Valor del gasto:" not in html
    assert 'class="detalle-orden__cerrar" data-cerrar-dialogo' in html
    assert "dialog.detalle-orden {" in _css()


def test_garantias_y_cartera_renderizan_las_tablas(cliente_admin: TestClient) -> None:
    """Ambas vistas siguen sirviendo sus tablas sin errores."""
    garantias = cliente_admin.get("/olb-byte/garantias")
    assert garantias.status_code == 200
    assert "Ranking de fallas" in garantias.text
    cartera = cliente_admin.get("/olb-byte/cartera")
    assert cartera.status_code == 200
    assert "Historial de gastos operativos" in cartera.text
