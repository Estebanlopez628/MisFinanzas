"""Pruebas de la SRS v4.4, bloque 1 (etiqueta, saldo real e íconos)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, gastos, perfiles, quincenas, usuarios

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador del administrador de pruebas.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_etiqueta_sueldo_percibido(cliente_admin: TestClient) -> None:
    """La etiqueta del resultado principal cambia sin tocar la fórmula."""
    html = cliente_admin.get("/finanzas").text
    assert "Sueldo-percibido" in html
    assert "Saldo para el bolsillo" not in html
    assert "data-campo=\"saldo_bolsillo\"" in html


def test_saldo_libre_descuenta_creditos_vinculados(bd) -> None:
    """Los gastos vinculados a deuda sí restan del saldo libre del bloque."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    gastos.crear_gasto(
        bd,
        id_usuario,
        "Créditos y Obligaciones",
        "Cuota banco",
        "100.000",
        date.today(),
        es_fijo=True,
        quincena=1,
        id_deuda=deuda.id_deuda,
    )

    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, date.today().year, date.today().month)
    assert any(fila.gastos >= Decimal("100000.00") for fila in resumen)
    # El gasto vinculado ya no se pinta dos veces: está en `gastos_detalle`.
    assert all(not fila.gastos_vinculados for fila in resumen)


def test_iconos_olb_byte_24_y_28(cliente_admin: TestClient) -> None:
    """Navegación a 24 px y encabezado interno a 28 px."""
    inicio = cliente_admin.get("/").text
    assert 'alt="OLB_BYTE" width="24" height="24"' in inicio

    modulo = cliente_admin.get("/olb-byte").text
    assert 'class="olb-interno__icono"' in modulo
    assert 'alt="OLB_BYTE" width="28" height="28"' in modulo
    assert "🛠" not in modulo

    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".olb-interno__icono {", 1)[1].split("}", 1)[0]
    assert "width: 28px" in bloque and "object-fit: contain" in bloque
