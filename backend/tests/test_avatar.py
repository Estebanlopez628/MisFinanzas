"""Avatar híbrido: foto de Google o iniciales, sin archivos en el servidor (SRS v1.8)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.seguridad import crear_token
from app.dependencias import NOMBRE_COOKIE
from app.main import crear_aplicacion
from app.routers.vistas import iniciales_alias
from app.servicios import acceso_google, usuarios

RAIZ_BACKEND = Path(__file__).resolve().parent.parent
FOTO_GOOGLE = "https://lh3.googleusercontent.com/a/ACg8ocK-ejemplo_foto=s96-c"
CLAVE = "Clave-Segura-2026"


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


def _cuenta(bd, correo: str, alias: str, avatar: str | None = None):
    """Garantiza una cuenta de prueba con el avatar indicado.

    Args:
        bd: Sesión de base de datos.
        correo: Correo de la cuenta.
        alias: Apodo de la cuenta.
        avatar: Foto de Google o `None`.

    Returns:
        La cuenta persistida.
    """
    cuenta = usuarios.buscar_por_correo(bd, correo)
    if cuenta is None:
        cuenta = usuarios.crear_usuario(bd, correo, CLAVE, alias)
    cuenta.avatar_url = avatar
    bd.commit()
    return cuenta


def test_iniciales_con_dos_palabras_y_con_una() -> None:
    """Dos palabras dan sus iniciales; una sola palabra, sus dos primeras letras."""
    assert iniciales_alias("Oscar Lopez") == "OL"
    assert iniciales_alias("ana maría") == "AM"
    assert iniciales_alias("ana") == "AN"
    assert iniciales_alias("  ") == ""


def test_solo_se_aceptan_fotos_https_de_google() -> None:
    """Cualquier otra URL, incluida una HTTP o de otro dominio, se descarta."""
    assert usuarios.url_avatar_valida(FOTO_GOOGLE)
    assert not usuarios.url_avatar_valida("http://lh3.googleusercontent.com/a/x")
    assert not usuarios.url_avatar_valida("https://evil.example.com/foto.png")
    assert not usuarios.url_avatar_valida(None)
    assert not usuarios.url_avatar_valida("https://lh3.googleusercontent.com/" + "a" * 600)


def test_registro_local_no_tiene_avatar(bd) -> None:
    """Una cuenta creada con correo y contraseña conserva el avatar vacío."""
    cuenta = usuarios.crear_usuario(bd, "local.avatar@correo.co", CLAVE, "Local Uno")

    assert cuenta.avatar_url is None


def test_google_guarda_la_foto_y_la_actualiza(cliente, bd, monkeypatch) -> None:
    """El callback de Google guarda `picture` y lo refresca en cada inicio de sesión."""
    correo = "foto.google@correo.co"
    monkeypatch.setattr(
        acceso_google,
        "intercambiar_codigo",
        lambda codigo: {"email": correo, "given_name": "Foto", "picture": FOTO_GOOGLE},
    )
    cliente.cookies.set("estado_google", "estado-foto")

    respuesta = cliente.get(
        "/login/google/callback", params={"code": "c", "state": "estado-foto"}, follow_redirects=False
    )

    assert respuesta.status_code == 303
    assert usuarios.buscar_por_correo(bd, correo).avatar_url == FOTO_GOOGLE


def test_google_sin_foto_valida_quita_el_avatar(cliente, bd, monkeypatch) -> None:
    """Si Google ya no envía una foto válida, la cuenta vuelve a las iniciales."""
    correo = "sin.foto@correo.co"
    _cuenta(bd, correo, "Sin Foto", avatar=FOTO_GOOGLE)
    monkeypatch.setattr(
        acceso_google,
        "intercambiar_codigo",
        lambda codigo: {"email": correo, "given_name": "Sin", "picture": "https://otro.example.com/x.png"},
    )
    cliente.cookies.set("estado_google", "estado-sin")

    cliente.get("/login/google/callback", params={"code": "c", "state": "estado-sin"}, follow_redirects=False)

    assert usuarios.buscar_por_correo(bd, correo).avatar_url is None


def test_con_foto_se_muestra_la_imagen_con_respaldo(bd) -> None:
    """La cabecera carga la foto con `referrerpolicy` y vuelve a las iniciales si falla."""
    cuenta = _cuenta(bd, "con.foto@correo.co", "Lucia Mora", avatar=FOTO_GOOGLE)

    html = _cliente_de(bd, cuenta.correo).get("/").text

    assert f'src="{FOTO_GOOGLE}"' in html
    assert 'referrerpolicy="no-referrer"' in html
    assert "this.nextElementSibling.hidden=false" in html
    assert 'class="avatar__iniciales" hidden>LM<' in html


def test_sin_foto_se_muestran_las_iniciales(bd) -> None:
    """Sin foto aparece el círculo con las dos iniciales del alias y ninguna imagen."""
    cuenta = _cuenta(bd, "sin.imagen@correo.co", "Pedro Rojas")

    html = _cliente_de(bd, cuenta.correo).get("/perfil").text

    assert 'class="avatar__iniciales">PR<' in html
    assert "avatar__imagen" not in html
    assert "avatar--destacado" in html


def test_csp_permite_las_fotos_de_google() -> None:
    """La política de imágenes admite Google además de 'self' y data:."""
    respuesta = TestClient(crear_aplicacion()).get("/login")

    politica = respuesta.headers["content-security-policy"]
    assert "img-src 'self' data: https://*.googleusercontent.com" in politica


def test_migracion_columna_avatar_es_idempotente(tmp_path: Path) -> None:
    """Sobre una base con el esquema anterior, la migración agrega la columna dos veces sin error."""
    ruta = tmp_path / "anterior.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute(
        "CREATE TABLE usuarios (id_usuario VARCHAR(32) PRIMARY KEY, correo VARCHAR(150) UNIQUE, "
        "hash_contrasena VARCHAR(255), alias VARCHAR(60), rol VARCHAR(20), activo BOOLEAN, "
        "fecha_registro DATETIME, ultimo_acceso DATETIME)"
    )
    conexion.execute(
        "INSERT INTO usuarios VALUES ('u1', 'previo@correo.co', 'x', 'Previo', 'USER_FINANZAS', 1, "
        "'2026-01-01 00:00:00', NULL)"
    )
    conexion.commit()
    conexion.close()

    script = "from app.core.base_datos import inicializar_base_datos; inicializar_base_datos(); print('ok')"
    entorno = os.environ.copy()
    entorno["DATABASE_URL"] = f"sqlite:///{ruta.as_posix()}"
    entorno["ENTORNO"] = "pruebas"
    entorno["CLAVE_SECRETA"] = "clave-secreta-solo-para-pruebas-0123456789"

    for _ in range(2):
        resultado = subprocess.run(
            [sys.executable, "-c", script],
            cwd=RAIZ_BACKEND,
            env=entorno,
            capture_output=True,
            text=True,
            check=False,
        )
        assert resultado.returncode == 0, resultado.stderr

    conexion = sqlite3.connect(ruta)
    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(usuarios)")}
    previo = conexion.execute("SELECT alias, avatar_url FROM usuarios WHERE id_usuario='u1'").fetchone()
    conexion.close()

    assert "avatar_url" in columnas
    assert previo == ("Previo", None)
