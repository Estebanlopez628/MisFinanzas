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


def _con_colchon(bd, id_usuario: str, monto: str = "300000"):
    """Fija un colchón explícito para preservar escenarios históricos de prueba.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil.
        monto: Valor a reservar.

    Returns:
        El perfil con el colchón guardado.
    """
    perfil = _perfil(bd, id_usuario)
    perfil.monto_minimo_liquidez = Decimal(monto)
    bd.commit()
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

    assert resultado.ingreso == Decimal("3209095.00")  # sueldo + auxilio 249.095
    # Solo la deducción de ley del 8 %: no hay gastos ni deudas.
    assert resultado.gastos == Decimal("236800.00")
    assert resultado.deudas == Decimal("0.00")
    assert resultado.semaforo == capacidad.ESTADO_VERDE
    assert resultado.porcentaje_deudas == Decimal("0.00")


def test_los_porcentajes_de_la_dona_suman_cien(bd) -> None:
    """Los arcos de la dona siempre cierran la circunferencia."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "2400000", "800000", 3)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _con_colchon(bd, id_usuario), HOY.year, HOY.month
    )

    total = sum((arco["porcentaje"] for arco in resultado.arcos), start=Decimal("0"))
    assert total == Decimal("100.0")
    # SRS v4.4: la cuota no se dibuja como tajada suelta; vive en la categoría
    # del gasto fijo vinculado registrado en el módulo.
    assert [arco["etiqueta"] for arco in resultado.arcos] == [
        "Gastos fijos",
        "Base mínima de liquidez",
        "Disponible para abonar",
    ]


def test_el_libre_se_parte_entre_la_base_y_lo_disponible(bd) -> None:
    """SRS v1.8: del libre, $300.000 son base mínima y el resto es abonable."""
    id_usuario = _id_admin(bd)
    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert resultado.base_minima == capacidad.BASE_MINIMA_LIQUIDEZ
    assert resultado.disponible_abono == resultado.libre - capacidad.BASE_MINIMA_LIQUIDEZ


def test_las_cifras_de_la_dona_usan_verde_y_rojo(bd) -> None:
    """Gastos y deudas salen en rojo; base y disponible, en verde (SRS v1.8)."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "2400000", "800000", 3)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _con_colchon(bd, id_usuario), HOY.year, HOY.month
    )

    clases = {arco["etiqueta"]: arco["clase"] for arco in resultado.arcos}
    assert clases["Gastos fijos"] == "valor-negativo"
    assert clases["Base mínima de liquidez"] == "valor-positivo"
    assert clases["Disponible para abonar"] == "valor-positivo"


