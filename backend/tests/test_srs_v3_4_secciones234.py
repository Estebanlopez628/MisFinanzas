"""Pruebas de la SRS v3.4, secciones 2 a 4."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA_APP = Path(__file__).resolve().parent.parent / "app"
CSS = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")


def test_columnas_compactas_en_atajos_movil() -> None:
    """SRS v4.42: la tabla se desliza, con columnas 38/34/28 y sin recortes."""
    inicio = CSS.index(".tabla-contenedor--atajos {", CSS.index("@media (max-width: 767px)"))
    contenedor = CSS[inicio : CSS.index("}", inicio)]
    assert "overflow-x: auto" in contenedor
    assert "width: max-content" in CSS
    assert "min-width: 100%" in CSS
    assert "max-width: none !important" in CSS


def test_boton_de_factura_usa_la_funcion_maestra(cliente_admin: TestClient) -> None:
    """El modal «Ver factura» invoca el mismo manejador que el ícono rápido."""
    html = (RUTA_APP / "templates/olb_byte/factura.html").read_text(encoding="utf-8")
    assert "data-compartir" in html
    assert "data-compartir-factura" in html
    assert "data-fragmento=" in html

    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")
    assert '[data-compartir], [data-compartir-factura]' in js
    assert "enviarPorWhatsapp(evento.currentTarget)" in js
    assert "navigator.clipboard" in js
    assert "new window.ClipboardItem" in js


def test_apertura_externa_y_icono_siempre_visible() -> None:
    """Sin navegación en la misma pestaña y sin ocultar el ícono de WhatsApp."""
    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")
    assert 'window.open(enlaceDirecto, "_blank", "noopener,noreferrer")' in js
    assert "window.location.href = enlaceDirecto" not in js
    assert 'boton.textContent = "Preparando…"' not in js
    assert 'boton.setAttribute("aria-busy", "true")' in js
    assert 'boton.removeAttribute("aria-busy")' in js
    assert "function finalizar()" in js
    assert "} catch (error) {" in js


def test_etiqueta_registrar_pago(cliente_admin: TestClient) -> None:
    """El botón de abonos dice «Registrar Pago» en todas las vistas."""
    cobro = (RUTA_APP / "templates/olb_byte/cobro.html").read_text(encoding="utf-8")
    pendientes = (RUTA_APP / "templates/olb_byte/pendientes.html").read_text(encoding="utf-8")
    cartera = (RUTA_APP / "templates/olb_byte/cartera.html").read_text(encoding="utf-8")
    assert ">Registrar Pago</button>" in cobro
    assert ">Registrar Pago</a>" in pendientes
    assert ">Registrar Pago</button>" in cartera
    assert "Registrar Abono / Pago Total" in cobro


def test_scroll_de_ida_a_nueva_deuda(cliente_usuario: TestClient) -> None:
    """El formulario «Nueva deuda» tiene id y el flag de ida se consume."""
    html = cliente_usuario.get("/deudas").text
    assert 'id="seccion-nueva-deuda"' in html

    categorias = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")
    deudas_js = (RUTA_APP / "static/js/deudas.js").read_text(encoding="utf-8")
    assert 'sessionStorage.setItem("misfinanzas_scroll_to_new_debt", "true")' in categorias
    assert 'sessionStorage.getItem("misfinanzas_scroll_to_new_debt") === "true"' in deudas_js
    assert 'sessionStorage.removeItem("misfinanzas_scroll_to_new_debt")' in deudas_js
    assert 'document.getElementById("seccion-nueva-deuda")' in deudas_js
    assert 'classList.add("retorno-resaltado")' in deudas_js


def test_validacion_de_registro_real_de_la_deuda(cliente_usuario: TestClient) -> None:
    """Solo se marca SI cuando el backend confirmó la deuda creada."""
    html = cliente_usuario.get("/deudas?guardado=1").text
    assert "pendiente.debt_created = true" in html
    assert "pendiente.created_debt_id" in html

    js = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")
    assert "debt_created: false" in js
    assert "created_debt_id: null" in js
    assert "pendiente.debt_created === true" in js
    assert "opcionNo.checked = true" in js


def test_valor_se_bloquea_y_desbloquea_segun_categoria() -> None:
    """El cambio de categoría gobierna de inmediato el campo Valor."""
    js = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")
    inicio = js.index("function sincronizarValor()")
    bloque = js[inicio : inicio + 2200]
    assert 'entradaCategoria.value === CATEGORIA_CREDITO' in bloque
    assert 'campoValor.placeholder = "Se cargará desde la deuda"' in bloque
    assert "campoValor.value = \"\"" in bloque
    assert "campoValor.readOnly = false" in bloque
    assert "campoValor.readOnly = true" in bloque
    assert "classList.remove(\"campo__control--bloqueado\")" in bloque
