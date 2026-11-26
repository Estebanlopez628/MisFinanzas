"""Pruebas de la estructura de la interfaz de OLB_BYTE (formulario de venta v2).

Comprueban lo que el servidor entrega al navegador: el submenú superior, el botón de
contactos oculto cuando no hay API, y que los campos del panel de producto no se
envían sin pasar por la tabla de detalle. El comportamiento en vivo se valida en el
navegador; estas pruebas fijan la estructura que el JavaScript necesita.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

RAIZ_ESTATICOS = Path(__file__).resolve().parent.parent / "app" / "static"


def _etiquetas_con(html: str, atributo: str) -> list[str]:
    """Devuelve las etiquetas <input> que contienen un atributo dado.

    Args:
        html: Documento HTML.
        atributo: Nombre del atributo buscado, por ejemplo `data-campo-panel`.

    Returns:
        Lista con el texto completo de cada etiqueta.
    """
    return [
        etiqueta
        for etiqueta in re.findall(r"<input[^>]*>", html)
        if f" {atributo}=" in etiqueta
    ]


def test_submenu_de_olb_byte_queda_arriba(cliente_admin: TestClient) -> None:
    """El submenú con las cinco secciones renombradas va bajo el encabezado."""
    texto = cliente_admin.get("/olb-byte").text

    assert "subnav-finanzas" in texto
    for ruta in ("/olb-byte/pendientes", "/olb-byte/cartera", "/olb-byte/garantias", "/olb-byte/analitica"):
        assert re.search(rf'href="[^"]*{re.escape(ruta)}"', texto)
    for etiqueta in (
        "Registro de ventas",
        "Cuentas por cobrar",
        "Cartera y pagos a proveedores",
        "Soporte y garantías",
        "Gestión y control de ventas",
    ):
        assert etiqueta in texto
    assert "Ver pendientes de pago (" not in texto
    assert texto.index("subnav-finanzas") < texto.index("Registrar venta")


def _pestana_activa(html: str) -> str:
    """Devuelve el texto de la pestaña marcada como página actual del submenú.

    Args:
        html: Documento HTML de la vista.

    Returns:
        Texto del enlace con `aria-current="page"`, o cadena vacía si no hay ninguno.
    """
    coincidencia = re.search(
        r'<a[^>]*aria-current="page"[^>]*>\s*(.*?)\s*</a>', html, flags=re.S
    )
    return coincidencia.group(1) if coincidencia else ""


def test_submenu_marca_la_seccion_activa_en_cada_vista(cliente_admin: TestClient) -> None:
    """Cada vista resalta su propia pestaña del submenú."""
    assert _pestana_activa(cliente_admin.get("/olb-byte/pendientes").text) == "Cuentas por cobrar"
    assert _pestana_activa(cliente_admin.get("/olb-byte/analitica").text) == "Gestión y control de ventas"
    assert _pestana_activa(cliente_admin.get("/olb-byte").text) == "Registro de ventas"


def test_titulo_principal_de_analitica_es_gestion_y_control(cliente_admin: TestClient) -> None:
    """El encabezado de Analítica y su título del navegador coinciden con la pestaña."""
    texto = cliente_admin.get("/olb-byte/analitica").text

    assert "📈 Gestión y control de ventas" in texto
    assert "Gestión y control de ventas · OLB BYTE</title>" in texto
    assert "📈 Gestión de ventas y control" not in texto


def test_encabezados_de_las_pestanas_coinciden_con_sus_nombres(cliente_admin: TestClient) -> None:
    """Cada vista muestra el nombre de su pestaña en el encabezado con emoji."""
    esperados = {
        "/olb-byte/pendientes": ("⏳", "Cuentas por cobrar"),
        "/olb-byte/cartera": ("📊", "Cartera y pagos a proveedores"),
        "/olb-byte/garantias": ("🛡️", "Soporte y garantías"),
        "/olb-byte/analitica": ("📈", "Gestión y control de ventas"),
    }
    for ruta, (emoji, nombre) in esperados.items():
        html = cliente_admin.get(ruta).text
        assert f'<h1 class="heroe__titulo">{emoji} {nombre}</h1>' in html
        assert f"{nombre} · OLB BYTE</title>" in html


def test_boton_pegar_numero_reemplaza_a_contactos(cliente_admin: TestClient) -> None:
    """El botón de número aparece con un solo rótulo y sin buscador de contactos."""
    texto = cliente_admin.get("/olb-byte").text

    assert "data-pegar-numero" in texto
    rotulo = texto.split("data-pegar-numero>", 1)[1].split("</button>", 1)[0]
    assert "Agregar Numero" in rotulo
    assert "Pegar número" not in rotulo
    assert "Buscar en Contactos" not in texto


def test_regla_global_de_hidden_esta_en_el_css() -> None:
    """El CSS oculta siempre los elementos con `hidden`, aunque tengan otra clase de display."""
    css = (RAIZ_ESTATICOS / "css" / "estilos.css").read_text(encoding="utf-8")

    assert "[hidden] {\n  display: none !important;" in css


def test_campos_del_panel_no_se_envian_sin_pasar_por_la_tabla(cliente_admin: TestClient) -> None:
    """Los campos del panel de producto no tienen `name`: solo viajan las filas de la tabla."""
    texto = cliente_admin.get("/olb-byte").text
    campos_panel = _etiquetas_con(texto, "data-campo-panel")

    assert len(campos_panel) == 6
    assert all(" name=" not in etiqueta for etiqueta in campos_panel)


def test_el_detalle_viaja_en_campos_ocultos_por_fila(cliente_admin: TestClient, bd) -> None:
    """Tras un error, cada producto vuelve a la tabla como fila con campos ocultos."""
    datos = {
        "cliente_nombre": "Ana",
        "cliente_telefono": "",
        "producto_nombre": ["Audífonos BT", ""],
        "categoria": ["Audio", ""],
        "cantidad": ["2", "1"],
        "costo_unitario": ["30000", ""],
        "precio_unitario": ["", ""],
        "garantia_meses": ["3", ""],
    }

    respuesta = cliente_admin.post("/olb-byte/ventas", data=datos)

    assert respuesta.status_code == 400
    assert 'data-fila-producto' in respuesta.text
    assert re.search(r'type="hidden" name="producto_nombre" value="Audífonos BT"', respuesta.text)
    assert re.search(r'type="hidden" name="categoria" value="Audio"', respuesta.text)


def test_cuadro_de_edicion_tiene_actualizar_y_cancelar(cliente_admin: TestClient) -> None:
    """El cuadro «Actualizar producto» trae sus dos botones en la misma fila."""
    texto = cliente_admin.get("/olb-byte").text

    assert "dialogo-edicion" in texto
    assert "fila-acciones-dialogo" in texto
    assert "data-guardar-edicion" in texto
    assert "data-cancelar-edicion" in texto


def test_pendientes_y_cartera_usan_el_submenu(cliente_admin: TestClient) -> None:
    """Las vistas de cobro y cartera ya no traen botones de «Volver al panel»."""
    for ruta in ("/olb-byte/pendientes", "/olb-byte/cartera", "/olb-byte/garantias", "/olb-byte/analitica"):
        texto = cliente_admin.get(ruta).text
        assert "subnav-finanzas" in texto
        assert "Volver al panel" not in texto

def test_cada_pantalla_de_olb_byte_tiene_boton_volver(cliente_admin: TestClient, bd) -> None:
    """Cada pantalla del módulo ofrece un botón para regresar al menú anterior."""
    from app.servicios import comercial

    venta = comercial.registrar_venta(
        bd,
        "Ana",
        None,
        [comercial.LineaVenta(nombre="Cable", cantidad=1, precio_unitario="1000", costo_unitario="500")],
    )
    abono = comercial.registrar_abono(bd, venta.id_venta, "100")
    rutas = [
        "/olb-byte",
        "/olb-byte/pendientes",
        f"/olb-byte/ventas/{venta.id_venta}/cobro",
        "/olb-byte/cartera",
        "/olb-byte/garantias",
        "/olb-byte/analitica",
        f"/olb-byte/factura/{venta.id_venta}",
        f"/olb-byte/recibos/{abono.id_abono}",
    ]
    for ruta in rutas:
        texto = cliente_admin.get(ruta).text
        assert "Volver" in texto, ruta