def test_una_deuda_alta_pone_el_semaforo_en_rojo(bd) -> None:
    """Una cuota que supera el 35 % del ingreso enciende el semáforo rojo."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "5600000", "2800000", 2)

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, _perfil(bd, id_usuario), HOY.year, HOY.month
    )

    assert resultado.semaforo == capacidad.ESTADO_ROJO
    assert resultado.porcentaje_deudas > capacidad.UMBRAL_AMBAR
    # SRS v4.4: el compromiso se reporta, pero una deuda sin gasto fijo
    # registrado en el módulo no se descuenta del libre de la dona.
    assert resultado.deudas == Decimal("2800000.00")


def test_una_deuda_media_pone_el_semaforo_en_ambar(bd) -> None:
    """Entre 20 % y 35 % el semáforo avisa con ámbar."""
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Banco", "2400000", "800000", 3)

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
    assert resultado.ingreso == Decimal("3709095.00")  # sueldo + extras + auxilio


def test_presupuesto_muestra_el_panel_de_capacidad(cliente_admin) -> None:
    """«Gastos y Presupuesto» incluye la dona, sin la tabla de 12 meses."""
    respuesta = cliente_admin.get("/presupuesto")

    assert respuesta.status_code == 200
    assert "Capacidad de endeudamiento" in respuesta.text
    assert "Proyección a 12 meses" not in respuesta.text
    assert "Deudas por terminar" in respuesta.text
    # SRS v1.8: las cifras de la dona llevan verde/rojo según el signo.
    assert "valor-positivo" in respuesta.text


def test_trabajos_extras_muestra_su_propia_instancia(cliente_admin) -> None:
    """«Trabajos Extras» reutiliza el panel con su propio título."""
    respuesta = cliente_admin.get("/trabajos-extras")

    assert respuesta.status_code == 200
    assert "Ingresos extras" in respuesta.text
    assert "Deudas por terminar" not in respuesta.text
    assert "Proyección a 12 meses" not in respuesta.text


def test_dona_de_trabajos_solo_cuenta_cobrado_y_gastos_del_trabajo(bd) -> None:
    """La dona de Trabajos Extras ignora el sueldo: solo lo cobrado y sus gastos fijos."""
    from app.servicios import trabajos as servicio_trabajos

    id_usuario = _id_admin(bd)
    trabajo = servicio_trabajos.crear_trabajo(bd, id_usuario, "Diseño", "1.000.000", date(2026, 11, 1))
    servicio_trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    pago = servicio_trabajos._pagos_del_mes(bd, trabajo.id_trabajo, 2026, 11)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, pago.id_gasto, HOY)
    servicio_trabajos.crear_gasto_trabajo(bd, id_usuario, trabajo.id_trabajo, "Hogar", "Internet", "200.000")

    resultado = capacidad.capacidad_trabajos(bd, id_usuario, 2026, 11)

    assert resultado.ingreso == Decimal("1000000.00")
    assert resultado.gastos == Decimal("200000.00")
    assert resultado.libre == Decimal("800000.00")
    assert resultado.deudas == Decimal("0")


def test_dona_de_trabajos_no_reserva_la_base_minima(bd) -> None:
    """Trabajos Extras no aparta los $300.000 de liquidez: todo el libre queda disponible."""
    from app.servicios import trabajos as servicio_trabajos

    id_usuario = _id_admin(bd)
    servicio_trabajos.crear_trabajo(bd, id_usuario, "Diseño", "200.000", date(2026, 11, 1))
    servicio_trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)

    resultado = capacidad.capacidad_trabajos(bd, id_usuario, 2026, 11)

    assert resultado.libre == Decimal("200000.00")
    assert resultado.base_minima == Decimal("0")
    assert resultado.disponible_abono == Decimal("200000.00")
    etiquetas = [arco["etiqueta"] for arco in resultado.arcos_categoria]
    assert "Base mínima de liquidez" not in etiquetas


def test_credito_como_deduccion_cuenta_como_deuda(bd) -> None:
    """Una deducción que dice crédito pesa como deuda, no como gasto fijo."""
    from app.servicios import deducciones_fijas

    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    antes = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, 2026, 11)

    deducciones_fijas.crear_deduccion(bd, id_usuario, "Crédito libranza banco", "150.000", 1)
    despues = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, 2026, 11)

    assert despues.deudas - antes.deudas == Decimal("150000.00")
    # SRS v4.4: la deducción fija del módulo sí cuenta en sus gastos.
    assert despues.gastos > antes.gastos


def test_es_credito_ignora_tildes_y_mayusculas() -> None:
    """«Crédito», «CREDITOS» y «credito» cuentan; «crediticio» y «seguro» no."""
    assert capacidad.es_credito("Crédito libranza")
    assert capacidad.es_credito("CREDITOS")
    assert capacidad.es_credito("credito")
    assert not capacidad.es_credito("Seguro de vida")
    assert not capacidad.es_credito("Crediticio")


def test_libre_se_desglosa_entre_salario_y_extras(bd) -> None:
    """El libre total es la suma del libre del salario y el de trabajos extras."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    trabajo = trabajos.crear_trabajo(bd, id_usuario, "Diseño", "600.000", HOY.replace(day=1))
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, HOY.year, HOY.month)
    resultado = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, HOY.year, HOY.month)

    assert resultado.libre_extras == Decimal("600000.00")
    assert resultado.libre_salario + resultado.libre_extras == resultado.libre
