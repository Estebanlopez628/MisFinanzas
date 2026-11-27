"""Pruebas de los contratos y pagos de Trabajos Extras (SRS v1.7, bloque E).

Cubren la generación de pagos por frecuencia, el corte de un término fijo, la
ventana móvil de un contrato indefinido, el aislamiento frente a gastos y
quincenas, el neto que llega al diagnóstico del mes y la eliminación en cascada.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import base_datos
from app.modelos import Gasto
from app.servicios import ahorro, gastos, pagos_metas, perfiles, trabajos, usuarios

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


def _pagos(bd, id_trabajo: str) -> list[Gasto]:
    """Lista los pagos generados por un contrato, ordenados por fecha.

    Args:
        bd: Sesión de base de datos.
        id_trabajo: Contrato consultado.

    Returns:
        Lista de pagos.
    """
    consulta = (
        select(Gasto)
        .where(Gasto.id_trabajo == id_trabajo)
        .order_by(Gasto.fecha)
    )
    return list(bd.scalars(consulta))


# ---------------------------------------------------------------------------
# Generación de pagos
# ---------------------------------------------------------------------------


def test_contrato_mensual_genera_un_pago_por_mes(bd) -> None:
    """Con frecuencia mensual hay un solo pago al mes, sin quincena."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Diseño de logo",
        "500.000",
        date(2026, 11, 1),
        "ACME",
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        frecuencia=trabajos.FRECUENCIA_MENSUAL,
        fecha_fin=date(2026, 11, 30),
        fecha_pago=date(2026, 11, 20),
    )
    creados = trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)

    pagos = _pagos(bd, trabajo.id_trabajo)
    assert creados == 1
    assert len(pagos) == 1
    assert pagos[0].quincena is None
    assert pagos[0].fecha == date(2026, 11, 20)
    assert pagos[0].valor == Decimal("500000.00")


TOTAL = Decimal("600000")


def test_contrato_quincenal_genera_dos_pagos(bd) -> None:
    """Con frecuencia quincenal hay pagos en la quincena 1 y en la 2."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Asesoría",
        "600.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_fin=date(2026, 11, 30),
        fecha_pago=date(2026, 11, 15),
        fecha_pago_quincena_2=date(2026, 11, 30),
        quincena_digitada=1,
        valor_quincena="250.000",
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)

    pagos = _pagos(bd, trabajo.id_trabajo)
    assert [pago.quincena for pago in pagos] == [1, 2]
    assert [pago.fecha.day for pago in pagos] == [15, 30]
    assert [pago.valor for pago in pagos] == [Decimal("250000.00"), Decimal("350000.00")]


def test_quincena_escrita_como_dos_calcula_la_uno(bd) -> None:
    """Si se escribe la quincena 2, la 1 es el total menos esa cantidad."""
    trabajo = trabajos.crear_trabajo(
        bd,
        _id_admin(bd),
        "Diseño",
        "600.000",
        date(2026, 11, 1),
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_pago_quincena_2=date(2026, 11, 30),
        quincena_digitada="2",
        valor_quincena="250.000",
    )

    assert trabajo.valor_quincena_1 == Decimal("350000.00")
    assert trabajo.valor_quincena_2 == Decimal("250000.00")


def test_porcentajes_conocidos_reparten_el_total(bd) -> None:
    """Con los porcentajes de la usuaria, cada quincena es su parte del total."""
    trabajo = trabajos.crear_trabajo(
        bd,
        _id_admin(bd),
        "Soporte",
        "600.000",
        date(2026, 11, 1),
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_pago_quincena_2=date(2026, 11, 30),
        conoce_porcentaje=True,
        porcentaje_quincena_1="40",
        porcentaje_quincena_2="60",
    )

    assert trabajo.valor_quincena_1 == Decimal("240000.00")
    assert trabajo.valor_quincena_2 == Decimal("360000.00")


def test_porcentajes_deben_sumar_cien() -> None:
    """Los dos porcentajes deben sumar exactamente 100 %."""
    with pytest.raises(ValueError, match="sumar 100"):
        trabajos.reparto_por_porcentajes(TOTAL, Decimal("40"), Decimal("50"))


def test_quincena_escrita_no_puede_superar_el_total() -> None:
    """Una quincena no puede valer más que el pago del mes."""
    with pytest.raises(ValueError, match="superar"):
        trabajos.reparto_quincenal(TOTAL, 1, Decimal("700000"))


def test_quincenal_sin_quincena_escrita_se_rechaza(bd) -> None:
    """Un contrato quincenal debe indicar qué quincena se escribió."""
    with pytest.raises(ValueError, match="quincena 1 o la quincena 2"):
        trabajos.crear_trabajo(
            bd,
            _id_admin(bd),
            "Asesoría",
            "600.000",
            date(2026, 11, 1),
            frecuencia=trabajos.FRECUENCIA_QUINCENAL,
            fecha_pago_quincena_2=date(2026, 11, 30),
            valor_quincena="250.000",
        )


def test_quincenal_con_porcentajes_incompletos_se_rechaza(bd) -> None:
    """Si dice que conoce los porcentajes, debe escribir los dos."""
    with pytest.raises(ValueError, match="porcentajes"):
        trabajos.crear_trabajo(
            bd,
            _id_admin(bd),
            "Asesoría",
            "600.000",
            date(2026, 11, 1),
            frecuencia=trabajos.FRECUENCIA_QUINCENAL,
            fecha_pago_quincena_2=date(2026, 11, 30),
            conoce_porcentaje=True,
            porcentaje_quincena_1="40",
        )


def test_quincena_ajusta_al_ultimo_dia_del_mes(bd) -> None:
    """El día 30 se ajusta al 28 en un febrero no bisiesto."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Soporte",
        "400.000",
        date(2027, 2, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_fin=date(2027, 2, 28),
        fecha_pago=date(2027, 2, 15),
        fecha_pago_quincena_2=date(2027, 2, 28),
        quincena_digitada=1,
        valor_quincena="200.000",
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2027, 2)

    pagos = _pagos(bd, trabajo.id_trabajo)
    assert [pago.fecha for pago in pagos] == [
        date(2027, 2, 15),
        date(2027, 2, 28),
    ]


