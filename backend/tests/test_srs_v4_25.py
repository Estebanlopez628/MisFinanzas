"""Pruebas de la SRS v4.25: gráfica sin paréntesis y badge a la derecha."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, usuarios

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


def test_grafica_sin_parentesis_en_el_texto(cliente_admin: TestClient, bd) -> None:
    """Ningún rótulo visible de la gráfica usa paréntesis."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "197568", "16464", 12)

    html = cliente_admin.get("/presupuesto").text
    inicio = html.index('class="impacto-deudas"')
    bloque = html[inicio : html.index("</section>", inicio)]

    assert "(" not in bloque
    assert ")" not in bloque
    assert "Deuda de" in bloque
    assert "mes 1 cuota" in bloque or "meses" in bloque


def test_badge_porcentaje_alineado_a_la_derecha_en_movil() -> None:
    """En móvil la etiqueta va a la izquierda y el badge al extremo derecho."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.rfind("@media (max-width: 639px) {")
    movil = css[inicio : inicio + 800]

    assert ".impacto-deuda__etiqueta-grupo" in movil
    assert "justify-content: space-between" in movil
