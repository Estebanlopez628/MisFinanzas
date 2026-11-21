"""Pruebas de la SRS v3.1, bloque A+B (scroll de retorno y logo en factura)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def test_ids_de_los_formularios_de_origen(bd, cliente_usuario: TestClient) -> None:
    """Cada módulo de origen expone el id estable para el scroll."""
    from datetime import date

    from app.servicios import trabajos, usuarios

    cuenta = usuarios.buscar_por_correo(bd, "usuario@finanzas.co")
    assert cuenta is not None
    if not trabajos.listar_trabajos(bd, cuenta.id_usuario):
        trabajos.crear_trabajo(bd, cuenta.id_usuario, "Diseño", "300.000", date.today())

    finanzas = cliente_usuario.get("/finanzas").text
    presupuesto = cliente_usuario.get("/presupuesto").text
    trabajos_html = cliente_usuario.get("/trabajos-extras").text

    assert 'id="seccion-gastos-fijos-finanzas"' in finanzas
    assert 'id="seccion-deducciones-fijas"' in presupuesto
    assert 'id="seccion-gastos-fijos-trabajos-extras"' in trabajos_html
    assert finanzas.count('id="seccion-gastos-fijos-finanzas"') == 1
    assert trabajos_html.count('id="seccion-gastos-fijos-trabajos-extras"') == 1


def test_scroll_y_resaltado_tras_restaurar() -> None:
    """Tras restaurar se desplaza, resalta y enfoca el selector de deudas."""
    js = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")
    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")

    assert 'objetivo: "seccion-gastos-fijos-finanzas"' in js
    assert 'objetivo: "seccion-deducciones-fijas"' in js
    assert 'objetivo: "seccion-gastos-fijos-trabajos-extras"' in js
    assert "origin_objetivo: origen.objetivo" in js
    assert "window.requestAnimationFrame" in js
    assert "}, 150);" in js
    assert 'scrollIntoView({ behavior: "smooth", block: "center" })' in js
    assert 'classList.add("retorno-resaltado")' in js
    assert "}, 1500);" in js
    assert "selector.focus({ preventScroll: true })" in js
    assert ".retorno-resaltado" in css
    assert "#3B82F6" in css


def test_logo_del_modal_con_carga_estable() -> None:
    """El logo tiene carga temprana, dimensiones y fallback."""
    html = (RUTA_APP / "templates/olb_byte/_hoja_factura.html").read_text(encoding="utf-8")
    assert 'class="logo-ob-imagen"' in html
    assert 'loading="eager"' in html
    assert 'decoding="sync"' in html
    assert 'width="230" height="64"' in html
    assert "onerror=" in html


def test_captura_no_toca_el_logo_visible_y_copia_imagen() -> None:
    """La captura usa un clon fuera de pantalla y el logo visible se restaura."""
    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")
    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")

    assert "function protegerLogoVisible()" in js
    assert "var restaurarLogo = protegerLogoVisible();" in js
    assert "restaurarLogo();" in js
    assert 'position:fixed;left:-10000px' in js
    assert "navigator.clipboard" in js
    assert "new window.ClipboardItem" in js
    assert "Chat abierto y comprobante copiado: si deseas adjuntar la imagen, solo pulsa Pegar en el chat de WhatsApp" in js
    assert "function mostrarAviso(texto)" in js
    assert ".aviso-toast" in css
