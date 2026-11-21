"""Pruebas de la deducción vinculada a una deuda (SRS v1.9, ADR-56).

Una libranza es a la vez un descuento de nómina y un crédito con cuotas. Estas
pruebas verifican que el dinero se cuenta una sola vez, que la deducción toma la
cuota de la deuda, que deja de descontarse al pagarse y que la vista muestra las
cuotas que faltan.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.modelos import Deuda
from app.servicios import (
    ahorro,
    capacidad,
    deducciones_fijas,
    deudas,
    perfiles,
    quincenas,
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


def _capacidad(bd, id_usuario: str):
    """Calcula la capacidad del mes actual para el usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los datos.

    Returns:
        Capacidad del mes en curso.
    """
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    return capacidad.capacidad_endeudamiento(bd, id_usuario, perfil, HOY.year, HOY.month)


def test_la_cuota_se_cuenta_una_sola_vez(bd) -> None:
    """Con la deducción vinculada, el libre es el mismo que con una deducción simple."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)
    vinculada = deducciones_fijas.crear_deduccion(
        bd, id_usuario, "Libranza banco", "999999", 2, deuda.id_deuda
    )
    con_vinculo = _capacidad(bd, id_usuario)

    assert vinculada.valor == Decimal("400000.00")
    # SRS v1.9: la cuota vive en la categoría 8 (deudas), no en gastos fijos.
    # Antes se restaba de `deudas`; ahora es la deuda la que se muestra y el
    # descuento vinculado deja de contarse como gasto, para no duplicarlo.
    assert con_vinculo.deudas == Decimal("400000.00")
    assert con_vinculo.gastos == Decimal("236800.00")

    # Comparación: solo el descuento, sin deuda. Ese es el libre correcto.
    deudas.eliminar_deuda(bd, id_usuario, deuda.id_deuda)
    solo_descuento = _capacidad(bd, id_usuario)

    assert solo_descuento.deudas == Decimal("0.00")
    assert con_vinculo.libre == solo_descuento.libre


def test_el_diagnostico_y_la_dona_coinciden_con_vinculo(bd) -> None:
    """El disponible del mes y el total libre salen iguales con la deuda vinculada."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Libranza", "0", 2, deuda.id_deuda)
    perfil = perfiles.obtener_perfil(bd, id_usuario)

    diagnostico = ahorro.diagnostico(bd, id_usuario, perfil, HOY.year, HOY.month)
    dona = _capacidad(bd, id_usuario)

    assert diagnostico["cuota_deudas"] == dona.deudas
    assert diagnostico["disponible"] == dona.libre


def test_la_deduccion_deja_de_descontarse_al_pagarse_la_deuda(bd) -> None:
    """Cuando la deuda queda pagada, el descuento sale del salario y del libre."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)
    deduccion = deducciones_fijas.crear_deduccion(
        bd, id_usuario, "Libranza", "0", 2, deuda.id_deuda
    )
    libre_con_deuda = _capacidad(bd, id_usuario).libre

    deuda_bd = bd.get(Deuda, deuda.id_deuda)
    deuda_bd.estado = deudas.ESTADO_PAGADA
    bd.commit()

    assert deduccion.id_deuda == deuda.id_deuda
    assert deducciones_fijas.listar_vigentes(bd, id_usuario) == []
    assert _capacidad(bd, id_usuario).libre == libre_con_deuda + Decimal("400000")


def test_la_proyeccion_retira_la_cuota_al_terminar(bd) -> None:
    """La proyección deja de cobrar la cuota cuando se cumplen las cuotas."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "800000", "400000", 2)
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Libranza", "0", 2, deuda.id_deuda)

    proyeccion = _capacidad(bd, id_usuario).proyeccion

    assert proyeccion[0]["deuda"] == Decimal("400000.00")
    assert proyeccion[-1]["deuda"] == Decimal("0.00")


def test_solo_se_vinculan_deudas_activas_y_propias(bd) -> None:
    """SRS v1.9, 3.2: se vinculan todas las activas (también quincenales)."""
    id_usuario = _id_admin(bd)
    quincenal = deudas.crear_deuda(
        bd, id_usuario, "Banco", "800000", "100000", 8,
        periodicidad=deudas.PERIODICIDAD_QUINCENAL
    )
    vinculada = deducciones_fijas.crear_deduccion(
        bd, id_usuario, "Libranza", "0", 1, quincenal.id_deuda
    )
    assert vinculada.id_deuda == quincenal.id_deuda

    mensual = deudas.crear_deuda(bd, id_usuario, "Banco", "800000", "400000", 2)
    bd.get(Deuda, mensual.id_deuda).estado = deudas.ESTADO_PAGADA
    bd.commit()
    with pytest.raises(ValueError, match="ya está pagada"):
        deducciones_fijas.crear_deduccion(bd, id_usuario, "Libranza", "0", 1, mensual.id_deuda)

    with pytest.raises(ValueError, match="no existe"):
        deducciones_fijas.crear_deduccion(bd, "otro-usuario", "Libranza", "0", 1, mensual.id_deuda)


def test_al_borrar_la_deuda_la_deduccion_queda_sin_vinculo(bd) -> None:
    """Borrar la deuda no borra el descuento: queda como deducción normal."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "800000", "400000", 2)
    deduccion = deducciones_fijas.crear_deduccion(
        bd, id_usuario, "Libranza", "0", 2, deuda.id_deuda
    )

    deudas.eliminar_deuda(bd, id_usuario, deuda.id_deuda)
    bd.refresh(deduccion)

    assert deduccion.id_deuda is None
    assert deduccion in deducciones_fijas.listar_vigentes(bd, id_usuario)


def test_la_vista_no_repite_los_detalles_del_credito_vinculado(
    cliente_admin: TestClient, bd
) -> None:
    """La fila solo muestra la deducción: el detalle de la deuda no desplaza los botones."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)
    deduccion = deducciones_fijas.crear_deduccion(
        bd, id_usuario, "Libranza BBVA", "0", 2, deuda.id_deuda
    )

    html = " ".join(cliente_admin.get("/presupuesto").text.split())

    assert "Libranza BBVA" in html
    assert f'data-id-deduccion="{deduccion.id_deduccion}"' in html
    assert "faltan 3 cuota(s)" not in html
    assert "Crédito con Banco" not in html


def test_formulario_vincula_la_deuda(cliente_admin: TestClient, bd) -> None:
    """El formulario guarda la deducción vinculada y toma la cuota de la deuda."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)

    respuesta = cliente_admin.post(
        "/presupuesto/deducciones",
        data={
            "descripcion": "Libranza",
            "valor": "1",
            "quincena": "2",
            "id_deuda": deuda.id_deuda,
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    creada = [d for d in deducciones_fijas.listar_deducciones(bd, id_usuario) if d.descripcion == "Libranza"]
    assert creada and creada[0].id_deuda == deuda.id_deuda
    assert creada[0].valor == Decimal("400000.00")
