"""Pruebas del cálculo en vivo de horas extras e incapacidades (SRS v1.4).

Cubren que el sueldo proyectado y las quincenas se recalculen con las novedades
del formulario, y que el descuento por incapacidad siga la norma: días 1 y 2 sin
descuento (empleador) y desde el día 3 descuento del 33,33 % (EPS).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.texto import formatear_cop
from app.servicios import usuarios
from app.servicios.incapacidad import liquidar_mes_incapacidad


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


def _calcular(cliente: TestClient, **campos) -> dict:
    """Envía el formulario de liquidación en JSON, como lo hace la interfaz.

    Args:
        cliente: Cliente HTTP autenticado.
        **campos: Campos adicionales del formulario.

    Returns:
        Cuerpo JSON de la respuesta.
    """
    cuerpo = {
        "anio": 2026,
        "mes": 11,
        "quincena": 0,
        "sueldo_basico": "3.000.000",
        "incapacidad_inicio": "",
        "incapacidad_fin": "",
    }
    cuerpo.update(campos)
    return cliente.post("/finanzas/calcular", json=cuerpo).json()


def test_incapacidad_de_dos_dias_no_descuenta_nada(cliente_admin: TestClient) -> None:
    """Días 1 y 2 los paga el empleador: el descuento es cero."""
    cuerpo = _calcular(
        cliente_admin, incapacidad_inicio="2026-11-01", incapacidad_fin="2026-11-02"
    )

    assert cuerpo["ok"] is True
    assert cuerpo["incapacidad"]["dias_al_100"] == 2
    assert cuerpo["incapacidad"]["dias_al_66"] == 0
    assert cuerpo["datos"]["deduccion_incapacidad"] == "$0"


def test_descuento_desde_el_tercer_dia_sigue_la_norma(
    cliente_admin: TestClient,
) -> None:
    """Cinco días: dos al 100 % y tres con descuento del 33,33 %, como el motor legal."""
    cuerpo = _calcular(
        cliente_admin, incapacidad_inicio="2026-11-01", incapacidad_fin="2026-11-05"
    )

    # La incapacidad se liquida sobre el sueldo mensual del perfil (2.960.000).
    esperado = liquidar_mes_incapacidad(
        date(2026, 11, 1), date(2026, 11, 5), Decimal("2960000"), anio=2026, mes=11
    )
    assert cuerpo["incapacidad"]["dias_al_100"] == 2
    assert cuerpo["incapacidad"]["dias_al_66"] == 3
    assert cuerpo["incapacidad"]["descuento"] == formatear_cop(esperado.valor_descontado)


def test_incapacidad_reduce_sueldo_proyectado_y_quincenas(
    cliente_admin: TestClient,
) -> None:
    """El sueldo proyectado y el ingreso de las quincenas bajan en vivo."""
    sin_novedad = _calcular(cliente_admin)
    con_incapacidad = _calcular(
        cliente_admin, incapacidad_inicio="2026-11-01", incapacidad_fin="2026-11-05"
    )

    assert con_incapacidad["datos"]["sueldo_proyectado"] != sin_novedad["datos"]["sueldo_proyectado"]
    assert sin_novedad["datos"]["sueldo_proyectado"] == "$3.000.000"

    ingresos_sin = {f["numero"]: f["ingreso"] for f in sin_novedad["quincenas"]}
    ingresos_con = {f["numero"]: f["ingreso"] for f in con_incapacidad["quincenas"]}
    assert ingresos_con != ingresos_sin


def test_horas_extras_suben_el_sueldo_proyectado(cliente_admin: TestClient) -> None:
    """Las horas extras entran al sueldo proyectado en el mismo cálculo."""
    base = _calcular(cliente_admin)
    con_extras = _calcular(cliente_admin, horas_EXTRA_DIURNA_NORMAL="10")

    assert base["datos"]["sueldo_proyectado"] == "$3.000.000"
    assert con_extras["datos"]["sueldo_proyectado"] != base["datos"]["sueldo_proyectado"]


def test_horas_extras_suben_salud_y_pension_en_vivo(cliente_admin: TestClient) -> None:
    """Salud y pensión se calculan sobre el devengado: las extras las elevan."""
    base = _calcular(cliente_admin)
    con_extras = _calcular(cliente_admin, horas_EXTRA_NOCTURNA="10")

    # 4 % de 3.000.000 = 120.000; con 250.000 de recargo, 4 % de 3.250.000 = 130.000.
    assert base["datos"]["deduccion_salud"] == "$120.000"
    assert con_extras["datos"]["deduccion_salud"] == "$130.000"
    assert con_extras["datos"]["deduccion_pension"] == "$130.000"


def test_incapacidad_baja_salud_y_pension_en_vivo(cliente_admin: TestClient) -> None:
    """La merma por incapacidad reduce la base de salud y pensión."""
    cuerpo = _calcular(
        cliente_admin, incapacidad_inicio="2026-11-01", incapacidad_fin="2026-11-05"
    )
    descuento = liquidar_mes_incapacidad(
        date(2026, 11, 1), date(2026, 11, 5), Decimal("2960000"), anio=2026, mes=11
    ).valor_descontado
    base = Decimal("3000000") - descuento
    esperado = formatear_cop((base * Decimal("0.04")).quantize(Decimal("0.01")))

    assert cuerpo["datos"]["deduccion_salud"] == esperado


def test_rango_de_incapacidad_invalido_se_rechaza(cliente_admin: TestClient) -> None:
    """Una fecha de fin anterior al inicio devuelve error, no un descuento."""
    cuerpo = _calcular(
        cliente_admin, incapacidad_inicio="2026-11-10", incapacidad_fin="2026-11-01"
    )

    assert cuerpo["ok"] is False
    assert cuerpo["errores"]


def test_valor_oculto_queda_listo_para_guardar(cliente_admin: TestClient) -> None:
    """El descuento que devuelve el cálculo es el que «Guardar periodo» debe usar."""
    cuerpo = _calcular(
        cliente_admin, incapacidad_inicio="2026-11-01", incapacidad_fin="2026-11-05"
    )

    esperado = liquidar_mes_incapacidad(
        date(2026, 11, 1), date(2026, 11, 5), Decimal("2960000"), anio=2026, mes=11
    ).valor_descontado
    assert cuerpo["rollover"] == str(esperado)
