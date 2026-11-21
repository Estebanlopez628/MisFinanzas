"""Pruebas del renombramiento y alineación del módulo de deudas (SRS v1.9, 2.1).

Verifican que el nombre nuevo aparezca en navegación, encabezado y título, y
que la regla CSS que nivela los dos paneles en escritorio exista y se aplique.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, usuarios

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"
NOMBRE = "Registro y Detalles de deudas"


def test_el_dashboard_usa_el_nombre_nuevo(cliente_admin: TestClient) -> None:
    """La tarjeta de navegación lleva el título actualizado."""
    html = cliente_admin.get("/").text

    assert NOMBRE in html
    assert "Resumen de Deudas" not in html


def test_la_vista_de_deudas_usa_el_nombre_en_titulo_y_encabezado(
    cliente_admin: TestClient,
) -> None:
    """El `<title>`, el `<h1>` y el contexto de la página usan el nombre nuevo."""
    respuesta = cliente_admin.get("/deudas")
    html = respuesta.text

    assert respuesta.status_code == 200
    assert html.count(NOMBRE) >= 2
    assert "📉 " + NOMBRE in html
    assert "Resumen de Deudas" not in html
    assert "Nueva deuda" in html
    assert "Deudas registradas" in html
    # Una sola fila por deuda: sin bloque de cuotas ni mensaje de deuda vacía.
    assert "fila-detalle-deuda" not in html
    assert "Esta deuda no tiene cuotas aplicadas." not in html


def test_la_tabla_tipo_excel_no_muestra_próximas_cuotas_ni_intereses(
    cliente_admin: TestClient, bd
) -> None:
    """La tabla usa las seis columnas pedidas y solo muestra cuotas aplicadas."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    deudas.crear_deuda(bd, cuenta.id_usuario, "Banco", "1.200.000", "300.000", 4)

    html = cliente_admin.get("/deudas").text

    for columna in (
        "Acreedor",
        "Total Adeudado",
        "Cuota",
        "No. de",
        "Periodicidad",
        "Estado",
    ):
        assert columna in html
    assert html.count('scope="col"') == 7  # seis columnas + acciones
    assert "Próximas cuotas" not in html
    assert "Esta deuda no tiene cuotas aplicadas." not in html
    assert "fila-detalle-deuda" not in html
    assert "tabla-contenedor--deudas" in html
    assert 'class="deudas__cuotas"' in html
    assert "deudas__acciones-contenido" in html
    assert 'name="tasa_interes"' not in html
    assert "interés" not in html.lower().replace("sin simular intereses", "")


def test_la_edicion_es_un_modal_centrado_con_tres_campos_y_dos_botones(
    cliente_admin: TestClient, bd
) -> None:
    """El lápiz abre el modal con Total, Cuota y Cuotas, Actualizar y Cancelar."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    deuda = deudas.crear_deuda(bd, cuenta.id_usuario, "Banco", "1.200.000", "300.000", 4)

    html = cliente_admin.get("/deudas").text

    assert 'class="fila-deuda" data-deuda-fila' in html
    assert f'data-id-deuda="{deuda.id_deuda}"' in html
    assert "edicion-gasto edicion-gasto--modal" in html
    assert "boton-circular--editar" in html
    assert f"/deudas/{deuda.id_deuda}/editar" in html
    assert 'name="saldo_total"' in html
    assert 'name="cuota"' in html
    assert 'name="cuotas_pendientes"' in html
    assert 'name="acreedor"' in html
    assert ">Actualizar</button>" in html
    assert "data-cancelar-edicion" in html
    assert 'aria-label="Eliminar Banco"' in html
    assert "js/deudas.js" in html


def test_la_fila_completa_es_táctil_en_móvil_y_el_modal_está_en_la_caché() -> None:
    """El JS abre el modal al tocar la fila en móvil y se ocultan los iconos."""
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    javascript = (RAIZ_APP / "static" / "js" / "deudas.js").read_text(encoding="utf-8")
    service_worker = (RAIZ_APP / "static" / "js" / "sw.js").read_text(encoding="utf-8")

    assert ".tabla--deudas .fila-deuda" in css
    assert "cursor: pointer;" in css
    assert ".deudas__acciones-contenido {" in css
    assert "vertical-align: middle;" in css
    assert ".tabla--deudas .deudas__cuotas {" in css
    assert ".tabla--deudas .fila-deuda > .deudas__acciones > .deudas__acciones-contenido > details > summary" in css
    assert "data-deuda-fila" in javascript
    assert "matchMedia" in javascript
    assert "js/deudas.js" in service_worker


def test_los_paneles_de_escritorio_comparten_la_misma_altura() -> None:
    """La rejilla estira ambos paneles y anula el margen superior del de tabla."""
    plantilla = (RAIZ_APP / "templates" / "deudas" / "index.html").read_text(encoding="utf-8")
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")

    assert 'rejilla-paneles rejilla-paneles--deudas' in plantilla
    assert ".rejilla-paneles--deudas {" in css
    rejilla = css.split(".rejilla-paneles--deudas {", 1)[1].split("}", 1)[0]
    assert "align-items: stretch;" in rejilla
    assert ".rejilla-paneles--deudas > .panel--tabla {" in css
    # La regla específica debe ir después del margin-top genérico para ganar.
    assert css.index(".rejilla-paneles--deudas > .panel--tabla {") > css.index(".panel--tabla {")
    bloque = css.split(".rejilla-paneles--deudas > .panel--tabla {", 1)[1].split("}", 1)[0]
    assert "margin-top: 0;" in bloque

    # La tabla muestra cuatro filas y permite scroll vertical y horizontal.
    tabla = css.split(".tabla-contenedor--deudas {", 1)[1].split("}", 1)[0]
    assert "max-height: 340px;" in tabla  # cuatro deudas en escritorio
    assert "overflow: auto;" in tabla
    assert "overscroll-behavior: contain;" in tabla
    assert "touch-action: pan-x pan-y;" in tabla
    assert "-webkit-overflow-scrolling: touch;" in tabla
    assert "max-width: 100%;" in tabla
    assert "\n  contain: paint;" not in tabla  # rompería el modal dentro de la tabla

    cabecera = css.split(".tabla-contenedor--deudas thead th {", 1)[1].split("}", 1)[0]
    assert "background: var(--bg-primary);" in cabecera
    assert "var(--bg-card)" not in cabecera
    assert "position: sticky;" in cabecera

    movil_tabla = (
        "@media (max-width: 640px) {\n"
        "  .tabla-contenedor--deudas {\n"
        "    max-height: 280px;"
    )
    assert movil_tabla in css  # la altura anterior se mantiene en móvil
