"""Pruebas de la SRS v4.31: ancho KPI y grilla 3 × 3 de Nueva deuda."""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_formulario_nueva_deuda_orden_y_clases() -> None:
    """Los seis campos siguen el orden descriptivo → numérico y llevan clases."""
    html = (RUTA / "templates/deudas/index.html").read_text(encoding="utf-8")

    assert "fila-campos--deuda-nueva" in html
    assert "acciones-formulario--deuda-nueva" in html
    posiciones = [
        html.index(f'name="{nombre}"')
        for nombre in (
            "acreedor", "descripcion", "periodicidad",
            "saldo_total", "cuota", "cuotas_pendientes",
        )
    ]
    assert posiciones == sorted(posiciones)


def test_grilla_web_tres_columnas_y_pie() -> None:
    """La grilla web usa tres columnas, base alineada y pie con divisoria."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("SRS v4.28 / v4.31")
    bloque = css[inicio : inicio + 2000]

    assert "@media (min-width: 768px)" in bloque
    reglas_grilla = [
        parte.split("}", 1)[0] for parte in bloque.split(".fila-campos--deuda-nueva {")[1:]
    ]
    grilla = next(r for r in reglas_grilla if "grid-template-columns" in r)
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in grilla
    assert "align-items: end" in grilla
    assert "gap: 18px" in grilla
    reglas_pie = [
        parte.split("}", 1)[0]
        for parte in bloque.split(".acciones-formulario--deuda-nueva {")[1:]
    ]
    pie = next(r for r in reglas_pie if "border-top" in r)
    assert "border-top: 1px solid var(--borde-suave)" in pie
    assert "justify-content: center" in pie
