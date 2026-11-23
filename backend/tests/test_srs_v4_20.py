"""Pruebas de la SRS v4.20 (ajustes post-v4.19)."""

from __future__ import annotations

from datetime import date
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


def test_cabeceras_en_dos_lineas() -> None:
    """Las columnas 2 y 3 llevan salto de línea explícito."""
    html = (RUTA / "templates/chancucos/index.html").read_text(encoding="utf-8")
    assert "Valor a<br />Pagar" in html
    assert "Días de<br />Pago" in html
    assert "<th scope=\"col\">Descripción</th>" in html


def test_proyeccion_solo_escritorio() -> None:
    """La proyección se envuelve y se oculta bajo 768 px."""
    html = (RUTA / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert 'class="cierre-deuda__proyeccion"' in html
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.rfind(
        "@media (max-width: 767px) {", 0, css.index("SRS v4.20, sección 4")
    )
    bloque = css[inicio : inicio + 900]
    assert ".cierre-deuda__proyeccion" in bloque
    assert "display: none !important" in bloque
    assert "text-align: center !important" in bloque


def test_pluralizacion_y_redaccion() -> None:
    """«1 cuota» sin `(s)` y «realizando el pago mínimo» en el mensaje."""
    assert consejero._palabra_plazo(1, "cuota", "cuotas") == "cuota"
    assert consejero._palabra_plazo(5, "cuota", "cuotas") == "cuotas"
    assert consejero._palabra_plazo(1, "mes", "meses") == "mes"
    assert consejero._palabra_plazo(12, "mes", "meses") == "meses"


def test_redaccion_exacta_de_las_vinetas(bd) -> None:
    """Las tres viñetas siguen la plantilla de la SRS v4.20."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "82320", "16464", 5)
    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("645204"), date(2026, 11, 1)
    )
    pasos = resultado.pasos

    assert "en la deuda que tienes con Alkomprar" in pasos[0]
    assert "realizando el pago mínimo de la cuota" in pasos[0]
    paso_liberacion = next(
        paso for paso in pasos if "que te acabo de recomendar" in paso
    )
    assert "Al cerrar las deudas que te acabo de recomendar (" in paso_liberacion
    assert ") podrás liberar " in paso_liberacion
    assert "para tus próximas metas a pagar." in paso_liberacion
    assert "Realizando el pago mínimo, cerrarías todas tus deudas recomendadas" in pasos[-1]
    assert "con los abonos las cerrarías en" in pasos[-1]
    assert "realizando el pago mínimo" in resultado.mensaje
    assert "(1 cuota)" in resultado.mensaje
    assert "cuota(s)" not in resultado.mensaje


def test_plazo_solo_sobre_deudas_recomendadas(bd) -> None:
    """La deuda larga no recomendada no alarga el plazo del cierre."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Corta", "200000", "50000", 4)
    deudas.crear_deuda(bd, id_usuario, "Media", "400000", "50000", 8)
    deudas.crear_deuda(bd, id_usuario, "Otra", "300000", "50000", 6)
    deudas.crear_deuda(bd, id_usuario, "Hipoteca", "98400000", "600000", 164)

    resultado = consejero.consejo_financiero(
        bd, id_usuario, "Ana", Decimal("400000"), date(2026, 11, 1)
    )
    # MAX(4, 8, 6) = 8; la hipoteca (164) queda fuera del plan de 3 deudas.
    assert resultado.meses_base == 8
    assert resultado.cierre["meses_minimo"] == 8
    assert "Hipoteca" not in " ".join(resultado.pasos)
