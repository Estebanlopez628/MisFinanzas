"""Pruebas del botón «Pegar Numero» en Registro de ventas y Migración de Cartera."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA = Path(__file__).resolve().parent.parent / "app"


def plantilla_leida(nombre: str) -> str:
    """Lee una plantilla del módulo comercial.

    Args:
        nombre: Archivo dentro de `templates/olb_byte`.

    Returns:
        Contenido de la plantilla.
    """
    return (RUTA / "templates/olb_byte" / nombre).read_text(encoding="utf-8")


def javascript_leido(nombre: str) -> str:
    """Lee un JavaScript estático del módulo comercial.

    Args:
        nombre: Archivo dentro de `static/js`.

    Returns:
        Contenido del script.
    """
    return (RUTA / "static/js" / nombre).read_text(encoding="utf-8")


def test_ambos_formularios_tienen_el_mismo_boton() -> None:
    """Las dos vistas muestran «Pegar Numero» con el mismo atributo."""
    for plantilla in ("index.html", "migracion.html"):
        texto = plantilla_leida(plantilla)
        rotulo = texto.split("data-pegar-numero>", 1)[1].split("</button>", 1)[0]
        assert "Pegar Numero" in rotulo
        assert "Agregar Numero" not in rotulo
        assert "data-rotulo-numero" not in texto
        assert "data-nota-contactos" not in texto


def test_el_boton_abre_whatsapp_sin_libreta_ni_portapapeles() -> None:
    """El clic abre WhatsApp directamente en móvil y web, sin Contact Picker."""
    for script in ("olb_byte.js", "migracion.js"):
        js = javascript_leido(script)
        assert 'window.location.href = "whatsapp://send?text=" + texto' in js
        assert '"https://wa.me/?text="' in js
        assert '"noopener,noreferrer"' in js
        assert "navigator.contacts.select" not in js
        assert "navigator.clipboard" not in js
        assert "data-rotulo-numero" not in js


def test_autowhatsapp_solo_en_registro_de_ventas() -> None:
    """El alta normal usa fetch y salto automático; la migración no."""
    ventas = javascript_leido("olb_byte.js")
    migracion = javascript_leido("migracion.js")

    assert '"X-OLB-AJAX": "1"' in ventas
    assert "data-wa-auto" in plantilla_leida("index.html")
    assert "wa_auto=" in ventas
    assert "data-migracion-form" in plantilla_leida("migracion.html")
    assert "fetch(" not in migracion
    assert "wa_auto" not in plantilla_leida("migracion.html")


def test_las_vistas_renderizan_el_boton(cliente_admin: TestClient) -> None:
    """Ambas rutas sirven el botón sin controles de contactos heredados."""
    for ruta in ("/olb-byte", "/olb-byte/migracion"):
        texto = cliente_admin.get(ruta).text
        assert "data-pegar-numero" in texto
        assert "Pegar Numero" in texto
        assert "data-elegir-contacto" not in texto
        assert data_no_presente(texto)


def data_no_presente(texto: str) -> bool:
    """Comprueba que no queden botones de respaldo del antiguo flujo.

    Args:
        texto: HTML renderizado.

    Returns:
        `True` si no aparecen los controles retirados.
    """
    return all(
        marcador not in texto
        for marcador in ("data-abrir-whatsapp", "data-pegar-portapapeles", "Agregar Numero")
    )
