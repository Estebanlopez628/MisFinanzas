"""Pruebas de persistencia de periodos e historial (bloque A y SRS v1.5)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.modelos import PeriodoNomina, SaldoIncapacidad
from app.servicios import periodos, registro_incapacidades, usuarios
from app.servicios.incapacidad import liquidar_mes_incapacidad
from app.servicios.nomina import liquidar_periodo


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de la cuenta `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def _liquidacion():
    """Genera una liquidación simple con dos horas extra diurnas.

    Returns:
        Resultado de `liquidar_periodo` con sueldo de 3.000.000.
    """
    return liquidar_periodo(
        sueldo_basico=Decimal("3000000"),
        horas_por_tipo={"EXTRA_DIURNA_NORMAL": Decimal("2")},
        aplicar_auxilio_legal=True,
    )


def test_guardar_periodo_persiste_totales_y_detalle(bd) -> None:
    """El encabezado y el detalle de horas quedan guardados."""
    id_usuario = _id_admin(bd)
    periodo = periodos.guardar_liquidacion(
        bd,
        id_usuario,
        2026,
        11,
        0,
        _liquidacion(),
        {"EXTRA_DIURNA_NORMAL": Decimal("2")},
        total_gastos=Decimal("150000"),
    )

    assert periodo.total_devengado > Decimal("3000000")
    assert periodo.total_gastos == Decimal("150000.00")
    assert periodos.horas_del_periodo(bd, periodo.id_periodo) == {
        "EXTRA_DIURNA_NORMAL": Decimal("2.00")
    }


def test_guardar_dos_veces_actualiza_el_mismo_periodo(bd) -> None:
    """Recalcular no debe duplicar filas del periodo."""
    id_usuario = _id_admin(bd)
    periodos.guardar_liquidacion(bd, id_usuario, 2026, 11, 0, _liquidacion(), {})
    periodos.guardar_liquidacion(bd, id_usuario, 2026, 11, 0, _liquidacion(), {})

    total = bd.scalar(
        select(func.count())
        .select_from(PeriodoNomina)
        .where(PeriodoNomina.id_usuario == id_usuario)
    )
    assert total == 1


def test_historial_ordena_del_mas_reciente_al_mas_antiguo(bd) -> None:
    """La lista se ordena por año, mes y quincena descendente."""
    id_usuario = _id_admin(bd)
    periodos.guardar_liquidacion(bd, id_usuario, 2026, 1, 0, _liquidacion(), {})
    periodos.guardar_liquidacion(bd, id_usuario, 2026, 12, 0, _liquidacion(), {})

    lista = periodos.listar_periodos(bd, id_usuario)
    assert [periodo.mes for periodo in lista] == [12, 1]


def test_incapacidad_que_cruza_de_mes_se_reparte_por_tramo(bd) -> None:
    """Cada mes recibe solo sus días; no se generan saldos pendientes."""
    id_usuario = _id_admin(bd)
    registro_incapacidades.registrar_incapacidad(
        bd,
        id_usuario,
        date(2026, 11, 28),
        date(2026, 12, 3),
        Decimal("2960000"),
    )

    tramos_noviembre = registro_incapacidades.tramos_del_mes(
        bd, id_usuario, 2026, 11, Decimal("2960000")
    )
    tramos_diciembre = registro_incapacidades.tramos_del_mes(
        bd, id_usuario, 2026, 12, Decimal("2960000")
    )

    assert [tramo.dias for tramo in tramos_noviembre] == [3]
    assert [tramo.dias for tramo in tramos_diciembre] == [3]
    # Noviembre aporta los dos días al 100 % y uno al 66,67 %; diciembre, tres.
    assert tramos_noviembre[0].dias_al_66 == 1
    assert tramos_diciembre[0].dias_al_66 == 3

    # SRS v1.5: el rollover desapareció; no se crean filas de saldo.
    assert list(bd.scalars(select(SaldoIncapacidad))) == []


def test_descuento_del_mes_sale_del_tramo_registrado(bd) -> None:
    """Diciembre descuenta su tramo desde las fechas, sin saldo almacenado."""
    id_usuario = _id_admin(bd)
    registro_incapacidades.registrar_incapacidad(
        bd,
        id_usuario,
        date(2026, 11, 28),
        date(2026, 12, 3),
        Decimal("2960000"),
    )

    descuento = registro_incapacidades.descuento_del_mes(
        bd, id_usuario, 2026, 12, Decimal("2960000")
    )
    esperado = liquidar_mes_incapacidad(
        date(2026, 11, 28), date(2026, 12, 3), Decimal("2960000"), anio=2026, mes=12
    ).valor_descontado

    assert descuento == esperado
    assert descuento > Decimal("0")


def test_eliminar_periodo_ajeno_no_hace_nada(bd) -> None:
    """Un usuario no puede borrar el periodo de otro."""
    id_admin = _id_admin(bd)
    periodo = periodos.guardar_liquidacion(bd, id_admin, 2026, 5, 0, _liquidacion(), {})

    assert periodos.eliminar_periodo(bd, "otro-usuario", periodo.id_periodo) is False
    assert bd.get(PeriodoNomina, periodo.id_periodo) is not None


def test_historial_muestra_tabla_cronologica(cliente_admin, bd) -> None:
    """La vista del historial lista fecha, sueldo, extras, deducciones y saldo."""
    periodos.guardar_liquidacion(
        bd,
        _id_admin(bd),
        2026,
        11,
        0,
        _liquidacion(),
        {"EXTRA_DIURNA_NORMAL": Decimal("2")},
        total_gastos=Decimal("150000"),
    )

    respuesta = cliente_admin.get("/finanzas/historial")
    texto = re.sub(r"\s+", " ", respuesta.text)

    assert respuesta.status_code == 200
    assert "Historial de Registros" in texto
    for columna in (
        "Fecha de guardado",
        "Sueldo base",
        "Total extras",
        "Total deducciones",
        "Gastos quincenales",
        "Saldo neto final",
    ):
        assert columna in texto
    assert "noviembre de 2026" in texto
    assert "Primer registro" in texto
