"""Pruebas de regresión del fallo de categorías en Trabajos Extras (ADR-60).

La migración de categorías no debe reclasificar los pagos generados por un
trabajo extra: si los convierte a «Otros Gastos Fijos», la comprobación de
idempotencia deja de encontrarlos y crea duplicados en cada arranque.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core import base_datos
from app.core.categorias import CATEGORIA_TRABAJO
from app.modelos import Base, Gasto, TrabajoExtra
from app.servicios import trabajos, usuarios


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


def test_migracion_no_reclasifica_pagos_de_trabajo(tmp_path, monkeypatch) -> None:
    """La normalización deja intacta la categoría técnica de los pagos."""
    ruta = tmp_path / "pagos.db"
    motor = create_engine(f"sqlite:///{ruta.as_posix()}")
    with motor.begin() as conexion:
        conexion.exec_driver_sql(
            "CREATE TABLE deudas (id_deuda VARCHAR(32) PRIMARY KEY, estado VARCHAR(20))"
        )
        conexion.exec_driver_sql(
            "CREATE TABLE gastos (id_gasto VARCHAR(32) PRIMARY KEY, categoria VARCHAR(60))"
        )
        conexion.exec_driver_sql(
            "CREATE TABLE deducciones_fijas ("
            "id_deduccion VARCHAR(32) PRIMARY KEY, descripcion VARCHAR(150))"
        )
        conexion.exec_driver_sql(
            "INSERT INTO gastos VALUES ('g1', 'Vivienda'), ('g2', 'Trabajo extra')"
        )

    monkeypatch.setattr(base_datos, "motor", motor)
    monkeypatch.setattr(base_datos, "_conexion_sqlite", True)
    base_datos._migrar_categorias_y_vinculos()
    # Segunda pasada: sigue sin reclasificar.
    base_datos._migrar_categorias_y_vinculos()

    with motor.connect() as conexion:
        categorias = dict(
            conexion.exec_driver_sql(
                "SELECT id_gasto, categoria FROM gastos ORDER BY id_gasto"
            ).fetchall()
        )
    motor.dispose()

    assert categorias["g1"] == "Vivienda y Servicios"
    assert categorias["g2"] == CATEGORIA_TRABAJO


def test_asegurar_no_duplica_despues_de_la_migracion(tmp_path, monkeypatch) -> None:
    """Tras migrar, el módulo reconoce sus pagos y no crea copias nuevas."""
    ruta = tmp_path / "trabajos.db"
    motor = create_engine(f"sqlite:///{ruta.as_posix()}")
    Base.metadata.create_all(motor)

    with Session(motor) as sesion:
        trabajo = TrabajoExtra(
            id_usuario="u1",
            descripcion="Auditoría y mantenimientos",
            valor=Decimal("1500000"),
            fecha=date(2026, 11, 1),
            tipo_contrato=trabajos.CONTRATO_INDEFINIDO,
            frecuencia=trabajos.FRECUENCIA_MENSUAL,
            fecha_pago=date(2026, 11, 25),
            estado=trabajos.ESTADO_PENDIENTE,
        )
        sesion.add(trabajo)
        sesion.commit()
        id_trabajo = trabajo.id_trabajo

    with Session(motor) as sesion:
        creados = trabajos.asegurar_pagos_trabajos(sesion, "u1", 2026, 11)
        total_antes = len(
            list(sesion.scalars(select(Gasto).where(Gasto.id_trabajo == id_trabajo)))
        )
    assert creados > 0

    monkeypatch.setattr(base_datos, "motor", motor)
    monkeypatch.setattr(base_datos, "_conexion_sqlite", True)
    base_datos._migrar_categorias_y_vinculos()

    with Session(motor) as sesion:
        pagos = list(sesion.scalars(select(Gasto).where(Gasto.id_trabajo == id_trabajo)))
        assert {pago.categoria for pago in pagos} == {CATEGORIA_TRABAJO}
        creados_despues = trabajos.asegurar_pagos_trabajos(sesion, "u1", 2026, 11)
        total_despues = len(
            list(sesion.scalars(select(Gasto).where(Gasto.id_trabajo == id_trabajo)))
        )
    motor.dispose()

    assert creados_despues == 0
    assert total_despues == total_antes


def test_reparar_restaura_categoria_y_elimina_duplicados(bd) -> None:
    """La reparación devuelve la categoría y deja un solo pago por mes."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd,
        id_usuario,
        "Auditoría y mantenimientos",
        "1500000",
        date(2026, 11, 1),
        tipo_contrato=trabajos.CONTRATO_TERMINO_FIJO,
        frecuencia=trabajos.FRECUENCIA_MENSUAL,
        fecha_fin=date(2026, 11, 30),
        fecha_pago=date(2026, 11, 25),
    )
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, 2026, 11)
    original = bd.scalars(
        select(Gasto).where(Gasto.id_trabajo == trabajo.id_trabajo)
    ).one()

    # Se simula el fallo: tres copias reclasificadas por la migración vieja.
    for _ in range(3):
        bd.add(
            Gasto(
                id_usuario=id_usuario,
                categoria="Otros Gastos Fijos",
                descripcion=original.descripcion,
                valor=original.valor,
                es_fijo=True,
                fecha=original.fecha,
                quincena=original.quincena,
                id_trabajo=trabajo.id_trabajo,
                pagado=False,
                check_visible=True,
            )
        )
    bd.commit()
    assert len(list(bd.scalars(select(Gasto).where(Gasto.id_trabajo == trabajo.id_trabajo)))) == 4

    resultado = trabajos.reparar_pagos_duplicados(bd)

    assert resultado == {"restaurados": 3, "eliminados": 3}
    pagos = list(bd.scalars(select(Gasto).where(Gasto.id_trabajo == trabajo.id_trabajo)))
    assert len(pagos) == 1
    assert pagos[0].categoria == CATEGORIA_TRABAJO

    # Segunda pasada: idempotente.
    assert trabajos.reparar_pagos_duplicados(bd) == {"restaurados": 0, "eliminados": 0}
