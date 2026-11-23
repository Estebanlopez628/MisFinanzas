"""Pruebas de la SRS v4.23: fecha compacta, texto sin recorte y fondo."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.servicios import consejero, deudas, usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


def _id_admin(bd) -> str:
    """Devuelve el identificador del administrador sembrado.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador del administrador de pruebas.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def _consejo(bd):
    """Siembra una deuda y devuelve el consejo activo.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Consejo financiero con cierre calculado.
    """
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "197568", "16464", 12)
    return consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("2000000"))


def test_fecha_corta_en_formato_mes_anio(bd) -> None:
    """La barra azul recibe «MM/AAAA» en vez del nombre del mes."""
    barra = _consejo(bd).cierre["barras_deuda"][0]
    fecha = barra["fecha_cierre_base_corta"]
    assert len(fecha) == 7
    assert fecha[2] == "/"
    assert fecha[:2].isdigit() and fecha[3:].isdigit()


def test_plantilla_usa_la_fecha_corta() -> None:
    """La etiqueta visible de la barra usa la fecha compacta."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert "barra.fecha_cierre_base_corta" in html
    assert "barra.fecha_cierre_base }}" not in html


def test_barra_no_recorta_y_fondo_es_el_de_los_velocimetros() -> None:
    """La barra crece con su texto y el recuadro usa el fondo del cockpit."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    barra = css.split(".impacto-deuda__barra {", 1)[1].split("}", 1)[0]
    assert "min-width: max-content" in barra
    assert "overflow: visible" in barra
    assert "overflow: hidden" not in barra

    contenedor = next(
        bloque.split("}", 1)[0]
        for bloque in css.split(".impacto-deudas {")[1:]
        if "background:" in bloque.split("}", 1)[0]
    )
    assert "background: rgba(15, 23, 42, 0.55)" in contenedor
    assert "border: 1px solid rgba(148, 163, 184, 0.16)" in contenedor
