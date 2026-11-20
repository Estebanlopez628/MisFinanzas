"""Pantalla de acceso en producción: sin cuentas demo, a pantalla completa y pie limpio."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import crear_aplicacion


def test_login_no_muestra_cuentas_de_demostracion() -> None:
    """La pantalla de acceso no muestra correos ni contraseñas de demostración."""
    html = TestClient(crear_aplicacion()).get("/login").text

    assert "Cuentas de demostración" not in html
    assert "Admin123" not in html
    assert "Usuario123" not in html


def test_login_ocupa_toda_la_pantalla_sin_cabecera() -> None:
    """El login usa la clase de pantalla completa, que oculta la cabecera."""
    html = TestClient(crear_aplicacion()).get("/login").text

    assert 'class="pagina-acceso"' in html
    assert "Análisis de nómina y presupuesto" in html
    assert "Accede a tu cuadro" not in html


def test_pie_solo_muestra_finanzas_version_y_anio() -> None:
    """El pie no muestra el entorno y dice «Finanzas · v… | © año»."""
    html = TestClient(crear_aplicacion()).get("/login").text

    assert "Entorno:" not in html
    assert "Finanzas · v1.0.0" in html
    assert "© " in html
