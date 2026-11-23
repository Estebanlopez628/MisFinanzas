"""Pruebas de la SRS v4.5, bloque 2 (descripción editable en deudas)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, usuarios

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


def _crear(bd, descripcion: str = "Tarjeta inicial"):
    """Crea una deuda de prueba.

    Args:
        bd: Sesión de base de datos.
        descripcion: Texto inicial.

    Returns:
        Deuda creada.
    """
    return deudas.crear_deuda(
        bd, _id_admin(bd), "Banco", "1.200.000", "300.000", 4,
        descripcion=descripcion,
    )


def test_modal_muestra_descripcion_editable(cliente_admin: TestClient, bd) -> None:
    """El modal trae un input visible, pre-cargado y obligatorio."""
    deuda = _crear(bd, "Tarjeta Visa")

    html = cliente_admin.get("/deudas").text
    indice = html.index('value="Tarjeta Visa"')
    fragmento = html[indice - 300 : indice + 200]
    assert 'name="descripcion"' in fragmento
    assert 'type="text"' in fragmento
    assert "required" in fragmento
    assert 'data-actualizar-deuda' in html
    assert "data-alerta-edicion-deuda" in html


def test_form_post_actualiza_la_descripcion(cliente_admin: TestClient, bd) -> None:
    """El formulario histórico sigue guardando el nombre corregido."""
    deuda = _crear(bd, "Nombre viejo")

    respuesta = cliente_admin.post(
        f"/deudas/{deuda.id_deuda}/editar",
        data={
            "acreedor": "Banco",
            "descripcion": "Nombre nuevo",
            "saldo_total": "1.200.000",
            "cuota": "300.000",
            "cuotas_pendientes": "4",
            "periodicidad": "MENSUAL",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    bd.refresh(deuda)
    assert deuda.descripcion == "Nombre nuevo"


def test_api_put_persiste_y_devuelve_la_deuda(cliente_admin: TestClient, bd) -> None:
    """PUT /api/deudas/{id} guarda y retorna el objeto actualizado."""
    deuda = _crear(bd, "Antes")

    respuesta = cliente_admin.put(
        f"/api/deudas/{deuda.id_deuda}",
        data={
            "acreedor": "Banco",
            "descripcion": "Después",
            "saldo_total": "1.200.000",
            "cuota": "300.000",
            "cuotas_pendientes": "4",
            "periodicidad": "MENSUAL",
        },
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["ok"] is True
    assert datos["deuda"]["descripcion"] == "Después"
    bd.refresh(deuda)
    assert deuda.descripcion == "Después"


def test_api_patch_solo_descripcion(cliente_admin: TestClient, bd) -> None:
    """PATCH permite corregir el nombre sin reenviar el plan."""
    deuda = _crear(bd, "Viejo")
    cuota_original = deuda.cuota_mensual

    respuesta = cliente_admin.patch(
        f"/api/deudas/{deuda.id_deuda}", data={"descripcion": "Corregido"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["deuda"]["descripcion"] == "Corregido"
    bd.refresh(deuda)
    assert deuda.cuota_mensual == cuota_original  # el plan queda intacto
    assert deuda.descripcion == "Corregido"


def test_api_rechaza_plan_insuficiente_con_mensaje_limpio(
    cliente_admin: TestClient, bd
) -> None:
    """La validación preventiva se mantiene también en el endpoint."""
    deuda = _crear(bd)

    respuesta = cliente_admin.patch(
        f"/api/deudas/{deuda.id_deuda}",
        data={
            "descripcion": "Cualquiera",
            "saldo_total": "1.000.000",
            "cuota": "10.000",
            "cuotas_pendientes": "2",
        },
    )

    assert respuesta.status_code == 400
    detalle = respuesta.json()["detail"]
    assert "cuotas" in detalle.lower()
    assert "Value error" not in detalle


def test_api_no_actualiza_deuda_ajena(cliente_admin: TestClient, bd) -> None:
    """Un identificador inexistente o ajeno responde 404."""
    respuesta = cliente_admin.patch(
        "/api/deudas/no-existe", data={"descripcion": "Cualquiera"}
    )
    assert respuesta.status_code == 404


def test_js_mantiene_validaciones_y_bloqueo(cliente_admin: TestClient) -> None:
    """El JavaScript conserva el modal propio y el bloqueo síncrono."""
    js = (RUTA_APP / "static/js/deudas.js").read_text(encoding="utf-8")
    assert "data-actualizar-deuda" in js
    assert "Actualizando..." in js
    assert "validarEdicion" in js
    assert "window.pedirConfirmacion" in js
    assert "method: \"DELETE\"" in js
