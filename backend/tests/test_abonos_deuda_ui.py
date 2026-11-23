"""Pruebas de las interfaces de abonos y del centrado de cabeceras."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, deducciones_fijas, gastos, usuarios

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


def test_modal_abono_en_base() -> None:
    """La base expone el modal propio con los tres botones exactos."""
    html = (RUTA / "templates/base.html").read_text(encoding="utf-8")
    assert 'id="modal-abono"' in html
    assert "Digita el valor que deseas abonar a tu deuda" in html
    assert "data-abono-solo" in html
    assert "Registrar abono</button>" in html
    assert "data-abono-cuota" in html
    assert "Registrar abono + cuota" in html
    assert "data-abono-cancelar" in html


def test_boton_abono_en_gasto_vinculado(cliente_admin: TestClient, bd) -> None:
    """Solo el gasto con id_deuda ofrece el botón Abonar."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)
    gastos.crear_gasto(
        bd, id_usuario, "Créditos y Obligaciones", "Cuota crédito", "50000", date.today(),
        es_fijo=True, quincena=1, id_deuda=deuda.id_deuda,
    )
    gastos.crear_gasto(
        bd, id_usuario, "Vivienda", "Arriendo", "800000", date.today(), es_fijo=True
    )

    html = cliente_admin.get("/finanzas").text
    assert html.count("data-abrir-abono") >= 1
    assert f'data-id-deuda="{deuda.id_deuda}"' in html


def test_boton_abono_en_deduccion_de_creditos(cliente_admin: TestClient, bd) -> None:
    """Las deducciones vinculadas a crédito también pueden abonar."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)
    deducciones_fijas.crear_deduccion(
        bd, id_usuario, "Libranza", "50000", 1, deuda.id_deuda
    )

    html = cliente_admin.get("/presupuesto").text
    assert f'data-id-deuda="{deuda.id_deuda}"' in html


def test_boton_abono_en_deudas_registradas(cliente_admin: TestClient, bd) -> None:
    """El modal de la deuda registrada también ofrece Abonar."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Alkomprar", "200000", "50000", 4)

    html = cliente_admin.get("/deudas").text
    assert f'data-id-deuda="{deuda.id_deuda}"' in html
    assert "data-abrir-abono" in html


def test_cabeceras_atajos_centradas() -> None:
    """Dos líneas y centrado, sin cambiar anchos ni padding."""
    plantilla = (RUTA / "templates/chancucos/index.html").read_text(encoding="utf-8")
    assert "Valor a<br />Pagar" in plantilla
    assert "Días de<br />Pago" in plantilla

    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert ".tabla--atajos thead th:nth-child(3)" in css
    assert "text-align: center !important" in css
    assert "width: 34% !important" in css
    assert "width: 28% !important" in css
