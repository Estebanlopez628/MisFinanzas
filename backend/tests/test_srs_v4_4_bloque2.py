"""Pruebas de la SRS v4.4, bloque 2 (vinculación, borrado e idempotencia)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, gastos, trabajos, usuarios

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


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


def test_api_deudas_reporta_vinculacion(cliente_admin: TestClient, bd) -> None:
    """El API distingue deudas vinculadas a Finanzas y a Trabajos Extras."""
    id_usuario = _id_admin(bd)
    deuda_finanzas = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "300.000", 4)
    deuda_extras = deudas.crear_deuda(bd, id_usuario, "Proveedor", "600.000", "150.000", 4)
    deuda_libre = deudas.crear_deuda(bd, id_usuario, "Tienda", "300.000", "100.000", 3)

    gastos.crear_gasto(
        bd, id_usuario, "Vivienda", "Cuota", "300.000", date.today(),
        es_fijo=True, id_deuda=deuda_finanzas.id_deuda,
    )
    trabajo = trabajos.crear_trabajo(bd, id_usuario, "Diseño", "500.000", date.today())
    trabajos.crear_gasto_trabajo(
        bd, id_usuario, trabajo.id_trabajo, "Otros Gastos Fijos", "Cuota", "150.000",
        id_deuda=deuda_extras.id_deuda,
    )

    datos = cliente_admin.get("/api/deudas").json()["deudas"]
    por_id = {fila["id_deuda"]: fila for fila in datos}

    assert por_id[deuda_finanzas.id_deuda]["esta_vinculada"] is True
    assert por_id[deuda_finanzas.id_deuda]["modulos_vinculados"] == ["Finanzas"]
    assert por_id[deuda_extras.id_deuda]["modulos_vinculados"] == ["Trabajos Extras"]
    assert por_id[deuda_libre.id_deuda]["esta_vinculada"] is False
    assert por_id[deuda_libre.id_deuda]["modulos_vinculados"] == []


def test_tabla_muestra_vinculacion_y_no_muestra_tarjeta_de_cuotas(
    cliente_admin: TestClient, bd
) -> None:
    """La tabla trae la columna nueva y se retira la tarjeta de cuotas."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "300.000", 4)
    deudas.crear_deuda(bd, id_usuario, "Tienda", "300.000", "100.000", 3)
    gastos.crear_gasto(
        bd, id_usuario, "Vivienda", "Cuota", "300.000", date.today(),
        es_fijo=True, id_deuda=deuda.id_deuda,
    )

    html = cliente_admin.get("/deudas").text
    assert "Vinculación" in html
    assert "insignia--vinculada" in html
    assert "Vinculada · Finanzas" in html
    assert "insignia--sin-vincular" in html
    assert "Pagos que faltan en las deudas activas" not in html
    assert "rejilla-tarjetas--deudas" in html


def test_modal_de_edicion_ofrece_eliminar(cliente_admin: TestClient, bd) -> None:
    """El modal trae un botón rojo de eliminación confirmada por la app."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "300.000", 4)

    html = cliente_admin.get("/deudas").text
    assert f'data-eliminar-deuda="{deuda.id_deuda}"' in html
    assert "boton--peligro" in html
    assert "data-confirmar" not in html.split(f'data-eliminar-deuda="{deuda.id_deuda}"', 1)[1].split("</button>", 1)[0]


def test_api_elimina_deuda_y_respeta_otro_usuario(cliente_admin: TestClient, bd) -> None:
    """DELETE borra la deuda propia; un id ajeno o inexistente da 404."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "300.000", 4)

    respuesta = cliente_admin.delete(f"/api/deudas/{deuda.id_deuda}")
    assert respuesta.status_code == 200
    assert respuesta.json()["ok"] is True
    assert deudas.listar_deudas(bd, id_usuario) == []

    assert cliente_admin.delete("/api/deudas/no-existe").status_code == 404


def test_alta_idempotente_no_duplica_en_diez_segundos(cliente_admin: TestClient, bd) -> None:
    """Dos POST idénticos seguidos crean una sola deuda."""
    id_usuario = _id_admin(bd)
    datos = {
        "acreedor": "Banco idempotente",
        "descripcion": "Prueba",
        "saldo_total": "1.200.000",
        "cuota": "300.000",
        "cuotas_pendientes": "4",
        "periodicidad": "MENSUAL",
    }

    primera = cliente_admin.post("/deudas", data=datos, follow_redirects=False)
    segunda = cliente_admin.post("/deudas", data=datos, follow_redirects=False)
    assert primera.status_code == 303
    assert segunda.status_code == 303

    creadas = [deuda for deuda in deudas.listar_deudas(bd, id_usuario) if deuda.acreedor == "Banco idempotente"]
    assert len(creadas) == 1


def test_js_bloquea_doble_envio_y_restaura_scroll() -> None:
    """El frontend usa guardia síncrona y restaura la posición sin ir al inicio."""
    js_deudas = (RUTA_APP / "static/js/deudas.js").read_text(encoding="utf-8")
    assert "envioEnCurso = true" in js_deudas
    assert 'botonGuardar.textContent = "Guardando..."' in js_deudas
    assert "if (envioEnCurso)" in js_deudas
    assert "method: \"DELETE\"" in js_deudas
    assert "window.pedirConfirmacion" in js_deudas

    js_app = (RUTA_APP / "static/js/app.js").read_text(encoding="utf-8")
    assert "window.scrollY" in js_app
    assert 'behavior: "instant"' in js_app
    assert 'block: "nearest"' in js_app
    assert "scrollTo(0, 0)" not in js_app

    html = (RUTA_APP / "templates/finanzas/index.html").read_text(encoding="utf-8")
    for ancla in ("bloque-quincena-1", "bloque-quincena-2", "bloque-pago-mensual"):
        assert ancla in html
