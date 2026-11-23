"""Pruebas del catálogo cerrado, migraciones y anti-duplicación (SRS v1.9).

Cubren el Paso 1 de la especificación: ocho categorías con colores exactos,
columnas nuevas en SQLite/PostgreSQL, esquemas Pydantic, tasa implícita
simulada y la regla de no contar dos veces las cuotas vinculadas a deudas.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import esquemas
from app.core import base_datos, categorias as catalogo
from app.modelos import Deuda
from app.servicios import capacidad, consejero, deudas, gastos, perfiles, usuarios

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


def test_catalogo_tiene_ocho_categorias_con_los_colores_exactos() -> None:
    """El catálogo cerrado coincide con el SRS, incluido el orden y los colores."""
    esperado = (
        ("Vivienda y Servicios", "#3B82F6"),
        # SRS v3.4: paleta de diez colores únicos, sin colisiones en la dona.
        ("Alimentación y Mercado", "#F97316"),
        ("Transporte y Movilidad", "#EAB308"),
        ("Salud y Bienestar", "#06B6D4"),
        ("Telefonía y Suscripciones", "#EC4899"),
        ("Educación y Familia", "#8B5CF6"),
        ("Otros Gastos Fijos", "#64748B"),
        ("Créditos y Obligaciones", "#EF4444"),
    )
    assert tuple((fila["nombre"], fila["color"]) for fila in catalogo.lista_categorias()) == esperado
    assert len(catalogo.CATEGORIAS) == 8


def test_normalizar_categoria_valida_texto_heredado_y_rechaza_invalido() -> None:
    """Los alias históricos se convierten y el modo estricto rechaza textos libres."""
    assert catalogo.normalizar_categoria("vivienda") == "Vivienda y Servicios"
    assert catalogo.normalizar_categoria("Mercado") == "Alimentación y Mercado"
    assert catalogo.normalizar_categoria("OCIO") == "Otros Gastos Fijos"
    assert catalogo.normalizar_categoria("inventado") == "Otros Gastos Fijos"
    with pytest.raises(ValueError, match="categoría válida"):
        catalogo.normalizar_categoria("inventado", estricto=True)
    assert catalogo.color_de_categoria("Créditos y Obligaciones") == "#EF4444"


def test_esquemas_pydantic_rechazan_categoria_fuera_del_catalogo() -> None:
    """El esquema bloquea texto libre y permite la categoría 8 con deuda."""
    datos = dict(
        categoria="Transporte",
        descripcion="Gasolina",
        valor="120.000",
        fecha="2026-11-10",
    )
    valido = esquemas.validar_formulario(esquemas.GastoNuevo, **datos)
    assert valido.categoria == "Transporte y Movilidad"

    with pytest.raises(ValueError, match="categoría válida"):
        esquemas.validar_formulario(esquemas.GastoNuevo, **{**datos, "categoria": "Ocio raro"})
    with pytest.raises(ValueError, match="para poder guardar este registro"):
        esquemas.validar_formulario(
            esquemas.GastoNuevo, **{**datos, "categoria": "Créditos y Obligaciones"}
        )
    vinculado = esquemas.validar_formulario(
        esquemas.GastoNuevo,
        **{**datos, "categoria": "Créditos y Obligaciones", "id_deuda": "abc123"},
    )
    assert vinculado.categoria == "Créditos y Obligaciones"


def test_tasa_implicita_simulada_no_cobra_intereses() -> None:
    """La simulación deriva una tasa sin guardarla ni modificar la amortización."""
    assert deudas.tasa_implicita_simulada("1200000", "400000", 3) == Decimal("0E-10")

    simulada = deudas.tasa_implicita_simulada("3500000", "100000", 48)
    # El ejemplo histórico daba 0,0137085766; con 10 decimales el último dígito
    # puede subir uno según el criterio de redondeo del contexto decimal.
    assert abs(simulada - Decimal("0.0137085766")) <= Decimal("0.000000001")

    esquema = esquemas.validar_formulario(
        esquemas.DeudaNueva,
        acreedor="Banco",
        saldo_total="3500000",
        cuota="100000",
        cuotas_pendientes="48",
    )
    assert esquema.tasa_implicita == simulada


def test_la_tasa_simulada_no_altera_los_pagos(bd) -> None:
    """Los abonos siguen sin intereses aunque el plan implique una tasa."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)
    cuotas = deudas.proyeccion_deuda(deuda)

    assert cuotas[0].abono_capital == Decimal("400000.00")
    assert cuotas[-1].ultima is True
    # Los pagos aplicados tampoco cobran intereses (columna heredada en cero).
    deuda_bd = bd.get(Deuda, deuda.id_deuda)
    deuda_bd.fecha_creacion = deuda_bd.fecha_creacion.replace(year=2020)
    bd.commit()
    assert deudas.aplicar_cuotas_vencidas(bd, id_usuario) > 0
    pagos = deudas.listar_pagos(bd, id_usuario)[deuda.id_deuda]
    assert all(pago.interes == CERO for pago in pagos)


