"""Pruebas de la capacidad de endeudamiento y su proyección (SRS v1.7, bloque F).

Cubren el reparto del ingreso entre gastos, deudas y libre, los umbrales del
semáforo, la lista de deudas por terminar, la proyección a doce meses, la suma
de los trabajos extras y las dos vistas que comparten el panel.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.servicios import capacidad, deudas, pagos_metas, perfiles, trabajos, usuarios

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


def _perfil(bd, id_usuario: str):
    """Obtiene el perfil financiero sembrado para la cuenta.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil.

    Returns:
        Perfil financiero.
    """
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    assert perfil is not None
    return perfil


# ---------------------------------------------------------------------------
# Reparto del ingreso y semáforo
# ---------------------------------------------------------------------------


def test_sin_deudas_el_arco_libre_domina_y_el_semaforo_es_verde(bd) -> None:
    """Sin deudas, el ingreso se reparte entre gastos y dinero libre."""
    id_usuario = _id_admin(bd)
    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert resultado.ingreso == Decimal("2960000.00")
    # Solo la deducción de ley del 8 %: no hay gastos ni deudas.
    assert resultado.gastos == Decimal("236800.00")
    assert resultado.deudas == Decimal("0.00")
    assert resultado.semaforo == capacidad.ESTADO_VERDE
    assert resultado.porcentaje_deudas == Decimal("0.00")


def test_los_porcentajes_de_la_dona_suman_cien(bd) -> None:
    """Los tres arcos de la dona siempre cierran la circunferencia."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "2000000", "800000", 3)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    total = sum((arco["porcentaje"] for arco in resultado.arcos), start=Decimal("0"))
    assert total == Decimal("100.0")
    assert [arco["etiqueta"] for arco in resultado.arcos] == [
        "Gastos fijos",
        "Cuota de deudas",
        "Libre",
    ]


def test_una_deuda_alta_pone_el_semaforo_en_rojo(bd) -> None:
    """Una cuota que supera el 35 % del ingreso enciende el semáforo rojo."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "5000000", "2800000", 2)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert resultado.semaforo == capacidad.ESTADO_ROJO
    assert resultado.porcentaje_deudas > capacidad.UMBRAL_AMBAR
    assert resultado.libre < 0


def test_una_deuda_media_pone_el_semaforo_en_ambar(bd) -> None:
    """Entre 20 % y 35 % el semáforo avisa con ámbar."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "2000000", "800000", 3)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert resultado.semaforo == capacidad.ESTADO_AMBAR
    assert capacidad.UMBRAL_VERDE < resultado.porcentaje_deudas <= capacidad.UMBRAL_AMBAR


def test_sin_perfil_no_hay_datos_para_la_dona(bd) -> None:
    """Sin perfil financiero el panel queda en estado sin datos."""
    id_usuario = _id_admin(bd)
    resultado = capacidad.capacidad_endeudamiento(bd, id_usuario, None, HOY.year, HOY.month)

    assert resultado.semaforo == capacidad.ESTADO_SIN_DATOS
    assert resultado.arcos == []
    assert resultado.proyeccion  # La proyección se entrega en ceros.


# ---------------------------------------------------------------------------
# Deudas por terminar
# ---------------------------------------------------------------------------


def test_solo_lista_deudas_con_tres_cuotas_o_menos(bd) -> None:
    """La lista de cierre excluye las deudas largas."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Corta", "200000", "100000", 2)
    deudas.crear_deuda(bd, id_usuario, "Larga", "600000", "100000", 6)

    filas = capacidad.deudas_por_terminar(bd, id_usuario)

    assert [fila["acreedor"] for fila in filas] == ["Corta"]
    assert filas[0]["cuotas_pendientes"] == 2
    assert filas[0]["fecha_fin"] is not None


def test_la_ultima_cuota_da_la_fecha_de_cierre(bd) -> None:
    """La fecha estimada es la de la última cuota de la amortización."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Corta", "200000", "100000", 2)

    filas = capacidad.deudas_por_terminar(bd, id_usuario)
    proyectadas = deudas.proyeccion_deuda(deuda)

    assert filas[0]["fecha_fin"] == proyectadas[-1].fecha


# ---------------------------------------------------------------------------
# Proyección a doce meses
# ---------------------------------------------------------------------------


def test_la_proyeccion_tiene_doce_meses(bd) -> None:
    """Siempre se entregan doce filas, con o sin deudas."""
    id_usuario = _id_admin(bd)
    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert len(resultado.proyeccion) == capacidad.MESES_PROYECCION


def test_la_cuota_baja_cuando_la_deuda_termina(bd) -> None:
    """Una deuda de dos cuotas deja de pesar en el tercer mes proyectado."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Corta", "200000", "100000", 2)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )
    proyeccion = resultado.proyeccion

    assert proyeccion[0]["deuda"] == Decimal("100000.00")
    assert proyeccion[1]["deuda"] == Decimal("100000.00")
    assert proyeccion[2]["deuda"] == Decimal("0.00")
    assert proyeccion[2]["libre"] > proyeccion[0]["libre"]
    assert proyeccion[1]["terminan"] == ["Corta"]


def test_una_deuda_quincenal_pesa_dos_cuotas_por_mes(bd) -> None:
    """La cuota quincenal se duplica para compararla con el ingreso mensual."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(
        bd,
        id_usuario,
        "Gota a gota",
        "300000",
        "100000",
        3,
        periodicidad=deudas.PERIODICIDAD_QUINCENAL,
    )

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert resultado.deudas == Decimal("200000.00")
    # Tres cuotas quincenales ocupan dos meses.
    assert resultado.proyeccion[1]["deuda"] == Decimal("200000.00")
    assert resultado.proyeccion[2]["deuda"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# Trabajos extras y vistas
# ---------------------------------------------------------------------------


def test_el_extra_cobrado_suma_al_ingreso(bd) -> None:
    """El neto de un trabajo extra cobrado entra en la capacidad del mes."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Asesoría",
        "500000",
        HOY,
        "ACME",
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        frecuencia=trabajos.FRECUENCIA_MENSUAL,
        fecha_fin=HOY,
        fecha_pago=HOY,
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, HOY.year, HOY.month)
    pago = next(iter(trabajos.pagos_del_mes(bd, id_usuario, HOY.year, HOY.month)))["periodos"][0]["pago"]
    pagos_metas.marcar_pagado(bd, id_usuario, pago.id_gasto, HOY)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert trabajo.id_trabajo
    assert resultado.ingreso == Decimal("3460000.00")


def test_presupuesto_muestra_el_panel_de_capacidad(cliente_admin) -> None:
    """«Gastos y Presupuesto» incluye la dona, sin la tabla de 12 meses."""
    respuesta = cliente_admin.get("/presupuesto")

    assert respuesta.status_code == 200
    assert "Capacidad de endeudamiento" in respuesta.text
    assert "Proyección a 12 meses" not in respuesta.text
    assert "Deudas por terminar" in respuesta.text


def test_trabajos_extras_muestra_su_propia_instancia(cliente_admin) -> None:
    """«Trabajos Extras» reutiliza el panel con su propio título."""
    respuesta = cliente_admin.get("/trabajos-extras")

    assert respuesta.status_code == 200
    assert "Capacidad con tus ingresos extras" in respuesta.text
    assert "Proyección a 12 meses" not in respuesta.text
