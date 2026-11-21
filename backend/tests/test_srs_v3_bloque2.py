"""Pruebas de la SRS v3.0, bloque 2 (recuperación y soporte)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.dependencias import UsuarioSesion
from app.servicios import feedback, usuarios

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


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


def test_recuperacion_solo_en_login_y_botones_separados(cliente, cliente_usuario) -> None:
    """El enlace de olvido no está en Mi Perfil y los botones tienen gap."""
    assert "Recuperar contraseña" not in cliente_usuario.get("/perfil").text
    login = cliente.get("/login").text
    assert "¿Olvidaste tu contraseña?" in login

    html = cliente.get("/olvide-contrasena").text
    assert 'class="olvide-acciones"' in html
    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    assert ".acceso-nuevo__formulario + .olvide-acciones" in css


def test_envio_en_segundo_plano_con_timeout_controlado() -> None:
    """El endpoint usa tareas de fondo y el SMTP tiene timeout de 10 s."""
    auth = (RUTA_APP / "routers/auth.py").read_text(encoding="utf-8")
    correo = (RUTA_APP / "servicios/correo.py").read_text(encoding="utf-8")

    assert "BackgroundTasks" in auth
    assert "tareas: BackgroundTasks" in auth
    assert "tareas.add_task(servicio_correo.enviar_recuperacion" in auth
    assert "configuracion_valida()" in auth
    assert "TIEMPO_ESPERA_SEGUNDOS = 10" in correo
    assert "Correo de recuperación enviado correctamente" in correo
    assert "No se pudo enviar el correo de recuperación" in correo


def test_alias_de_configuracion_smtp() -> None:
    """Se aceptan SMTP_PASSWORD y FROM_EMAIL como alias."""
    config = (RUTA_APP / "core/config.py").read_text(encoding="utf-8")
    assert 'os.getenv("SMTP_PASSWORD", "")' in config
    assert 'os.getenv("FROM_EMAIL", "")' in config


def test_patch_de_estado_guarda_fecha_de_resolucion(bd, cliente_admin: TestClient) -> None:
    """El PATCH actualiza el estado y la fecha; volver a Pendiente la limpia."""
    usuario = UsuarioSesion(
        id_usuario=_id_usuario(bd),
        correo="usuario@finanzas.co",
        alias="Usuario",
        rol="USER_FINANZAS",
    )
    reporte = feedback.crear_reporte(bd, usuario, "ERROR", "Fallo en dona", "Finanzas")

    respuesta = cliente_admin.patch(
        f"/api/feedback/{reporte.id_feedback}", json={"estado": "Resuelto"}
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["estado"] == "Resuelto"
    assert datos["fecha_resolucion"] is not None
    assert datos["pendientes"] == 0

    vuelta = cliente_admin.patch(
        f"/api/feedback/{reporte.id_feedback}", json={"estado": "Pendiente"}
    )
    assert vuelta.json()["fecha_resolucion"] is None
    assert vuelta.json()["pendientes"] == 1


def test_endpoint_de_reportes_propios(bd, cliente_usuario: TestClient) -> None:
    """El usuario ve solo sus reportes, con su estado actual."""
    propio = UsuarioSesion(
        id_usuario=_id_usuario(bd),
        correo="usuario@finanzas.co",
        alias="Usuario",
        rol="USER_FINANZAS",
    )
    ajeno = UsuarioSesion(
        id_usuario=_id_admin(bd),
        correo="admin@olbbyte.co",
        alias="Admin",
        rol="ADMIN_OLB",
    )
    feedback.crear_reporte(bd, propio, "SUGERENCIA", "Reporte propio", "Finanzas")
    feedback.crear_reporte(bd, ajeno, "ERROR", "Reporte ajeno", "Finanzas")

    datos = cliente_usuario.get("/api/feedback/mios").json()
    assert len(datos["reportes"]) == 1
    assert datos["reportes"][0]["descripcion"] == "Reporte propio"
    assert datos["reportes"][0]["estado"] == "Pendiente"


def test_vista_movil_de_comentarios_y_historial(
    bd, cliente_admin: TestClient, cliente_usuario: TestClient
) -> None:
    """La tabla tiene su equivalente en tarjetas y el usuario ve su historial."""
    reportante = UsuarioSesion(
        id_usuario=_id_usuario(bd),
        correo="usuario@finanzas.co",
        alias="Usuario",
        rol="USER_FINANZAS",
    )
    feedback.crear_reporte(bd, reportante, "ERROR", "Fallo móvil", "Finanzas")

    html = cliente_admin.get("/admin/comentarios").text
    assert "reportes-moviles" in html
    assert "reporte-movil" in html
    assert "data-estado-reporte" in html

    js = (RUTA_APP / "static/js/comentarios.js").read_text(encoding="utf-8")
    assert 'fetch("/api/feedback/"' in js
    assert 'method: "PATCH"' in js

    ayuda = cliente_usuario.get("/ayuda").text
    assert "Mis reportes enviados" in ayuda
    assert "data-mis-reportes" in ayuda
    ayuda_js = (RUTA_APP / "static/js/ayuda.js").read_text(encoding="utf-8")
    assert 'fetch("/api/feedback/mios"' in ayuda_js
