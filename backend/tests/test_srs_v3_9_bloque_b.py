"""Pruebas de la SRS v3.9.1, bloque B (modales propios)."""

from __future__ import annotations

import re
from pathlib import Path

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def test_no_quedan_dialogos_nativos_en_el_codigo() -> None:
    """Auditoría global: cero llamadas a alert/confirm/prompt."""
    patron = re.compile(
        r"\b(?:window\.)?(?:alert|confirm|prompt)\s*\(",
        re.IGNORECASE,
    )
    encontrados: list[str] = []
    for ruta in RUTA_APP.rglob("*"):
        if ruta.suffix not in {".js", ".html"}:
            continue
        texto = ruta.read_text(encoding="utf-8")
        for numero, linea in enumerate(texto.splitlines(), 1):
            if patron.search(linea):
                encontrados.append(f"{ruta.name}:{numero}: {linea.strip()[:80]}")
    assert encontrados == [], "\n".join(encontrados)


def test_modales_propios_en_la_base() -> None:
    """Los dos modales oscuros están disponibles en todas las vistas."""
    html = (RUTA_APP / "templates/base.html").read_text(encoding="utf-8")
    assert 'id="modal-confirmacion"' in html
    assert 'id="modal-aviso"' in html
    assert "data-confirm-cancelar" in html
    assert "data-confirm-aceptar" in html
    assert "data-aviso-entendido" in html

    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    assert ".app-modal" in css
    assert "z-index: 9999" in css
    assert "background: var(--bg-card)" in css
    assert "background: #0F172A" in css


def test_app_js_usa_los_modales() -> None:
    """El sistema global reemplaza al antiguo confirm inline."""
    js = (RUTA_APP / "static/js/app.js").read_text(encoding="utf-8")
    for texto in (
        "function pedirConfirmacion(mensaje, peligro)",
        "function mostrarAvisoApp(mensaje)",
        "formulario.requestSubmit(control)",
        "data-confirmar",
    ):
        assert texto in js


def test_plantillas_migradas_a_data_confirmar() -> None:
    """Las acciones destructivas usan el atributo en vez de onclick inline."""
    revisar = (
        "templates/gastos/index.html",
        "templates/historial/index.html",
        "templates/incapacidades/index.html",
        "templates/chancucos/index.html",
        "templates/presupuesto/index.html",
    )
    for relativa in revisar:
        html = (RUTA_APP / relativa).read_text(encoding="utf-8")
        assert "data-confirmar=" in html, relativa
        assert "return confirm(" not in html, relativa