def test_termino_fijo_no_genera_pagos_despues_del_fin(bd) -> None:
    """La generación se detiene en el mes de `fecha_fin`."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Consultoría",
        "400.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        fecha_fin=date(2027, 1, 15),
        fecha_pago=date(2026, 11, 1),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)

    pagos = _pagos(bd, trabajo.id_trabajo)
    assert [pago.fecha.month for pago in pagos] == [11, 12, 1]
    assert max(pago.fecha for pago in pagos).year == 2027
    assert all(pago.fecha.year == 2026 or pago.fecha.month == 1 for pago in pagos)


def test_indefinido_extiende_la_ventana_al_abrir_el_modulo(bd) -> None:
    """Un contrato indefinido cubre doce meses y crece con el mes visible."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Mantenimiento",
        "150.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_INDEFINIDO,
        fecha_pago=date(2026, 11, 1),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    assert len(_pagos(bd, trabajo.id_trabajo)) == 12

    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2027, 3)

    pagos = _pagos(bd, trabajo.id_trabajo)
    # De noviembre de 2026 a febrero de 2028 hay 16 meses.
    assert len(pagos) == 16
    assert pagos[-1].fecha.year == 2028
    assert pagos[-1].fecha.month == 2


def test_abrir_dos_veces_no_duplica_pagos(bd) -> None:
    """La generación es idempotente por contrato y mes."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Clases",
        "100.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        fecha_fin=date(2026, 11, 30),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)

    assert len(_pagos(bd, trabajo.id_trabajo)) == 1


# ---------------------------------------------------------------------------
# Aislamiento y diagnóstico
# ---------------------------------------------------------------------------


def test_pagos_de_trabajo_no_restan_en_gastos_ni_quincenas(bd) -> None:
    """Los pagos de trabajos no son gastos ni entran en los totales del mes."""
    id_usuario = _id_admin(bd)
    trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Reparación",
        "800.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        fecha_fin=date(2026, 11, 30),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)

    assert gastos.listar_gastos(bd, id_usuario, 2026, 11) == []
    assert gastos.total_gastos_mes(bd, id_usuario, 2026, 11) == Decimal("0.00")


def test_check_del_pago_suma_al_diagnostico_del_mes(bd) -> None:
    """El neto cobrado se suma al disponible sin mover el saldo libre."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Reparación",
        "800.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        fecha_fin=date(2026, 11, 30),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    pago = _pagos(bd, trabajo.id_trabajo)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, pago.id_gasto, date(2026, 11, 15))

    assert trabajos.extras_cobrados_mes(bd, id_usuario, 2026, 11) == Decimal(
        "800000.00"
    )
    diagnostico = ahorro.diagnostico(
        bd, id_usuario, perfiles.obtener_perfil(bd, id_usuario), 2026, 11
    )
    assert diagnostico["extras_mes"] == Decimal("800000.00")
    assert diagnostico["disponible"] == diagnostico["saldo_libre"] + Decimal(
        "800000.00"
    )


