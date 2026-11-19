"""Pruebas del acceso a OLB_BYTE por correo y del inicio de sesión con Google (SRS v1.8).

Cubren la restricción del módulo a los correos autorizados, la tarjeta del panel, el
flujo de Google con `state` y la creación automática de cuentas nuevas.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.seguridad import crear_token
from app.dependencias import NOMBRE_COOKIE
from app.main import crear_aplicacion
from app.servicios import acceso_google, perfiles, usuarios

CORREO_AUTORIZADO = "oscar.esteban.lopez.bedoya@gmail.com"
CORREO_NUEVO = "persona.nueva@gmail.com"


def _cliente_de(bd, correo: str) -> TestClient:
    """Crea un cliente con sesión para una cuenta existente.

    Args:
        bd: Sesión de base de datos.
        correo: Correo de la cuenta.

    Returns:
        Cliente HTTP autenticado.
    """
    cuenta = usuarios.buscar_por_correo(bd, correo)
    assert cuenta is not None
    cliente = TestClient(crear_aplicacion())
    cliente.cookies.set(NOMBRE_COOKIE, crear_token(cuenta.id_usuario, cuenta.rol, cuenta.alias))
    return cliente


def _cuenta_autorizada(bd) -> None:
    """Garantiza una cuenta de Gmail autorizada con perfil configurado.

    Args:
        bd: Sesión de base de datos.
    """
    cuenta = usuarios.buscar_por_correo(bd, CORREO_AUTORIZADO)
    if cuenta is None:
        cuenta = usuarios.crear_usuario(bd, CORREO_AUTORIZADO, "Gmail123*", "Oscar")
    perfiles.guardar_perfil(
        bd, cuenta.id_usuario, "2.960.000", perfiles.MODALIDAD_QUINCENAL, "50", "50", perfiles.QUINCENA_PRIMERA
    )


def test_olb_byte_bloqueado_para_otros_usuarios(cliente_usuario) -> None:
    """Un usuario que no está en la lista recibe 403 en el módulo."""
    assert cliente_usuario.get("/olb-byte").status_code == 403


def test_tarjeta_olb_byte_solo_para_correos_autorizados(cliente_usuario, bd) -> None:
    """La tarjeta no aparece para quien no está autorizado."""
    html = cliente_usuario.get("/").text
    assert 'tarjeta__titulo">OLB_BYTE' not in html


def test_olb_byte_visible_para_correo_autorizado(bd) -> None:
    """Un correo autorizado entra al módulo y ve la tarjeta."""
    _cuenta_autorizada(bd)
    cliente = _cliente_de(bd, CORREO_AUTORIZADO)

    assert cliente.get("/olb-byte").status_code == 200
    assert 'tarjeta__titulo">OLB_BYTE' in cliente.get("/").text


def test_google_inactivo_redirige_al_login(cliente, monkeypatch) -> None:
    """Sin credenciales, el botón de Gmail no inicia nada."""
    monkeypatch.setattr(acceso_google, "google_activo", lambda: False)

    respuesta = cliente.get("/login/google", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"


def test_google_envia_a_la_autorizacion_con_estado(cliente, monkeypatch) -> None:
    """El inicio con Google redirige a Google y guarda una cookie de estado."""
    monkeypatch.setattr(acceso_google, "google_activo", lambda: True)
    monkeypatch.setattr(
        acceso_google, "url_autorizacion", lambda estado: f"https://accounts.google.com/x?state={estado}"
    )

    respuesta = cliente.get("/login/google", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("https://accounts.google.com/")
    assert "estado_google" in respuesta.headers["set-cookie"]


def test_google_crea_la_cuenta_y_abre_sesion(cliente, bd, monkeypatch) -> None:
    """Una cuenta de Gmail verificada entra y queda registrada como usuario."""
    monkeypatch.setattr(
        acceso_google,
        "intercambiar_codigo",
        lambda codigo: {"email": CORREO_NUEVO, "email_verified": True, "given_name": "Ana"},
    )
    cliente.cookies.set("estado_google", "estado-123")

    respuesta = cliente.get(
        "/login/google/callback?code=abc&state=estado-123", follow_redirects=False
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/"
    assert NOMBRE_COOKIE in respuesta.headers["set-cookie"]
    cuenta = usuarios.buscar_por_correo(bd, CORREO_NUEVO)
    assert cuenta is not None
    assert cuenta.rol == usuarios.ROL_USUARIO


def test_google_rechaza_un_estado_que_no_coincide(cliente, monkeypatch) -> None:
    """Si el estado no coincide, no se abre sesión."""
    monkeypatch.setattr(
        acceso_google, "intercambiar_codigo", lambda codigo: {"email": CORREO_NUEVO, "email_verified": True}
    )
    cliente.cookies.set("estado_google", "correcto")

    respuesta = cliente.get("/login/google/callback?code=abc&state=falso", follow_redirects=False)

    assert respuesta.status_code == 401
    assert NOMBRE_COOKIE not in respuesta.headers.get("set-cookie", "")


def test_google_rechaza_un_correo_no_verificado(cliente, monkeypatch) -> None:
    """Si Google no confirma el correo, la pantalla de acceso muestra el error."""

    def no_verificado(codigo: str) -> dict[str, object]:
        raise acceso_google.AccesoGoogleError("Google no confirmó tu correo.")

    monkeypatch.setattr(acceso_google, "intercambiar_codigo", no_verificado)
    cliente.cookies.set("estado_google", "estado-1")

    respuesta = cliente.get("/login/google/callback?code=abc&state=estado-1", follow_redirects=False)

    assert respuesta.status_code == 401
    assert "Google no confirmó tu correo." in respuesta.text
