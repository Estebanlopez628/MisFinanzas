"""Pruebas del límite de filas y opacidad de la cabecera de movimientos."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_movimientos_muestran_seis_filas() -> None:
    """El contenedor admite el encabezado más seis filas de 42 px."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".tabla-contenedor--movimientos {", 1)[1].split("}", 1)[0]
    assert "max-height: 296px" in bloque


def test_cabecera_de_movimientos_es_opaca() -> None:
    """Un selector más específico que `.tabla thead th` fija el fondo sólido."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".tabla-contenedor--movimientos .tabla thead th {", 1)[1].split("}", 1)[0]
    assert "background: var(--bg-primary)" in bloque
    assert "position: sticky" in bloque
    plantilla = (RUTA / "templates/olb_byte/cartera.html").read_text(encoding="utf-8")
    assert "seis filas visibles" in plantilla


def test_movimientos_en_movil_muestran_cuatro_filas() -> None:
    """La lista móvil se limita a cuatro filas con scroll vertical."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    media = css.split("@media (max-width: 640px) {", 1)[1]
    bloque = media.split(".ordenes-moviles--movimientos {", 1)[1].split("}", 1)[0]
    assert "max-height: 168px" in bloque
    assert "overflow-y: auto" in bloque
    plantilla = (RUTA / "templates/olb_byte/cartera.html").read_text(encoding="utf-8")
    assert "ordenes-moviles--movimientos" in plantilla
