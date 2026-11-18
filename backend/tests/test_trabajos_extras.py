"""Pruebas de los contratos y pagos de Trabajos Extras (SRS v1.7, bloque E).

Cubren la generación de pagos por frecuencia, el corte de un término fijo, la
ventana móvil de un contrato indefinido, el aislamiento frente a gastos y
quincenas, el neto que llega al diagnóstico del mes y la eliminación en cascada.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

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


def test_contrato_quincenal_genera_dos_pagos(bd) -> None:
    """Con frecuencia quincenal hay pagos en la quincena 1 y en la 2."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Asesoría",
        "300.000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_fin=date(2026, 11, 30),
        fecha_pago=date(2026, 11, 1),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)

    pagos = _pagos(bd, trabajo.id_trabajo)
    assert [pago.quincena for pago in pagos] == [1, 2]
    assert [pago.fecha.day for pago in pagos] == [15, 30]


def test_quincena_ajusta_al_ultimo_dia_del_mes(bd) -> None:
    """El día 30 se ajusta al 28 en un febrero no bisiesto."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Soporte",
        "200.000",
        date(2027, 2, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        frecuencia=trabajos.FRECUENCIA_QUINCENAL,
        fecha_fin=date(2027, 2, 28),
        fecha_pago=date(2027, 2, 1),
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


def test_desmarcar_el_pago_retira_el_neto_del_diagnostico(bd) -> None:
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

    assert trabajos.extras_cobrados_mes(bd, id_usuario, 2026, 11) == Decimal("0.00")


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