def test_desmarcar_el_pago_no_cambia_el_valor_del_diagnostico(bd) -> None:
    """Quitar el ✔ devuelve el extra a pendiente."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Reparación",
        "800.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        fecha_fin=date(2026, 11, 30),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    pago = _pagos(bd, trabajo.id_trabajo)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, pago.id_gasto, date(2026, 11, 15))
    pagos_metas.desmarcar_pagado(bd, id_usuario, pago.id_gasto)

    assert trabajos.extras_cobrados_mes(bd, id_usuario, 2026, 11) == Decimal("800000.00")


# ---------------------------------------------------------------------------
# Eliminación y validación
# ---------------------------------------------------------------------------


def test_eliminar_trabajo_borra_sus_pagos(bd) -> None:
    """Eliminar el contrato elimina también sus pagos generados."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Reparación",
        "800.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        fecha_fin=date(2026, 11, 30),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    assert _pagos(bd, trabajo.id_trabajo)

    assert trabajos.eliminar_trabajo(bd, id_usuario, trabajo.id_trabajo) is True
    assert _pagos(bd, trabajo.id_trabajo) == []


def test_termino_fijo_exige_fecha_final(bd) -> None:
    """Un contrato a término fijo sin fecha final se rechaza."""
    try:
        trabajos.crear_trabajo(
            bd,
            _id_admin(bd),
            "Consultoría",
            "100.000",
            date(2026, 11, 1),
            tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        )
    except ValueError as error:
        assert "fecha final" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_fecha_de_pago_anterior_al_inicio_se_rechaza(bd) -> None:
    """El primer pago no puede preceder el inicio del contrato."""
    try:
        trabajos.crear_trabajo(
            bd,
            _id_admin(bd),
            "Consultoría",
            "100.000",
            date(2026, 11, 10),
            fecha_pago=date(2026, 11, 1),
        )
    except ValueError as error:
        assert "anterior" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


# ---------------------------------------------------------------------------
# Camino HTTP
# ---------------------------------------------------------------------------


