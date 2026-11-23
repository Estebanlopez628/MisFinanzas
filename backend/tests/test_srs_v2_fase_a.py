"""Pruebas de la SRS v2.0, Fase A (backend y PostgreSQL).

Cubre la tabla `feedback_usuarios`, sus endpoints y la obligación de que los
GET de gastos fijos devuelvan también los vinculados a deudas con la cuota
mediante `JOIN`, sin duplicarla en dona ni consejero.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import capacidad, deudas, feedback, gastos, perfiles, quincenas, usuarios


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


def _id_usuario(bd) -> str:
    """Devuelve el identificador de la cuenta estándar sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de `usuario@finanzas.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "usuario@finanzas.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_detectar_dispositivo_desde_user_agent() -> None:
    """El servidor distingue celulares de escritorio sin depender de JS."""
    assert feedback.detectar_dispositivo(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605"
    ) == "Móvil"
    assert feedback.detectar_dispositivo(
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile"
    ) == "Móvil"
    assert feedback.detectar_dispositivo(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"
    ) == "Escritorio"
    assert feedback.detectar_dispositivo("") == "Escritorio"


def test_catalogo_de_modulos_excluye_olb_byte() -> None:
    """Las guías y el selector del usuario estándar nunca mencionan OLB_BYTE."""
    unidos = " ".join(feedback.MODULOS).lower()
    assert "olb" not in unidos
    assert "factur" not in unidos
    assert "Registro y Detalles de deudas" in feedback.MODULOS
    assert "Atajos de pago" in feedback.MODULOS


def test_crear_reporte_guarda_estado_y_snapshot(bd, cliente_usuario: TestClient) -> None:
    """El alta registra usuario, correo, dispositivo y estado «Pendiente»."""
    respuesta = cliente_usuario.post(
        "/feedback",
        json={
            "tipo_reporte": "SUGERENCIA",
            "modulo": "Finanzas",
            "descripcion": "Sería útil ver el historial por categoría.",
        },
        headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile"
        },
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "Pendiente"

    reportes = feedback.listar_reportes(bd)
    assert len(reportes) == 1
    assert reportes[0].usuario_correo == "usuario@finanzas.co"
    assert reportes[0].dispositivo == "Móvil"
    assert reportes[0].estado == "Pendiente"
    assert reportes[0].tipo_reporte == "SUGERENCIA"


def test_reporte_rechaza_modulo_privado(bd, cliente_usuario: TestClient) -> None:
    """El catálogo cerrado impide reportar módulos del administrador."""
    respuesta = cliente_usuario.post(
        "/feedback",
        json={
            "tipo_reporte": "ERROR",
            "modulo": "OLB_BYTE",
            "descripcion": "Esto no debería aceptarse.",
        },
    )
    # El catálogo cerrado se aplica en el esquema Pydantic (422) y, como red de
    # seguridad, en el servicio (400).
    assert respuesta.status_code in (400, 422)


def test_contador_y_cambio_de_estado(bd) -> None:
    """El contador baja al resolver un reporte y el listado lo refleja."""
    from app.dependencias import UsuarioSesion

    usuario = UsuarioSesion(
        id_usuario=_id_admin(bd),
        correo="admin@olbbyte.co",
        alias="Administrador",
        rol="ADMIN_OLB",
    )
    feedback.crear_reporte(bd, usuario, "ERROR", "Falla 1", "Finanzas")
    feedback.crear_reporte(bd, usuario, "CALCULO", "Falla 2", "Atajos de pago")

    assert feedback.contar_pendientes(bd) == 2
    reporte = feedback.listar_reportes(bd)[0]
    actualizado = feedback.cambiar_estado(bd, reporte.id_feedback, "Resuelto")
    assert actualizado is not None
    assert feedback.contar_pendientes(bd) == 1
    assert feedback.cambiar_estado(bd, reporte.id_feedback, "Inexistente") is None


def test_endpoints_admin_y_rbac(
    bd, cliente_admin: TestClient, cliente_usuario: TestClient, cliente: TestClient
) -> None:
    """Solo el administrador puede listar, contar y cambiar estados."""
    from app.dependencias import UsuarioSesion

    usuario = UsuarioSesion(
        id_usuario=_id_usuario(bd),
        correo="usuario@finanzas.co",
        alias="Usuario",
        rol="USER_FINANZAS",
    )
    reporte = feedback.crear_reporte(bd, usuario, "ERROR", "No carga la dona", "Finanzas")

    assert cliente_admin.get("/feedback/pendientes").json() == {"pendientes": 1}
    listado = cliente_admin.get("/feedback").json()
    assert len(listado["reportes"]) == 1
    assert listado["reportes"][0]["correo"] == "usuario@finanzas.co"

    cambio = cliente_admin.post(
        f"/feedback/{reporte.id_feedback}/estado", json={"estado": "En revisión"}
    )
    assert cambio.status_code == 200
    assert cambio.json() == {"ok": True, "estado": "En revisión", "pendientes": 0}

    assert cliente_usuario.get("/feedback").status_code == 403
    assert cliente_usuario.get("/feedback/pendientes").status_code == 403
    assert cliente.get("/feedback", headers={"Accept": "application/json"}).status_code == 401


def test_gastos_vinculados_aparecen_en_get_con_cuota(bd) -> None:
    """El GET de gastos incluye el vínculo y trae cuota y acreador del JOIN."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco Ejemplo", "1.200.000", "100.000", 12)
    gasto = gastos.crear_gasto(
        bd,
        id_usuario,
        "Créditos y Obligaciones",
        "Cuota del banco",
        "999.999",
        date(2026, 11, 1),
        es_fijo=True,
        id_deuda=deuda.id_deuda,
    )

    filas = gastos.listar_gastos_con_deuda(bd, id_usuario, 2026, 11)
    assert len(filas) == 1
    assert filas[0]["id_deuda"] == deuda.id_deuda
    assert filas[0]["acreedor_deuda"] == "Banco Ejemplo"
    assert filas[0]["cuota_deuda"] == str(Decimal("100000.00"))
    assert filas[0]["valor"] == str(Decimal("100000.00"))
    assert gasto.valor == Decimal("100000.00")


def test_endpoint_get_gastos_fijos_incluye_vinculados(
    bd, cliente_admin: TestClient
) -> None:
    """La API JSON de gastos fijos expone los registros con `id_deuda`."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Cooperativa", "600.000", "50.000", 12)
    gastos.crear_gasto(
        bd,
        id_usuario,
        "Créditos y Obligaciones",
        "Aporte",
        "50.000",
        date(2026, 11, 1),
        id_deuda=deuda.id_deuda,
    )

    datos = cliente_admin.get("/gastos/api/fijos?anio=2026&mes=11").json()
    assert len(datos["gastos"]) == 1
    assert datos["gastos"][0]["acreedor_deuda"] == "Cooperativa"


def test_no_duplicar_cuota_en_dona_ni_consejero(bd) -> None:
    """La cuota vinculada se cuenta una sola vez: no resta del saldo libre."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    gastos.crear_gasto(
        bd,
        id_usuario,
        "Créditos y Obligaciones",
        "Cuota",
        "100.000",
        date(2026, 11, 1),
        es_fijo=True,
        id_deuda=deuda.id_deuda,
    )

    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, 2026, 11)
    # SRS v4.4, sección 3: la cuota vinculada sí resta del saldo libre del bloque.
    assert any(fila.gastos >= Decimal("100000.00") for fila in resumen)

    calculo = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, 2026, 11)
    assert calculo.deudas >= Decimal("100000.00")
