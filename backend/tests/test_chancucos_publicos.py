"""Atajos de pago (Chancucos) disponibles para todos los usuarios autenticados (SRS v1.8).

Cada usuario ve y administra solo sus propios atajos.
"""

from __future__ import annotations

from app.servicios import chancucos, usuarios


def _id_usuario(bd, correo: str) -> str:
    """Devuelve el identificador de una cuenta sembrada.

    Args:
        bd: Sesión de base de datos.
        correo: Correo de la cuenta.

    Returns:
        Identificador de la cuenta.
    """
    cuenta = usuarios.buscar_por_correo(bd, correo)
    assert cuenta is not None
    return cuenta.id_usuario


def test_usuario_comun_ve_el_enlace_de_atajos(cliente_usuario) -> None:
    """El submenú de Mis Finanzas muestra Configurar Atajos de Pago a todos."""
    html = cliente_usuario.get("/finanzas").text

    assert "Configurar Atajos de Pago" in html


def test_usuario_comun_entra_y_crea_su_atajo(cliente_usuario, bd) -> None:
    """Un usuario común puede abrir la pantalla y registrar un atajo propio."""
    assert cliente_usuario.get("/chancucos").status_code == 200

    respuesta = cliente_usuario.post(
        "/chancucos",
        data={"descripcion": "Internet Hogar", "numero_referencia": "REF-123"},
        follow_redirects=False,
    )

    assert respuesta.status_code in (200, 303)
    propios = chancucos.listar_chancucos(bd, _id_usuario(bd, "usuario@finanzas.co"))
    assert any(item.descripcion == "Internet Hogar" for item in propios)


def test_cada_usuario_solo_ve_sus_atajos(cliente_usuario, bd) -> None:
    """Los atajos de un usuario no aparecen en la lista de otro."""
    id_comun = _id_usuario(bd, "usuario@finanzas.co")
    id_admin = _id_usuario(bd, "admin@olbbyte.co")
    chancucos.crear_chancuco(bd, id_comun, "Gas del usuario", "GAS-1")

    ajenos = chancucos.listar_chancucos(bd, id_admin)

    assert all(item.descripcion != "Gas del usuario" for item in ajenos)
