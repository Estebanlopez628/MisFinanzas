"""Pruebas de la SRS v3.9.3 (fondo de gráficas, mensajes e icono comercial)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import esquemas
from app.routers import vistas

RUTA_APP = Path(__file__).resolve().parent.parent / "app"
CSS = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")


def test_fondo_del_consejero_igual_al_de_olas_graficas() -> None:
    """La tarjeta usa la superficie de .panel, sin negro profundo."""
    inicio = CSS.index(".cierre-deuda {")
    bloque = CSS[inicio : inicio + 400]
    assert "rgba(30, 41, 59, 0.75)" in bloque
    assert "var(--borde-suave)" in bloque
    assert "var(--radio-lg)" in bloque
    assert "#0F172A" not in bloque


def test_velocimetros_compactos_en_escritorio() -> None:
    """Dos columnas (640 px en v4.5), SVG 156x88 en web y 120x68 en móvil."""
    assert "max-width: 640px" in CSS
    assert "width: 120px" in CSS  # base móvil
    assert "height: 68px" in CSS
    assert "width: 156px" in CSS  # escritorio >= 768 px
    assert "height: 88px" in CSS
    assert "max-height: 170px" in CSS
    assert ".cierre-deuda__meses button" in CSS
    assert "background: transparent !important" in CSS

    html = (RUTA_APP / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert html.count('width="120" height="68"') == 2


def test_mensaje_de_tasa_implicita_sin_prefijos() -> None:
    """Pydantic no filtra nombres de campo ni 'Value error' al usuario."""
    with pytest.raises(ValueError) as error:
        esquemas.validar_formulario(
            esquemas.DeudaNueva,
            acreedor="Banco",
            saldo_total="1.200.000",
            cuota="100.000",
            cuotas_pendientes="5",
        )
    mensaje = str(error.value)
    assert "tasa_implicita" not in mensaje
    assert "Value error" not in mensaje
    assert mensaje.startswith("El número de cuotas por el valor de cuota")


def test_limpieza_de_prefijos_en_frontend() -> None:
    """El manejador HTTP quita cualquier prefijo técnico restante."""
    app_js = (RUTA_APP / "static/js/app.js").read_text(encoding="utf-8")
    assert "function limpiarMensajeError(texto)" in app_js
    assert "/^tasa_implicita:\\s*Value error,\\s*/i" in app_js
    assert "window.limpiarMensajeError = limpiarMensajeError" in app_js

    finanzas_js = (RUTA_APP / "static/js/finanzas.js").read_text(encoding="utf-8")
    assert "window.limpiarMensajeError(mensaje)" in finanzas_js


def test_icono_comercial_en_el_menu_de_olb_byte(cliente_admin: TestClient) -> None:
    """SRS v3.9.5: la tarjeta usa el PNG oficial, no una llave inglesa."""
    tarjeta = next(t for t in vistas.TARJETAS_DASHBOARD if t["clave"] == "olb-byte")
    assert tarjeta["icono"] == ""
    assert tarjeta["icono_archivo"] == "img/icono_OLBBYTE.png"
    assert "🛠" not in tarjeta["icono"]

    html = cliente_admin.get("/").text
    assert "icono_OLBBYTE.png" in html