CERO = Decimal("0")


def test_migracion_agrega_columnas_y_normaliza_en_sqlite(tmp_path, monkeypatch) -> None:
    """La migración idempotente añade `categoria` y `id_deuda` y limpia textos."""
    ruta = tmp_path / "antigua.db"
    motor_viejo = create_engine(f"sqlite:///{ruta.as_posix()}")
    with motor_viejo.begin() as conexion:
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
            "INSERT INTO gastos VALUES ('g1', 'Vivienda'), ('g2', 'Ocio')"
        )
        conexion.exec_driver_sql(
            "INSERT INTO deducciones_fijas VALUES ('d1', 'Crédito libranza')"
        )

    monkeypatch.setattr(base_datos, "motor", motor_viejo)
    monkeypatch.setattr(base_datos, "_conexion_sqlite", True)
    base_datos._migrar_categorias_y_vinculos()
    # Segunda pasada: no debe fallar ni duplicar columnas.
    base_datos._migrar_categorias_y_vinculos()

    with motor_viejo.connect() as conexion:
        columnas_gastos = {
            fila[1] for fila in conexion.exec_driver_sql("PRAGMA table_info(gastos)").fetchall()
        }
        columnas_fijas = {
            fila[1]
            for fila in conexion.exec_driver_sql("PRAGMA table_info(deducciones_fijas)").fetchall()
        }
        categorias = conexion.exec_driver_sql("SELECT categoria FROM gastos ORDER BY id_gasto").fetchall()
        deduccion = conexion.exec_driver_sql(
            "SELECT categoria FROM deducciones_fijas WHERE id_deduccion = 'd1'"
        ).scalar()
    assert "id_deuda" in columnas_gastos
    assert {"categoria", "id_deuda"} <= columnas_fijas
    assert [fila[0] for fila in categorias] == ["Vivienda y Servicios", "Otros Gastos Fijos"]
    assert deduccion == "Créditos y Obligaciones"
    motor_viejo.dispose()


def test_dona_no_duplica_un_gasto_vinculado_a_deuda(bd) -> None:
    """La cuota vinculada cuenta en la categoría 8 y no como gasto fijo."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    antes = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, HOY.year, HOY.month)

    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)
    gasto = gastos.crear_gasto(
        bd,
        id_usuario,
        "Vivienda",
        "Cuota del crédito",
        "999999",
        HOY,
        es_fijo=True,
        id_deuda=deuda.id_deuda,
    )
    despues = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, HOY.year, HOY.month)

    assert gasto.id_deuda == deuda.id_deuda
    assert gasto.valor == Decimal("400000.00")
    assert gasto.categoria == "Créditos y Obligaciones"
    # SRS v4.4: el gasto vinculado sí se descuenta en Gastos y Presupuestos
    # (sección 3) y su cuota se cuenta una sola vez en la dona (sección 1).
    assert despues.gastos >= antes.gastos + Decimal("400000.00")
    obligaciones = next(fila for fila in despues.categorias if fila["es_obligacion"])
    assert obligaciones["valor"] == Decimal("400000.00")
    assert obligaciones["color"] == "#EF4444"
    # SRS v4.4: la cuota registrada vive dentro de las categorías; `deudas` es
    # solo el compromiso informativo del semáforo.
    assert despues.deudas == Decimal("400000.00")
    assert sum((fila["valor"] for fila in despues.categorias), CERO) == despues.gastos


def test_dona_y_consejero_respetan_el_colchon_de_trescientos_mil(bd) -> None:
    """La base mínima se aparta antes de ofrecer el excedente al consejero."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    resultado = capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, HOY.year, HOY.month)
    consejo = consejero.consejo_financiero(bd, id_usuario, "Admin", resultado.libre)

    assert resultado.base_minima == Decimal("300000.00")
    assert resultado.disponible_abono == resultado.libre - Decimal("300000.00")
    assert consejo.excedente == resultado.disponible_abono
    assert sum((fila["porcentaje"] for fila in resultado.arcos_categoria), CERO) == Decimal("100.0")


def test_router_rechaza_categoria_invalida(cliente_admin: TestClient, bd) -> None:
    """El formulario HTTP solo acepta las categorías del catálogo cerrado."""
    respuesta = cliente_admin.post(
        "/gastos",
        data={
            "categoria": "Texto inventado",
            "descripcion": "Gasolina",
            "valor": "120.000",
            "fecha": "2026-11-10",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 400
    assert "categoría válida" in respuesta.text

    correcta = cliente_admin.post(
        "/gastos",
        data={
            "categoria": "Transporte",
            "descripcion": "Gasolina",
            "valor": "120.000",
            "fecha": "2026-11-10",
        },
        follow_redirects=False,
    )
    assert correcta.status_code == 303
    assert gastos.listar_gastos(bd, _id_admin(bd))[0].categoria == "Transporte y Movilidad"
