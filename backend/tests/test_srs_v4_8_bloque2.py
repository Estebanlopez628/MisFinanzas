"""Pruebas de la SRS v4.8, bloque 2 (quincenas reales y etiquetas limpias)."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import perfiles, quincenas, usuarios

SUELDO = "3.484.000"
AUXILIO = Decimal("249095")


def _id_admin(bd) -> str:
    """Devuelve el identificador del administrador sembrado.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador del administrador de pruebas.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def _perfil_40_60(bd):
    """Configura el perfil del caso base (40 % Q1, 60 % Q2, deducciones en Q2).

    Args:
        bd: Sesión de base de datos.

    Returns:
        Perfil financiero configurado.
    """
    id_usuario = _id_admin(bd)
    perfiles.guardar_perfil(
        bd,
        id_usuario,
        SUELDO,
        perfiles.MODALIDAD_QUINCENAL,
        porcentaje_quincena_1="40",
        porcentaje_quincena_2="60",
        quincena_deducciones=2,
        dia_quincena_1=15,
        dia_quincena_2=30,
    )
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    assert perfil is not None
    return perfil


def test_quincena_2_incluye_auxilio_y_neto_real(bd) -> None:
    """El caso base rinde 1.393.600 en Q1 y 2.060.775 netos en Q2."""
    id_usuario = _id_admin(bd)
    perfil = _perfil_40_60(bd)

    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, 2026, 11)
    primera, segunda = resumen

    assert primera.ingreso == Decimal("1393600.00")
    assert primera.deducciones == Decimal("0.00")
    assert segunda.ingreso == Decimal("2090400.00") + AUXILIO
    assert segunda.deducciones == Decimal("278720.00")
    assert segunda.saldo_libre == Decimal("2060775.00")
    assert sum((fila.devengado_neto for fila in resumen), Decimal("0")) == Decimal(
        "3454375.00"
    )


def test_recargos_se_suman_al_total_devengado_del_corte(bd) -> None:
    """Los recargos de los siete conceptos engrosan el mismo corte y el consolidado."""
    id_usuario = _id_admin(bd)
    perfil = _perfil_40_60(bd)

    # 17.000 de recargos mantiene el devengado (3.501.000) bajo el tope de
    # 2 SMMLV, así que el auxilio sigue aplicando.
    resumen = quincenas.resumen_quincenas(
        bd, id_usuario, perfil, 2026, 11, recargos=Decimal("17000")
    )
    primera, segunda = resumen

    assert primera.ingreso == Decimal("1393600.00")
    assert segunda.ingreso == Decimal("2356495.00")
    assert segunda.deducciones == Decimal("280080.00")
    assert primera.devengado_neto + segunda.devengado_neto == Decimal("3470015.00")


def test_etiquetas_limpias_en_la_interfaz(cliente_admin: TestClient) -> None:
    """«Sueldo devengado» y «Total devengado» sustituyen a las etiquetas con guion."""
    html = cliente_admin.get("/finanzas").text

    assert "Sueldo devengado" in html
    assert "Total devengado" in html
    assert "Ingreso proyectado" not in html
    assert "Sueldo-percibido" not in html
    assert "data-campo=\"total_devengado_consolidado\"" in html


def test_json_expone_el_total_devengado_consolidado(cliente_usuario: TestClient) -> None:
    """El recálculo en vivo mantiene el mismo criterio que la vista."""
    respuesta = cliente_usuario.post(
        "/finanzas/calcular",
        json={"sueldo_basico": SUELDO, "deduccion_incapacidad": "0"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert "total_devengado_consolidado" in cuerpo["datos"]
    assert cuerpo["datos"]["total_devengado_consolidado"].startswith("$")
    # El auxilio sigue publicándose en su propio bloque.
    assert cuerpo["datos"]["auxilio_transporte"] == "$249.095"


def test_pago_mensual_tambien_recibe_el_auxilio(bd) -> None:
    """En modalidad mensual el auxilio entra en el único corte."""
    id_usuario = _id_admin(bd)
    perfiles.guardar_perfil(bd, id_usuario, SUELDO, perfiles.MODALIDAD_MENSUAL)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    assert perfil is not None

    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, 2026, 11)

    assert len(resumen) == 1
    assert resumen[0].ingreso == Decimal("3733095.00")
    assert resumen[0].devengado_neto == Decimal("3454375.00")
