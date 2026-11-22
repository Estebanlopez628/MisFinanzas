"""Pruebas de la SRS v3.9.1, bloque A (deudas y fechas)."""

from __future__ import annotations

from pathlib import Path

from app.servicios import deudas

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def test_mensaje_amigable_sin_codigo_http() -> None:
    """El backend devuelve el texto literal, sin prefijo de error técnico."""
    mensaje = deudas.MENSAJE_CUOTAS_INSUFICIENTES
    assert mensaje == (
        "El valor total calculado entre el valor de la cuota y la cantidad de "
        "cuotas no alcanza a cubrir la totalidad de la deuda. Por favor, "
        "verifica nuevamente la información y digita correctamente los datos."
    )
    assert "Error 400" not in mensaje
    assert "400" not in mensaje


def test_validacion_en_vivo_en_la_vista() -> None:
    """La alerta va debajo del botón y el JS escucha los tres campos."""
    html = (RUTA_APP / "templates/deudas/index.html").read_text(encoding="utf-8")
    boton = html.index("data-guardar-deuda")
    alerta = html.index("data-alerta-deuda")
    assert boton < alerta
    assert 'class="alerta alerta--error" data-alerta-deuda' in html

    js = (RUTA_APP / "static/js/deudas.js").read_text(encoding="utf-8")
    assert "function numeroDeuda(texto)" in js
    assert "cuota * cuotas < total" in js
    assert "botonGuardar.disabled = insuficiente" in js
    assert 'classList.toggle("boton--deshabilitado", insuficiente)' in js
    assert "alertaDeuda.hidden = !insuficiente" in js
    for campo in ("saldo_total", "cuota", "cuotas_pendientes"):
        assert f'name="{campo}"' in js


def test_selectores_de_fecha() -> None:
    """Icono gris visible y apertura rápida con showPicker en escritorio."""
    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    assert "filter: invert(0.82) brightness(1.15)" in css
    assert "opacity: 0.9" in css
    assert "input[type=\"date\"]::-webkit-calendar-picker-indicator" in css

    js = (RUTA_APP / "static/js/app.js").read_text(encoding="utf-8")
    assert 'var esMovil = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);' in js
    assert 'campo.type !== "date"' in js
    assert "campo.showPicker();" in js
