"""Recuperación de contraseña por correo electrónico (SRS v1.8, bloque 8)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.core.seguridad import (
    TokenInvalido,
    crear_token,
    crear_token_recuperacion,
    decodificar_token,
    decodificar_token_recuperacion,
)
from app.main import crear_aplicacion
from app.routers import auth as auth_router
from app.servicios import auditoria, usuarios

CORREO = "recupera@correo.co"
CLAVE = "Clave-Original1"
NUEVA = "Clave-Nueva-2026"
MENSAJE_NEUTRO = "Si el correo está registrado, te enviamos un enlace"


@pytest.fixture()
def correos(monkeypatch) -> list[dict[str, str]]:
    """Captura los correos enviados en lugar de salir por SMTP.

    Args:
        monkeypatch: Herramienta de pytest para reemplazar el envío.

    Returns:
        Lista donde se guardan destinatario, asunto y cuerpo de cada correo.
    """
    enviados: list[dict[str, str]] = []

    def capturar(destino: str, asunto: str, cuerpo: str) -> bool:
        enviados.append({"destino": destino, "asunto": asunto, "cuerpo": cuerpo})
        return True

    monkeypatch.setattr(auth_router.servicio_correo, "enviar_correo", capturar)
    return enviados


@pytest.fixture()
def cuenta(bd):
    """Garantiza una cuenta con contraseña conocida.

    Args:
        bd: Sesión de base de datos.

    Returns:
        La cuenta de prueba.
    """
    existente = usuarios.buscar_por_correo(bd, CORREO)
    if existente is None:
        existente = usuarios.crear_usuario(bd, CORREO, CLAVE, "Rita")
    usuarios.restablecer_contrasena(bd, existente.id_usuario, CLAVE)
    return usuarios.buscar_por_correo(bd, CORREO)


def _token_del_correo(correos: list[dict[str, str]]) -> str:
    """Extrae el token del enlace del último correo enviado.

    Args:
        correos: Correos capturados.

    Returns:
        Token del enlace.
    """
    cuerpo = correos[-1]["cuerpo"]
    coincidencia = re.search(r"restablecer-contrasena\?token=([^\s]+)", cuerpo)
    assert coincidencia, cuerpo
    return coincidencia.group(1)


def test_el_enlace_es_de_recuperacion_y_no_sirve_como_sesion(cuenta) -> None:
    """Un token de recuperación no abre sesión y un token de sesión no recupera."""
    recuperacion = crear_token_recuperacion(cuenta.id_usuario, cuenta.rol, cuenta.alias, "huella")
    sesion = crear_token(cuenta.id_usuario, cuenta.rol, cuenta.alias)

    assert decodificar_token_recuperacion(recuperacion)["sub"] == cuenta.id_usuario
    with pytest.raises(TokenInvalido):
        decodificar_token(recuperacion)
    with pytest.raises(TokenInvalido):
        decodificar_token_recuperacion(sesion)


def test_el_enlace_vence_a_los_quince_minutos(cuenta) -> None:
    """Pasados quince minutos el enlace ya no sirve."""
    emitido = 1_800_000_000
    token = crear_token_recuperacion(cuenta.id_usuario, cuenta.rol, cuenta.alias, "h", ahora=emitido)

    assert decodificar_token_recuperacion(token, ahora=emitido + 14 * 60)["sub"] == cuenta.id_usuario
    with pytest.raises(TokenInvalido):
        decodificar_token_recuperacion(token, ahora=emitido + 16 * 60)


def test_respuesta_neutra_con_correo_registrado(cliente, cuenta, correos) -> None:
    """Un correo registrado recibe el enlace y la respuesta es la misma de siempre."""
    respuesta = cliente.post("/olvide-contrasena", data={"correo": CORREO})

    assert respuesta.status_code == 200
    assert MENSAJE_NEUTRO in respuesta.text
    assert correos and correos[-1]["destino"] == CORREO
    assert "restablecer-contrasena?token=" in correos[-1]["cuerpo"]


def test_respuesta_neutra_con_correo_desconocido(cliente, correos) -> None:
    """Un correo sin cuenta responde igual y no envía nada."""
    antes = len(correos)

    respuesta = cliente.post("/olvide-contrasena", data={"correo": "nadie@correo.co"})

    assert respuesta.status_code == 200
    assert MENSAJE_NEUTRO in respuesta.text
    assert len(correos) == antes


def test_flujo_completo_cambia_la_contrasena_y_el_enlace_no_se_reutiliza(
    cliente, bd, cuenta, correos
) -> None:
    """El enlace permite cambiar la contraseña una sola vez."""
    cliente.post("/olvide-contrasena", data={"correo": CORREO})
    token = _token_del_correo(correos)

    formulario = cliente.get("/restablecer-contrasena", params={"token": token})
    assert formulario.status_code == 200
    assert 'name="contrasena"' in formulario.text

    cambio = cliente.post(
        "/restablecer-contrasena",
        data={"token": token, "contrasena": NUEVA, "confirmacion": NUEVA},
        follow_redirects=False,
    )
    assert cambio.status_code == 303
    assert cambio.headers["location"] == "/login?restablecida=1"
    bd.expire_all()
    assert usuarios.autenticar(bd, CORREO, NUEVA) is not None
    assert usuarios.autenticar(bd, CORREO, CLAVE) is None

    reutilizado = cliente.post(
        "/restablecer-contrasena",
        data={"token": token, "contrasena": "Otra-Clave-123", "confirmacion": "Otra-Clave-123"},
    )
    assert reutilizado.status_code == 400


def test_contrasena_corta_o_distinta_no_se_guarda(cliente, bd, cuenta, correos) -> None:
    """La nueva contraseña debe tener 8 caracteres y coincidir con la confirmación."""
    cliente.post("/olvide-contrasena", data={"correo": CORREO})
    token = _token_del_correo(correos)

    corta = cliente.post(
        "/restablecer-contrasena", data={"token": token, "contrasena": "abc", "confirmacion": "abc"}
    )
    distinta = cliente.post(
        "/restablecer-contrasena",
        data={"token": token, "contrasena": NUEVA, "confirmacion": "otra-cosa-123"},
    )

    assert corta.status_code == 400
    assert distinta.status_code == 400
    assert "no coinciden" in distinta.text
    assert usuarios.autenticar(bd, CORREO, CLAVE) is not None


def test_enlace_invalido_muestra_aviso(cliente) -> None:
    """Un token falso no muestra el formulario."""
    respuesta = cliente.get("/restablecer-contrasena", params={"token": "no-es-un-token"})

    assert respuesta.status_code == 400
    assert "no es válido" in respuesta.text
    assert 'name="contrasena"' not in respuesta.text


def test_la_solicitud_queda_auditada(cliente, bd, cuenta, correos) -> None:
    """Cada solicitud de recuperación deja un evento en la auditoría."""
    cliente.post("/olvide-contrasena", data={"correo": CORREO})
    cliente.post("/olvide-contrasena", data={"correo": "ausente@correo.co"})

    acciones = [evento.accion for evento in auditoria.listar_eventos(bd, limite=50)]

    assert "RECUPERACION_SOLICITADA" in acciones


def test_login_muestra_el_aviso_tras_restablecer(cliente) -> None:
    """Tras cambiar la contraseña el login confirma el cambio."""
    respuesta = cliente.get("/login", params={"restablecida": 1})

    assert "Tu contraseña se actualizó" in respuesta.text


def test_sin_smtp_en_desarrollo_no_falla(monkeypatch) -> None:
    """Sin SMTP configurado, en desarrollo el envío se registra y no rompe el flujo."""
    from types import SimpleNamespace

    from app.servicios import correo

    monkeypatch.setattr(correo, "obtener_configuracion", lambda: SimpleNamespace(smtp_host="", es_produccion=False))
    assert correo.enviar_correo("x@correo.co", "Asunto", "Cuerpo") is True