def test_http_crea_contrato_y_muestra_sus_pagos(cliente_admin: TestClient) -> None:
    """El formulario guarda el contrato y la vista lista el pago del mes."""
    inicio = HOY.replace(day=1)
    fin = (inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    respuesta = cliente_admin.post(
        "/trabajos-extras",
        data={
            "descripcion": "Asesoría contable",
            "cliente": "Cliente X",
            "valor": "300.000",
            "fecha": inicio.isoformat(),
            "fecha_pago": inicio.isoformat(),
            "tipo_contrato": "TERMINO_FIJO",
            "frecuencia": "QUINCENAL",
            "quincena_digitada": "1",
            "fecha_pago_quincena_2": fin.isoformat(),
            "valor_quincena": "150.000",
            "fecha_fin": fin.isoformat(),
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    html = cliente_admin.get("/trabajos-extras").text
    assert "Asesoría contable" in html
    assert "Pagos de" in html
    assert "Trabajo · Asesoría contable" in html
    assert html.count("boton-circular--check") == 2


def test_http_contrato_invalido_vuelve_con_error(cliente_admin: TestClient) -> None:
    """Un término fijo sin fecha final muestra el error en la vista."""
    respuesta = cliente_admin.post(
        "/trabajos-extras",
        data={
            "descripcion": "Asesoría",
            "valor": "100.000",
            "fecha": HOY.isoformat(),
            "tipo_contrato": "TERMINO_FIJO",
            "frecuencia": "MENSUAL",
        },
    )

    assert respuesta.status_code == 400
    assert "fecha final" in respuesta.text.lower()


# ---------------------------------------------------------------------------
# Migración
# ---------------------------------------------------------------------------


def test_migracion_de_trabajos_es_idempotente() -> None:
    """Ejecutar la migración dos veces no falla ni duplica columnas."""
    base_datos._migrar_columnas_trabajos()
    base_datos._migrar_columnas_trabajos()

    with base_datos.motor.connect() as conexion:
        columnas = [
            fila[1]
            for fila in conexion.exec_driver_sql("PRAGMA table_info(trabajos_extras)")
        ]

    assert {"tipo_contrato", "frecuencia", "fecha_fin", "fecha_pago"} <= set(columnas)


def test_pagos_mensuales_muestran_mes_completo(cliente_admin, bd) -> None:
    """Un contrato mensual muestra una sola tabla «Pago mensual» con gastos fijos."""
    trabajos.crear_trabajo(bd, _id_admin(bd), "Mensual", "500.000", HOY.replace(day=1))

    html = cliente_admin.get("/trabajos-extras").text

    assert "Pago mensual" in html
    assert 'quincena__titulo">Quincena 1' not in html
    assert "Agregar gasto fijo" in html


def test_pagos_quincenales_muestran_dos_tablas(cliente_admin, bd) -> None:
    """Un contrato quincenal muestra las tablas de la quincena 1 y la 2."""
    trabajos.crear_trabajo(
        bd,
        _id_admin(bd),
        "Quincenal",
        "300.000",
        HOY.replace(day=1),
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_pago_quincena_2=date(2026, 11, 30),
        quincena_digitada=1,
        valor_quincena="150.000",
    )

    html = cliente_admin.get("/trabajos-extras").text

    assert 'quincena__titulo form-header-white form-header-white--inline">Quincena 1 · día 15' in html
    assert 'quincena__titulo form-header-white form-header-white--inline">Quincena 2 · día 30' in html
    assert "Mes completo" not in html


def test_botones_de_vuelta_en_los_modulos_de_finanzas(cliente_admin) -> None:
    """Mis Finanzas, Gastos y Presupuesto, Deudas y Trabajos ofrecen volver."""
    assert "Volver al inicio" in cliente_admin.get("/finanzas").text
    assert "Volver a Mis Finanzas" in cliente_admin.get("/presupuesto").text
    assert "Volver al inicio" in cliente_admin.get("/deudas").text
    assert "Volver al inicio" in cliente_admin.get("/trabajos-extras").text


def test_gasto_fijo_de_trabajo_no_pasa_a_las_quincenas(bd) -> None:
    """Un gasto fijo del trabajo solo vive en Trabajos Extras, no en Mis Finanzas."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Diseño",
        "600.000",
        date(2026, 11, 1),
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_pago_quincena_2=date(2026, 11, 30),
        quincena_digitada=1,
        valor_quincena="250.000",
    )
    trabajos.crear_gasto_trabajo(bd, id_usuario, trabajo.id_trabajo, "Hogar", "Transporte", "80.000", "1")

    assert gastos.listar_gastos(bd, id_usuario) == []
    assert gastos.total_gastos_quincena(bd, id_usuario, 2026, 11, 1) == Decimal("0")
    assert [g.descripcion for g in trabajos.gastos_fijos_trabajo(bd, trabajo.id_trabajo)] == ["Transporte"]


def test_disponible_es_cobrado_menos_gastos_del_trabajo(bd) -> None:
    """El disponible que viaja al diagnóstico descuenta los gastos fijos del trabajo."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(bd, id_usuario, "Diseño", "500.000", date(2026, 11, 1))
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    pago = _pagos(bd, trabajo.id_trabajo)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, pago.id_gasto, HOY)
    trabajos.crear_gasto_trabajo(bd, id_usuario, trabajo.id_trabajo, "Hogar", "Internet", "120.000")

    assert trabajos.extras_cobrados_mes(bd, id_usuario, 2026, 11) == Decimal("380000.00")


def test_http_gasto_fijo_de_trabajo_se_queda_en_trabajos(cliente_admin, bd) -> None:
    """El formulario del trabajo guarda el gasto y no aparece en Mis Finanzas."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(bd, id_usuario, "Diseño", "500.000", HOY.replace(day=1))

    respuesta = cliente_admin.post(
        f"/trabajos-extras/{trabajo.id_trabajo}/gastos",
        data={"categoria": "Hogar", "descripcion": "Gasto-solo-trabajo", "valor": "90.000"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert "Gasto-solo-trabajo" in cliente_admin.get("/trabajos-extras").text
    assert "Gasto-solo-trabajo" not in cliente_admin.get("/finanzas").text


def test_caso_confirmado_por_la_usuaria(bd) -> None:
    """El valor del pago es el total: 1.500.000 con 50/50 da 750.000 cada quincena."""
    id_usuario = _id_admin(bd)
    quincenal = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Consultoría",
        "1.500.000",
        date(2026, 11, 1),
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_pago_quincena_2=date(2026, 11, 30),
        conoce_porcentaje=True,
        porcentaje_quincena_1="50",
        porcentaje_quincena_2="50",
    )
    por_valor = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Consultoría",
        "1.500.000",
        date(2026, 11, 1),
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_pago_quincena_2=date(2026, 11, 30),
        quincena_digitada=1,
        valor_quincena="600.000",
    )
    mensual = trabajos.crear_trabajo(bd, id_usuario, "Consultoría", "1.500.000", date(2026, 11, 1))

    assert (quincenal.valor_quincena_1, quincenal.valor_quincena_2) == (
        Decimal("750000.00"),
        Decimal("750000.00"),
    )
    assert (por_valor.valor_quincena_1, por_valor.valor_quincena_2) == (
        Decimal("600000.00"),
        Decimal("900000.00"),
    )
    assert mensual.valor == Decimal("1500000.00")
    assert trabajos.porcentaje_del_total(por_valor.valor_quincena_2, por_valor.valor) == Decimal("60.0")


def test_pago_saltado_no_suma_al_diagnostico(bd) -> None:
    """Un pago saltado con la x ya no se espera: no suma al diagnostico."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(bd, id_usuario, "Asesoria", "500.000", date(2026, 11, 1))
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    pago = _pagos(bd, trabajo.id_trabajo)[0]
    pagos_metas.quitar_gasto(bd, id_usuario, pago.id_gasto, hoy=HOY)

    assert trabajos.extras_cobrados_mes(bd, id_usuario, 2026, 11) == Decimal("0.00")
