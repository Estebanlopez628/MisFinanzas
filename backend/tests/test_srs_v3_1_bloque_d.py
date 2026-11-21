"""Pruebas de la SRS v3.1, bloque D (botones azules uniformes)."""

from __future__ import annotations

import re
from pathlib import Path

RUTA_PLANTILLAS = Path(__file__).resolve().parent.parent / "app" / "templates"


def test_todos_los_botones_de_retorno_son_azules() -> None:
    """Ningún «Volver/Regresar» conserva el estilo secundario gris."""
    patron = re.compile(r'class="boton boton--secundario[^"]*"[^>]*>\s*(?:←\s*)?(Volver|Regresar)')
    encontrados: list[str] = []
    for ruta in RUTA_PLANTILLAS.rglob("*.html"):
        texto = ruta.read_text(encoding="utf-8")
        if patron.search(texto):
            encontrados.append(str(ruta.relative_to(RUTA_PLANTILLAS)))
    assert encontrados == [], f"Botones de retorno aún grises: {encontrados}"


def test_botones_de_alta_son_azules() -> None:
    """Agregar gasto, agregar deducción y guardar incapacidad usan primario."""
    esperados = {
        "finanzas/index.html": "+ Agregar gasto fijo",
        "trabajos/index.html": "Agregar gasto fijo",
        "presupuesto/index.html": "Agregar deducción fija",
        "incapacidades/index.html": "Guardar incapacidad",
    }
    for relativa, texto_boton in esperados.items():
        html = (RUTA_PLANTILLAS / relativa).read_text(encoding="utf-8")
        indice = html.index(texto_boton)
        inicio = html.rfind("<button", 0, indice)
        etiqueta = html[inicio:indice]
        assert "boton--primario" in etiqueta, relativa


def test_volver_de_modulos_internos_es_azul() -> None:
    """Las vistas internas de OLB_BYTE y Ayuda comparten el azul institucional."""
    revisar = (
        "ayuda/index.html",
        "admin/comentarios.html",
        "deudas/index.html",
        "finanzas/index.html",
        "historial/index.html",
        "chancucos/index.html",
        "presupuesto/index.html",
        "trabajos/index.html",
        "olb_byte/index.html",
        "olb_byte/cartera.html",
        "olb_byte/factura.html",
        "olb_byte/pendientes.html",
        "olb_byte/recibo.html",
        "olb_byte/cobro.html",
        "olb_byte/garantias.html",
        "olb_byte/analitica.html",
        "olvide_contrasena.html",
    )
    for relativa in revisar:
        html = (RUTA_PLANTILLAS / relativa).read_text(encoding="utf-8")
        assert "boton--primario" in html, relativa
