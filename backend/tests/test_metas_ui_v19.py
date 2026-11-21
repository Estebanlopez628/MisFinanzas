"""Pruebas de los ajustes visuales de «Mis metas y abonos» (SRS v1.9)."""

from __future__ import annotations

from pathlib import Path

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"


def test_los_abonos_muestran_dos_filas_en_escritorio() -> None:
    """La caja de abonos limita la altura y hace scroll internamente."""
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".abonos-scroll {", 1)[1].split("}", 1)[0]

    assert "max-height: 180px;" in bloque
    assert "overflow-y: auto;" in bloque
    assert "opacity" not in bloque
    assert "transform" not in bloque


def test_el_boton_eliminar_va_arriba_a_la_derecha_en_movil() -> None:
    """La cabecera de la meta no se envuelve: Eliminar queda junto al título."""
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    movil = css.split("@media (max-width: 640px)", 1)[1]

    cabecera = movil.split(".meta__cabecera {", 1)[1].split("}", 1)[0]
    assert "flex-wrap: nowrap;" in cabecera
    assert "align-items: flex-start;" in cabecera
    assert ".meta__cabecera form {" in movil
    assert "flex: 0 0 auto;" in movil


def test_el_texto_ayuda_refleja_dos_filas() -> None:
    """El aviso dice cuántas filas se ven, sin prometer cinco abonos."""
    plantilla = (RAIZ_APP / "templates" / "presupuesto" / "index.html").read_text(encoding="utf-8")

    assert "Se ven dos filas de abonos" in plantilla
    assert "Se ven 5 abonos" not in plantilla
