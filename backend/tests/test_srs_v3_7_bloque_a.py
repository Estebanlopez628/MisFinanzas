"""Pruebas de la SRS v3.7, bloque A (atajos y WhatsApp nativo)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA_APP = Path(__file__).resolve().parent.parent / "app"
CSS = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")


def test_atajos_sin_scroll_lateral_y_columnas_alineadas() -> None:
    """El contenedor no se desplaza y cabecera/filas comparten rejilla."""
    html = (RUTA_APP / "templates/chancucos/index.html").read_text(encoding="utf-8")
    assert "tabla-contenedor--atajos" in html
    bloque = CSS.split("@media (max-width: 767px) {", 1)[1].split(".atajo-modal", 1)[0]
    assert "overflow-x: hidden" in bloque
    assert "grid-template-columns: fit-content(160px) max-content max-content" in bloque
    assert "text-align: right" in bloque
    assert "white-space: nowrap" in bloque


def test_copiado_de_imagen_intacto() -> None:
    """No se toca la lógica maestra de ClipboardItem."""
    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")
    assert "function copiarImagen(promesaBlob)" in js
    assert "navigator.clipboard" in js
    assert "new window.ClipboardItem({ \"image/png\": promesaBlob })" in js
    assert "data-compartir], [data-compartir-factura]" in js


def test_no_hay_descarga_automatica_al_compartir() -> None:
    """El compartir no guarda PNG en el dispositivo."""
    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")
    inicio = js.index("function enviarPorWhatsapp(boton)")
    fin = js.index("function descargarImagen(boton)")
    funcion = js[inicio:fin]
    assert "descargar(" not in funcion
    assert "link.click()" not in funcion
    assert "a.download" not in funcion


def test_squema_nativo_en_movil_y_web_en_escritorio() -> None:
    """iOS/Android usan whatsapp://send; el PC mantiene wa.me en _blank."""
    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")
    assert "var esMovil = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);" in js
    assert '"whatsapp://send?phone=" + numero' in js
    assert "window.location.href = enlaceNativo;" in js
    assert 'window.open(enlaceDirecto, "_blank", "noopener,noreferrer")' in js
