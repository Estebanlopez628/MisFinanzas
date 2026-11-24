"""Pruebas del consejero financiero (SRS v1.8).

Cubren la activación por encima de la base mínima de liquidez, la elección de la
deuda que libera más cuotas, la comparación base frente a optimizado, el modo
ahorro con y sin metas y las dos situaciones de la vista de presupuesto.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.servicios import (
    ahorro,
    consejero,
    deducciones_fijas,
    deudas,
    usuarios,
)

HOY = date.today()


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


# ---------------------------------------------------------------------------
# Activación
# ---------------------------------------------------------------------------


def test_el_consejero_no_se_activa_sin_excedente_suficiente(bd) -> None:
    """Con 300.000 exactos el consejero queda apagado: el umbral es estricto."""
    id_usuario = _id_admin(bd)
    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("300000"))

    assert resultado.activo is False
    assert resultado.serie == []


def test_el_consejero_se_activa_por_encima_del_umbral(bd) -> None:
    """Superar el umbral activa el consejo con saludo y pasos."""
    id_usuario = _id_admin(bd)
    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("900000"))

    assert resultado.activo is True
    assert "Ana" in resultado.titulo
    assert resultado.pasos
    assert len(resultado.serie) == consejero.MESES


# ---------------------------------------------------------------------------
# Deudas: liberación de flujo de caja
# ---------------------------------------------------------------------------


def test_el_excedente_ataca_la_deuda_que_libera_mas_cuotas(bd) -> None:
    """Con un excedente que cancela varias, gana la de más cuotas por delante."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Grande", "1200000", "100000", 12)
    deudas.crear_deuda(bd, id_usuario, "Pequeña", "500000", "100000", 5)

    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("1800000"))

    assert resultado.modo == consejero.MODO_DEUDA
    assert resultado.estrategia == consejero.ESTRATEGIA_FLUJO
    assert resultado.deuda_objetivo == "Grande"
    assert resultado.excedente == Decimal("1500000.00")
    assert resultado.meses_optimizado < resultado.meses_base
    assert resultado.cuota_liberada == Decimal("200000.00")


def test_sin_excedente_para_cancelar_empieza_por_el_saldo_menor(bd) -> None:
    """Si no alcanza para cerrar ninguna, el orden empieza por la más pequeña."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Grande", "1200000", "100000", 12)
    deudas.crear_deuda(bd, id_usuario, "Pequeña", "500000", "100000", 5)
    estados = consejero._estados(deudas.listar_deudas(bd, id_usuario))

    orden = consejero._ordenar(estados, Decimal("400000"))

    assert orden[0].deuda.acreedor == "Pequeña"
    assert orden[-1].deuda.acreedor == "Grande"


def test_el_excedente_liquida_la_deuda_dentro_del_año(bd) -> None:
    """Una deuda corta con excedente grande se cierra y se informa el mes."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Corta", "200000", "100000", 2)

    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("500000"))

    assert resultado.meses_liquidacion == 1
    assert resultado.serie[0]["optimizado"] == Decimal("0.00")


def test_la_serie_de_deuda_baja_con_el_excedente(bd) -> None:
    """En modo deuda, el saldo optimizado nunca supera al base."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "3000000", "250000", 12)

    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("400000"))

    for fila in resultado.serie:
        assert fila["optimizado"] <= fila["base"]
        assert Decimal("0") <= fila["base_pct"] <= Decimal("100")
        assert Decimal("0") <= fila["optimizado_pct"] <= Decimal("100")


# ---------------------------------------------------------------------------
# Sin deudas: metas de ahorro
# ---------------------------------------------------------------------------


def test_sin_deudas_ni_metas_sugiere_crear_una(bd) -> None:
    """Sin pasivos ni metas, el consejo invita a crear una meta."""
    id_usuario = _id_admin(bd)
    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("800000"))

    assert resultado.modo == consejero.MODO_AHORRO
    assert resultado.estrategia == consejero.ESTRATEGIA_SIN_METAS
    assert "meta" in resultado.mensaje.lower()


def test_con_metas_el_consejo_apunta_a_la_primera(bd) -> None:
    """Con una meta activa, el mensaje la nombra y calcula su duración."""
    id_usuario = _id_admin(bd)
    ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Viaje a la costa",
        "500000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses=6,
    )

    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("600000"))

    assert resultado.estrategia == consejero.ESTRATEGIA_METAS
    assert "Viaje a la costa" in resultado.mensaje


def test_la_serie_de_ahorro_sube_con_el_excedente(bd) -> None:
    """En modo ahorro, el escenario optimizado acumula más que el base."""
    id_usuario = _id_admin(bd)
    ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Fondo de emergencia",
        "200000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses=12,
    )

    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("500000"))

    assert resultado.ahorro_optimizado > resultado.ahorro_base
    for fila in resultado.serie:
        assert fila["optimizado"] >= fila["base"]


# ---------------------------------------------------------------------------
# Vista de presupuesto
# ---------------------------------------------------------------------------


def test_presupuesto_muestra_el_consejero_cuando_hay_excedente(cliente_admin) -> None:
    """Con el perfil sembrado y sin gastos, el excedente supera el umbral."""
    respuesta = cliente_admin.get("/presupuesto")

    assert respuesta.status_code == 200
    assert "Consejero financiero" in respuesta.text
    assert "impacto-deudas" in respuesta.text
    assert "Base frente a optimizado" not in respuesta.text


def test_presupuesto_avisa_sin_excedente_suficiente(bd, cliente_admin) -> None:
    """Una deducción fija alta deja el libre en la base mínima y apaga el consejo."""
    id_usuario = _id_admin(bd)
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Cuota interna", "2800000", 1)

    respuesta = cliente_admin.get("/presupuesto")

    assert respuesta.status_code == 200
    assert "Base mínima de liquidez" in respuesta.text
    assert "No puedo ofrecerte un consejo financiero" in respuesta.text
    assert "Base frente a optimizado" not in respuesta.text
