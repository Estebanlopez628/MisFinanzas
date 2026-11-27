"""Pruebas del Documento Único Integrado, secciones 5 y 6.

Responsabilidad
---------------
- Verificar que la base mínima de liquidez la elige cada usuario en el
  onboarding, que las cuentas previas conservan $300.000 y que la dona, el
  diagnóstico y el Consejero leen ese mismo valor.
- Verificar que la recuperación guarda solo el SHA-256 del token, vence a los
  20 minutos, invalida enlaces anteriores y permite cambiar la contraseña una
  sola vez, tanto por JSON como por la vista `/reset-password`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select, text

from app.core import base_datos as modulo_bd
from app.core.base_datos import FabricaSesiones
from app.core.config import ConfiguracionApp
from app.servicios import ahorro, capacidad, consejero, perfiles, tokens_recuperacion
from app.servicios import correo as servicio_correo
from app.modelos import PerfilFinanciero, TokenRecuperacion

CORREO = "usuario@finanzas.co"


def _id_usuario() -> str:
    """Devuelve el identificador de la cuenta pública de pruebas.

    Returns:
        ID de la cuenta `usuario@finanzas.co`.
    """
    from app.servicios import usuarios

    with FabricaSesiones() as sesion:
        cuenta = usuarios.buscar_por_correo(sesion, CORREO)
        assert cuenta is not None
        return cuenta.id_usuario


def test_columna_liquidez_tipo_y_valor_previo(bd) -> None:
    """La columna existe como NUMERIC(12,2) y los perfiles previos valen 300000."""
    with FabricaSesiones() as conexion:
        filas = conexion.execute(text("PRAGMA table_info(perfiles_financieros)")).fetchall()
    columna = next((fila for fila in filas if fila[1] == "monto_minimo_liquidez"), None)
    assert columna is not None
    assert "NUMERIC" in columna[2].upper()
    assert "12" in columna[2]
    perfil = perfiles.obtener_perfil(bd, _id_usuario())
    assert perfil is not None
    assert perfil.monto_minimo_liquidez == Decimal("300000.00")


def test_migracion_base_antigua_recibe_300000(tmp_path, monkeypatch) -> None:
    """Una base sin la columna recibe 300000 en las filas ya existentes."""
    archivo = tmp_path / "perfil_antiguo.db"
    conexion = sqlite3.connect(archivo)
    conexion.execute(
        "CREATE TABLE perfiles_financieros ("
        "id_perfil TEXT PRIMARY KEY, id_usuario TEXT, sueldo_basico NUMERIC, "
        "modalidad_pago TEXT)"
    )
    conexion.execute(
        "INSERT INTO perfiles_financieros VALUES ('p-antiguo', 'u-antiguo', 2960000, 'MENSUAL')"
    )
    conexion.commit()
    conexion.close()

    motor = create_engine(f"sqlite:///{archivo.as_posix()}")
    monkeypatch.setattr(modulo_bd, "motor", motor)
    monkeypatch.setattr(modulo_bd, "_conexion_sqlite", True)
    modulo_bd._migrar_monto_minimo_liquidez()

    with motor.connect() as enlace:
        columnas = enlace.execute(text("PRAGMA table_info(perfiles_financieros)")).fetchall()
        assert any(fila[1] == "monto_minimo_liquidez" for fila in columnas)
        valor = enlace.execute(
            text("SELECT monto_minimo_liquidez FROM perfiles_financieros")
        ).scalar()
    assert Decimal(str(valor)) == Decimal("300000")
    motor.dispose()


def test_onboarding_guarda_monto_digitado(cliente_usuario, bd, monkeypatch) -> None:
    """El primer inicio de sesión persiste el colchón escrito por el usuario."""
    id_usuario = _id_usuario()
    with FabricaSesiones() as sesion:
        sesion.query(PerfilFinanciero).filter(
            PerfilFinanciero.id_usuario == id_usuario
        ).delete()
        sesion.commit()

    html = cliente_usuario.get("/perfil?bienvenida=1").text
    assert "Monto mínimo que deseas mantener libre para imprevistos" in html
    assert 'name="monto_minimo_liquidez"' in html
    assert 'type="number"' in html
    assert "Digita el valor:" in html

    respuesta = cliente_usuario.post(
        "/perfil",
        data={
            "alias": "Usuario",
            "sueldo_basico": "3.000.000",
            "modalidad_pago": perfiles.MODALIDAD_MENSUAL,
            "monto_minimo_liquidez": "450000",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    assert perfil is not None
    assert perfil.monto_minimo_liquidez == Decimal("450000.00")


def test_liquidez_configurada_alimenta_calculos(bd) -> None:
    """El monto guardado sustituye a la constante en dona, alerta y Consejero."""
    perfil = perfiles.obtener_perfil(bd, _id_usuario())
    assert perfil is not None
    perfil.monto_minimo_liquidez = Decimal("450000")
    bd.commit()
    bd.refresh(perfil)

    assert capacidad.base_minima_de(perfil) == Decimal("450000.00")
    base, disponible = capacidad.repartir_libre(
        Decimal("500000"), capacidad.base_minima_de(perfil)
    )
    assert base == Decimal("450000.00")
    assert disponible == Decimal("50000.00")

    diagnostico = ahorro.diagnostico(bd, perfil.id_usuario, perfil, 2026, 11)
    assert diagnostico["umbral"] == Decimal("450000.00")

    consejo = consejero.consejo_financiero(
        bd, perfil.id_usuario, "Usuario", Decimal("500000"), umbral=diagnostico["umbral"]
    )
    assert consejo.umbral == Decimal("450000.00")
    assert consejo.excedente == Decimal("50000.00")


def test_token_guarda_solo_hash_invalida_previos_y_expira(bd) -> None:
    """Se persiste el SHA-256, se invalidan los anteriores y vence a 20 minutos."""
    primero = tokens_recuperacion.solicitar_token(bd, CORREO)
    assert primero is not None
    crudo, correo, id_usuario = primero
    assert correo == CORREO

    registros = list(bd.scalars(select(TokenRecuperacion)))
    assert len(registros) == 1
    assert registros[0].token_hash == tokens_recuperacion.hash_token(crudo)
    assert crudo not in registros[0].token_hash
    assert not registros[0].used
    ahora_naive = tokens_recuperacion.agora_utc().replace(tzinfo=None)
    assert timedelta(minutes=19) < registros[0].expires_at - ahora_naive < timedelta(minutes=21)

    segundo = tokens_recuperacion.solicitar_token(bd, CORREO)
    assert segundo is not None
    nuevo, _correo, _id = segundo
    assert tokens_recuperacion.buscar_valido(bd, crudo) is None
    assert tokens_recuperacion.buscar_valido(bd, nuevo) is not None

    # Un token vencido, aunque no esté usado, deja de ser válido.
    vigente = tokens_recuperacion.buscar_valido(bd, nuevo)
    assert vigente is not None
    vigente.expires_at = tokens_recuperacion.agora_utc() - timedelta(seconds=1)
    bd.commit()
    assert tokens_recuperacion.buscar_valido(bd, nuevo) is None
    assert id_usuario == _id_usuario()


def test_recuperacion_unica_con_login_nuevo(cliente, bd) -> None:
    """Tras cambiar la clave, el enlace queda inutilizado y se entra con ella."""
    solicitado = tokens_recuperacion.solicitar_token(bd, CORREO)
    assert solicitado is not None
    token = solicitado[0]
    id_usuario, _correo = tokens_recuperacion.restablecer(bd, token, "ClaveNueva123*")
    assert id_usuario == _id_usuario()
    assert tokens_recuperacion.buscar_valido(bd, token) is None

    respuesta = cliente.post(
        "/login", data={"correo": CORREO, "contrasena": "ClaveNueva123*"}, follow_redirects=False
    )
    assert respuesta.status_code == 303


def test_endpoint_forgot_password_neutro_con_resend(cliente, monkeypatch) -> None:
    """El endpoint responde igual para todos y envía el enlace con FRONTEND_URL."""
    enviados: list[tuple[str, str]] = []

    def falso_envio(destino: str, enlace: str) -> bool:
        enviados.append((destino, enlace))
        return True

    monkeypatch.setattr(
        "app.routers.auth.servicio_correo.enviar_recuperacion_token", falso_envio
    )
    monkeypatch.setattr(
        "app.routers.auth.obtener_configuracion",
        lambda: SimpleNamespace(frontend_url="https://finanzas.example", app_url=""),
    )

    mensaje = "Si el correo existe en el sistema, te hemos enviado un enlace de recuperación."
    respuesta = cliente.post("/auth/forgot-password", json={"email": CORREO})
    assert respuesta.status_code == 200
    assert respuesta.json()["message"] == mensaje
    assert len(enviados) == 1
    assert enviados[0][0] == CORREO
    assert enviados[0][1].startswith("https://finanzas.example/reset-password?token=")

    otra = cliente.post("/auth/forgot-password", json={"email": "noexiste@correo.test"})
    assert otra.status_code == 200
    assert otra.json()["message"] == mensaje
    assert len(enviados) == 1


def test_endpoint_reset_password_json_unico(cliente, bd) -> None:
    """El JSON cambia la clave y rechaza un segundo uso del enlace."""
    solicitado = tokens_recuperacion.solicitar_token(bd, CORREO)
    assert solicitado is not None
    token = solicitado[0]

    respuesta = cliente.post(
        "/auth/reset-password", json={"token": token, "new_password": "JsonClave123*"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["message"].startswith("Contraseña actualizada correctamente")

    repetido = cliente.post(
        "/auth/reset-password", json={"token": token, "new_password": "OtraClave123*"}
    )
    assert repetido.status_code == 400

    entrada = cliente.post(
        "/login", data={"correo": CORREO, "contrasena": "JsonClave123*"}, follow_redirects=False
    )
    assert entrada.status_code == 303


def test_vista_reset_password_valida_e_invalida(cliente, bd) -> None:
    """La vista solo abre con un token vigente y aplica la contraseña confirmada."""
    solicitado = tokens_recuperacion.solicitar_token(bd, CORREO)
    assert solicitado is not None
    token = solicitado[0]

    assert cliente.get(f"/reset-password?token={token}").status_code == 200
    invalida = cliente.get("/reset-password?token=token-invalido-largo")
    assert invalida.status_code == 400
    assert "ya se usó o ha expirado" in invalida.text

    desigual = cliente.post(
        "/reset-password",
        data={"token": token, "contrasena": "VistaClave123*", "confirmacion": "OtraClave123*"},
    )
    assert desigual.status_code == 400

    correcta = cliente.post(
        "/reset-password",
        data={"token": token, "contrasena": "VistaClave123*", "confirmacion": "VistaClave123*"},
        follow_redirects=False,
    )
    assert correcta.status_code == 303
    assert "/login?restablecida=1" in correcta.headers["location"]


def test_configuracion_resend_y_remitente(monkeypatch) -> None:
    """RESEND_FROM y FRONTEND_URL se leen del entorno y se usan en Resend."""
    monkeypatch.setenv("RESEND_API_KEY", "re_clave_de_prueba")
    monkeypatch.setenv("RESEND_FROM", "onboarding@resend.dev")
    monkeypatch.setenv("FRONTEND_URL", "https://finanzas.example")
    configuracion = ConfiguracionApp()
    assert configuracion.resend_from == "onboarding@resend.dev"
    assert configuracion.frontend_url == "https://finanzas.example"

    captura: dict[str, object] = {}

    class RespuestaFalsa:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def urlopen_falso(peticion, timeout):
        captura["cuerpo"] = json.loads(peticion.data.decode("utf-8"))
        captura["autorizacion"] = peticion.headers.get("Authorization")
        return RespuestaFalsa()

    monkeypatch.setattr(servicio_correo.urllib.request, "urlopen", urlopen_falso)
    config_api = SimpleNamespace(
        resend_api_key="re_clave_de_prueba",
        resend_from="onboarding@resend.dev",
        brevo_api_key="",
        sendgrid_api_key="",
        smtp_from="histórico@correo.test",
    )
    assert servicio_correo._enviar_por_api(
        config_api, "usuario@correo.test", "Recupera tu contraseña", "texto", html="<p>hola</p>"
    )
    cuerpo = captura["cuerpo"]
    assert cuerpo["from"] == "onboarding@resend.dev"
    assert cuerpo["html"] == "<p>hola</p>"
    assert captura["autorizacion"] == "Bearer re_clave_de_prueba"
