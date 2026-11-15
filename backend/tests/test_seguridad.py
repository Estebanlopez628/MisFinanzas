"""Pruebas unitarias de la capa de seguridad (Tarea 5).

Cubren el hash de contraseñas PBKDF2 y el ciclo de vida del token de sesión:
emisión, verificación de firma, vencimiento y manipulación.
"""

from __future__ import annotations

import pytest

from app.core.seguridad import (
    TokenInvalido,
    crear_token,
    decodificar_token,
    hash_contrasena,
    verificar_contrasena,
)


def test_hash_no_guarda_la_contrasena_en_claro() -> None:
    """El hash debe ser distinto del texto y tener el formato documentado."""
    almacenado = hash_contrasena("ClaveSegura123")

    assert "ClaveSegura123" not in almacenado
    assert almacenado.startswith("pbkdf2_sha256$")


def test_hash_es_salado() -> None:
    """Dos hashes de la misma contraseña no deben coincidir (sal aleatoria)."""
    assert hash_contrasena("ClaveSegura123") != hash_contrasena("ClaveSegura123")


def test_verificar_contrasena_correcta() -> None:
    """La contraseña original valida contra su hash."""
    almacenado = hash_contrasena("ClaveSegura123")

    assert verificar_contrasena("ClaveSegura123", almacenado) is True


def test_verificar_contrasena_incorrecta() -> None:
    """Una contraseña distinta no valida."""
    almacenado = hash_contrasena("ClaveSegura123")

    assert verificar_contrasena("ClaveSegura124", almacenado) is False


def test_verificar_hash_corrupto_no_lanza_excepcion() -> None:
    """Un hash con formato inválido se rechaza en lugar de romper el login."""
    assert verificar_contrasena("ClaveSegura123", "texto-plano") is False


def test_hash_rechaza_contrasena_corta() -> None:
    """La política mínima se aplica en la capa de seguridad, no solo en la UI."""
    with pytest.raises(ValueError, match="al menos 8"):
        hash_contrasena("corta")


def test_token_ida_y_vuelta() -> None:
    """El contenido del token se recupera íntegro."""
    token = crear_token("usuario-1", "ADMIN_OLB", "Esteban")
    contenido = decodificar_token(token)

    assert contenido["sub"] == "usuario-1"
    assert contenido["rol"] == "ADMIN_OLB"
    assert contenido["alias"] == "Esteban"
    assert contenido["exp"] > contenido["iat"]


def test_token_alterado_se_rechaza() -> None:
    """Cambiar cualquier parte sin re-firmar invalida el token."""
    token = crear_token("usuario-1", "USER_FINANZAS", "Camila")
    cabecera, contenido, firma = token.split(".")
    firma_alterada = ("A" if firma[0] != "A" else "B") + firma[1:]

    with pytest.raises(TokenInvalido, match="firma"):
        decodificar_token(f"{cabecera}.{contenido}.{firma_alterada}")


def test_token_vencido_se_rechaza() -> None:
    """Un token con `exp` en el pasado no autoriza la petición."""
    token = crear_token("usuario-1", "ADMIN_OLB", "Esteban", minutos=1, ahora=1000)

    with pytest.raises(TokenInvalido, match="vencido"):
        decodificar_token(token, ahora=1000 + 61)


def test_token_mal_formado_se_rechaza() -> None:
    """Un texto sin las tres partes del JWT no es un token."""
    with pytest.raises(TokenInvalido, match="no es válido"):
        decodificar_token("solo-una-parte")


def test_token_con_algoritmo_no_soportado_se_rechaza() -> None:
    """La cabecera debe declarar HS256 (evita el ataque `alg: none`)."""
    token = crear_token("usuario-1", "ADMIN_OLB", "Esteban")
    _, contenido, firma = token.split(".")

    with pytest.raises(TokenInvalido, match="no es válido"):
        decodificar_token(f"bm9uZQ.{contenido}.{firma}")
