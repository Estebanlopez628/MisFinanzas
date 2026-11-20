"""Pruebas de coherencia entre el diagnóstico del mes y la dona de capacidad (SRS v1.9).

El disponible del diagnóstico y el «Total libre» de la dona salen del mismo
ingreso. Ambos deben descontar la cuota mensual de las deudas; si uno lo omite,
el usuario ve dos cifras distintas para el mismo dinero.
"""

from __future__ import annotations

from datetime import date

from app.servicios import ahorro, capacidad, deudas, perfiles, usuarios


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


def test_disponible_del_diagnostico_coincide_con_el_total_libre(bd) -> None:
    """Con deudas activas, el diagnóstico y la dona muestran el mismo libre."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "2400000", "800000", 3)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    hoy = date.today()

    diagnostico = ahorro.diagnostico(bd, id_usuario, perfil, hoy.year, hoy.month)
    dona = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, hoy.year, hoy.month)

    assert diagnostico["cuota_deudas"] > 0
    assert diagnostico["cuota_deudas"] == dona.deudas
    assert diagnostico["disponible"] == dona.libre
