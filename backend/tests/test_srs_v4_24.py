"""Pruebas de la SRS v4.24: badge móvil, texto sin «/mes» y ancho alineado."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_cuota_sin_sufijo_mes() -> None:
    """La descripción de la tarjeta no alarga el texto con «/mes»."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert "cuota: {{ barra.cuota | cop }})" in html
    assert "{{ barra.cuota | cop }}/mes" not in html


def test_badge_web_y_movil() -> None:
    """El badge va en la cabecera en web y junto a «Pago mínimo» en móvil."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert "impacto-deuda__badge--web" in html
    assert "impacto-deuda__badge--movil" in html
    assert "impacto-deuda__etiqueta-grupo" in html
    # El badge móvil vive dentro del grupo de la etiqueta «Pago mínimo».
    inicio = html.index("impacto-deuda__etiqueta-grupo")
    bloque = html[inicio : inicio + 900]
    assert "Pago mínimo" in bloque
    assert "impacto-deuda__badge--movil" in bloque


def test_css_badges_y_ancho_movil() -> None:
    """Reglas responsive de badges y ancho compartido en móvil."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    movil = css.split("@media (max-width: 639px) {", 1)[1].split("}", 2)[0]
    assert ".impacto-deuda__badge--web" in movil
    assert "display: none" in movil
    assert ".impacto-deuda__badge--movil" in css

    ancho = css.split("@media (max-width: 767px) {")[-1]
    bloque = ancho.split(".cierre-deuda {", 1)[1].split("}", 1)[0]
    assert "padding: 14px" in bloque
    assert ".cierre-deuda__velocimetros," in ancho
    assert ".impacto-deudas {" in ancho
    assert "max-width: 100% !important" in ancho

    subtitulo = ancho.split(".impacto-deudas__subtitulo {", 1)[1].split("}", 1)[0]
    assert "background: rgba(16, 185, 129, 0.15)" in subtitulo
    assert "color: #6EE7B7" in subtitulo
    assert "font-size: 0.8rem" in subtitulo
    assert "border-radius: 14px" in subtitulo
    assert "text-align: center" in subtitulo
