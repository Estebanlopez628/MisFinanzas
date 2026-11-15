"""Pruebas del flujo de autenticación y del RBAC por rol (Tarea 5).

Cubren login válido e inválido, cookie segura, cierre de sesión, registro
público y bloqueo de los módulos privados para `USER_FINANZAS`.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.dependencias import NOMBRE_COOKIE
from app.servicios import usuarios

CUENTA_ADMIN = {"correo": "admin@olbbyte.co", "contrasena": "Admin123*"}
CUENTA_USUARIO = {"correo": "usuario@finanzas.co", "contrasena": "Usuario123*"}


def test_login_valido_redirige_y_abre_sesion(cliente: TestClient) -> None:
    """Credenciales correctas: 303 al tablero y cookie HttpOnly."""
    respuesta = cliente.post("/login", data=CUENTA_ADMIN, follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/"
    galleta = respuesta.headers["set-cookie"]
    assert NOMBRE_COOKIE in galleta
    assert "HttpOnly" in galleta
    assert "samesite=lax" in galleta.lower()
    assert "max-age" in galleta.lower()


def test_login_invalido_no_revela_si_el_correo_existe(cliente: TestClient) -> None:
    """Contraseña errónea: 401 con un mensaje genérico y sin cookie."""
    respuesta = cliente.post(
        "/login",
        data={"correo": CUENTA_ADMIN["correo"], "contrasena": "incorrecta"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 401
    assert "Correo o contraseña incorrectos." in respuesta.text
    assert NOMBRE_COOKIE not in respuesta.cookies


def test_login_de_correo_inexistente_usa_el_mismo_mensaje(cliente: TestClient) -> None:
    """Un correo que no existe responde igual que una contraseña equivocada."""
    respuesta = cliente.post(
        "/login",
        data={"correo": "nadie@ejemplo.com", "contrasena": "Cualquiera123*"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 401
    assert "Correo o contraseña incorrectos." in respuesta.text


def test_usuario_autenticado_no_ve_el_login(cliente_admin: TestClient) -> None:
    """Con sesión activa, /login redirige al tablero."""
    respuesta = cliente_admin.get("/login", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/"


def test_cerrar_sesion_elimina_la_cookie(cliente_admin: TestClient) -> None:
    """El POST de salida invalida la cookie y vuelve al login."""
    respuesta = cliente_admin.post("/salir", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"
    assert 'max-age=0' in respuesta.headers["set-cookie"].lower()


def test_registro_crea_cuenta_publica(cliente: TestClient, bd) -> None:
    """El auto-registro siempre asigna el rol USER_FINANZAS."""
    correo = f"nuevo-{uuid.uuid4().hex[:8]}@ejemplo.com"
    respuesta = cliente.post(
        "/registro",
        data={
            "correo": correo,
            "alias": "Nueva Persona",
            "contrasena": "ClaveSegura123",
            "confirmar_contrasena": "ClaveSegura123",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login?registrado=1"

    creada = usuarios.buscar_por_correo(bd, correo)
    assert creada is not None
    assert creada.rol == usuarios.ROL_USUARIO


def test_registro_rechaza_contrasenas_distintas(cliente: TestClient) -> None:
    """La confirmación debe coincidir antes de crear la cuenta."""
    respuesta = cliente.post(
        "/registro",
        data={
            "correo": f"otro-{uuid.uuid4().hex[:8]}@ejemplo.com",
            "alias": "Otra Persona",
            "contrasena": "ClaveSegura123",
            "confirmar_contrasena": "ClaveSegura124",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert "Las contraseñas no coinciden." in respuesta.text


def test_registro_rechaza_correo_duplicado(cliente: TestClient) -> None:
    """No se puede registrar dos veces el mismo correo."""
    respuesta = cliente.post(
        "/registro",
        data={
            "correo": CUENTA_USUARIO["correo"],
            "alias": "Duplicada",
            "contrasena": "ClaveSegura123",
            "confirmar_contrasena": "ClaveSegura123",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert "Ya existe una cuenta con ese correo." in respuesta.text


def test_administrador_abre_los_modulos_privados(cliente_admin: TestClient) -> None:
    """ADMIN_OLB conserva OLB_BYTE y Chancucos; el resto es de acceso general."""
    for ruta in ("/olb-byte", "/chancucos", "/deudas", "/trabajos-extras"):
        respuesta = cliente_admin.get(ruta)
        assert respuesta.status_code == 200, ruta


def test_usuario_publico_solo_queda_bloqueado_en_olb_byte_y_chancucos(
    cliente_usuario: TestClient,
) -> None:
    """El RBAC del servidor reserva OLB_BYTE y Chancucos al administrador.

    Deudas y Trabajos Extras pasaron a ser de acceso general en el SRS v1.2.
    """
    for ruta in ("/olb-byte", "/chancucos"):
        respuesta = cliente_usuario.get(ruta)
        assert respuesta.status_code == 403, ruta

    for ruta in ("/deudas", "/trabajos-extras"):
        respuesta = cliente_usuario.get(ruta)
        assert respuesta.status_code == 200, ruta


def test_usuario_publico_puede_usar_finanzas_e_incapacidades(
    cliente_usuario: TestClient,
) -> None:
    """Los dos módulos del rol público responden con normalidad."""
    assert cliente_usuario.get("/finanzas").status_code == 200
    assert cliente_usuario.get("/incapacidades").status_code == 200
