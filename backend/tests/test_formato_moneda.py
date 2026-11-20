"""Pruebas del formato de pesos en los campos de texto (SRS v1.9).

Los campos de dinero se marcan con `data-moneda` para que el navegador les dé
separadores de miles al escribir o pegar. Porcentajes y cantidades no se marcan.
El valor inicial del sueldo en el perfil se muestra como «3.484.000».
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.servicios import perfiles, usuarios


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def _etiqueta(html: str, nombre: str) -> str:
    """Devuelve la etiqueta `<input>` de un campo por su nombre.

    Args:
        html: HTML de la página.
        nombre: Atributo `name` del campo.

    Returns:
        Texto de la etiqueta, o cadena vacía si no existe.
    """
    for etiqueta in re.findall(r"<input\b[^>]*>", html, flags=re.S):
        if f'name="{nombre}"' in etiqueta:
            return etiqueta
    return ""


def test_el_sueldo_del_perfil_se_muestra_con_separadores(bd, cliente_admin: TestClient) -> None:
    """El sueldo guardado como 3484000 aparece como 3.484.000, sin centavos."""
    perfiles.guardar_perfil(bd, _id_admin(bd), "3484000", "MENSUAL")

    html = cliente_admin.get("/perfil").text

    etiqueta = _etiqueta(html, "sueldo_basico")
    assert 'value="3.484.000"' in etiqueta
    assert "data-moneda" in etiqueta
    assert "3484000,00" not in html


def test_los_campos_de_pesos_llevan_la_marca(cliente_admin: TestClient) -> None:
    """Los campos de dinero del perfil y de las deudas están marcados para formato."""
    perfil = cliente_admin.get("/perfil").text
    deudas = cliente_admin.get("/deudas").text

    assert "data-moneda" in _etiqueta(perfil, "neto_sin_deducciones")
    assert "data-moneda" in _etiqueta(deudas, "saldo_total")
    assert "data-moneda" in _etiqueta(deudas, "cuota")


def test_porcentajes_y_cantidades_no_se_formatean_como_pesos(cliente_admin: TestClient) -> None:
    """Un porcentaje o una cantidad no lleva la marca de pesos."""
    html = cliente_admin.get("/perfil").text
    presupuesto = cliente_admin.get("/presupuesto").text

    assert "data-moneda" not in _etiqueta(html, "porcentaje_quincena_1")
    assert "data-moneda" not in _etiqueta(presupuesto, "cantidad")
    assert "data-moneda" not in _etiqueta(presupuesto, "meses")
