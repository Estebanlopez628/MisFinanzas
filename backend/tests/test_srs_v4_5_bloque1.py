"""Pruebas de la SRS v4.5, bloque 1 (dona global por categoría y origen)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core import categorias as catalogo
from app.servicios import (
    ahorro,
    capacidad,
    deducciones_fijas,
    perfiles,
    trabajos,
    usuarios,
)

HOY = date.today()
CERO = Decimal("0")


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


def _perfil(bd, id_usuario: str):
    """Obtiene el perfil financiero del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil.

    Returns:
        Perfil financiero.
    """
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    assert perfil is not None
    return perfil


def _crear_extras(bd, id_usuario: str, valor: str = "1.000.000") -> None:
    """Crea un trabajo extra con sus pagos del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del trabajo.
        valor: Valor del pago.
    """
    trabajo = trabajos.crear_trabajo(bd, id_usuario, "Diseño", valor, HOY)
    trabajos.asegurar_pagos_trabajos(bd, id_usuario, HOY.year, HOY.month)
    assert trabajo is not None


def test_base_global_suma_ingresos_brutos_de_extras(bd) -> None:
    """La base de la dona global es sueldo más ingresos brutos de extras."""
    id_usuario = _id_admin(bd)
    perfil = _perfil(bd, id_usuario)
    _crear_extras(bd, id_usuario)
    trabajo = trabajos.listar_trabajos(bd, id_usuario)[0]
    trabajos.crear_gasto_trabajo(
        bd, id_usuario, trabajo.id_trabajo, "Otros Gastos Fijos", "Gasto", "200.000"
    )

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, perfil, HOY.year, HOY.month
    )

    ingresos_extras = sum(
        (bloque["ingreso"] for bloque in trabajos.pagos_del_mes(bd, id_usuario, HOY.year, HOY.month)),
        CERO,
    )
    # SRS v4.8: el sueldo percibido ya incorpora el auxilio legal.
    assert resultado.base_global == redondear(
        perfil.sueldo_basico + Decimal("249095") + ingresos_extras
    )
    assert resultado.base_global > resultado.ingreso  # antes se usaba el neto


def redondear(valor: Decimal) -> Decimal:
    """Redondea a centavos para comparar importes.

    Args:
        valor: Importe a redondear.

    Returns:
        Importe con dos decimales.
    """
    return valor.quantize(Decimal("0.01"))


def test_categorias_consolidadas_y_total_libre_unico(bd) -> None:
    """Las categorías homólogas suman y el libre se dibuja una sola vez."""
    id_usuario = _id_admin(bd)
    perfil = _perfil(bd, id_usuario)
    _crear_extras(bd, id_usuario)
    trabajo = trabajos.listar_trabajos(bd, id_usuario)[0]
    trabajos.crear_gasto_trabajo(
        bd, id_usuario, trabajo.id_trabajo, "Créditos y Obligaciones", "Cuota", "150.000"
    )

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, perfil, HOY.year, HOY.month
    )

    etiquetas = [arco["etiqueta"] for arco in resultado.arcos_categoria]
    assert etiquetas.count("Total libre") == 1
    assert "Base mínima de liquidez" not in etiquetas
    assert "Disponible para abonar" not in etiquetas
    assert etiquetas.count(catalogo.CATEGORIA_CREDITOS) == 1

    # La suma de categorías más el libre cierra la base global al 100 %.
    suma = sum((fila["valor"] for fila in resultado.categorias_globales), CERO) + resultado.libre
    assert suma == resultado.base_global
    assert sum((arco["porcentaje"] for arco in resultado.arcos_categoria), CERO) == Decimal("100.0")


def test_desglose_por_origen_en_arcos(bd) -> None:
    """La leyenda recibe el desglose apilado de cada categoría compartida."""
    id_usuario = _id_admin(bd)
    perfil = _perfil(bd, id_usuario)
    _crear_extras(bd, id_usuario)
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Crédito libranza", "100.000", 1)
    trabajo = trabajos.listar_trabajos(bd, id_usuario)[0]
    trabajos.crear_gasto_trabajo(
        bd, id_usuario, trabajo.id_trabajo, "Créditos y Obligaciones", "Cuota", "150.000"
    )

    resultado = capacidad.capacidad_endeudamiento(
        bd, id_usuario, perfil, HOY.year, HOY.month
    )
    por_etiqueta = {arco["etiqueta"]: arco for arco in resultado.arcos_categoria}

    creditos = por_etiqueta[catalogo.CATEGORIA_CREDITOS]["desglose"]
    assert {parte["origen"] for parte in creditos} == {"Mis Finanzas", "Trabajos Extras"}
    diferencia = abs(
        sum((parte["porcentaje"] for parte in creditos), CERO)
        - por_etiqueta[catalogo.CATEGORIA_CREDITOS]["porcentaje"]
    )
    assert diferencia <= Decimal("0.1")  # redondeo a un decimal del arco

    libre = por_etiqueta["Total libre"]["desglose"]
    assert [parte["origen"] for parte in libre] == ["Mis Finanzas", "Trabajos Extras"]
    assert sum((parte["valor"] for parte in libre), CERO) == resultado.libre


def test_leyenda_muestra_subitems_apilados(cliente_admin: TestClient, bd) -> None:
    """El HTML pinta los sub-ítems con sangría bajo cada categoría."""
    id_usuario = _id_admin(bd)
    perfil = _perfil(bd, id_usuario)
    _crear_extras(bd, id_usuario)

    html = cliente_admin.get("/presupuesto").text
    assert "dona__desglose" in html
    assert "↳ Mis Finanzas:" in html
    assert "↳ Trabajos Extras:" in html
    assert "Ingreso global del mes:" in html
    assert "Libre de tu salario:" not in html


def test_dona_individual_de_extras_permanece_intacta(bd) -> None:
    """La dona de Trabajos Extras no adopta la tajada global."""
    id_usuario = _id_admin(bd)
    _crear_extras(bd, id_usuario)

    resultado = capacidad.capacidad_trabajos(bd, id_usuario, HOY.year, HOY.month)

    etiquetas = [arco["etiqueta"] for arco in resultado.arcos_categoria]
    assert "Total libre" not in etiquetas
    assert any(etiqueta.startswith("Disponible") for etiqueta in etiquetas)
    assert resultado.base_global == CERO


def test_consejero_sigue_usando_el_libre_consolidado(bd) -> None:
    """El Consejero no cambia: recibe el mismo libre que la dona global."""
    id_usuario = _id_admin(bd)
    perfil = _perfil(bd, id_usuario)
    _crear_extras(bd, id_usuario)

    capacidad_global = capacidad.capacidad_endeudamiento(
        bd, id_usuario, perfil, HOY.year, HOY.month
    )
    diagnostico = ahorro.diagnostico(bd, id_usuario, perfil, HOY.year, HOY.month)

    assert diagnostico["disponible"] == capacidad_global.libre
