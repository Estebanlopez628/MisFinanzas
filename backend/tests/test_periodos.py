"""Pruebas de persistencia de periodos, historial y rollover (bloque A)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.modelos import PeriodoNomina, SaldoIncapacidad
from app.servicios import periodos, registro_incapacidades, usuarios
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


def test_incapacidad_que_cruza_de_mes_genera_rollover(bd) -> None:
    """La parte de diciembre queda pendiente y se ofrece en el resumen."""
    id_usuario = _id_admin(bd)
    registro_incapacidades.registrar_incapacidad(
        bd,
        id_usuario,
        date(2026, 11, 28),
        date(2026, 12, 3),
        Decimal("2960000"),
    )

    resumen = periodos.resumen_rollover(bd, id_usuario, 2026, 12)
    assert resumen.hay_saldo is True
    assert resumen.dias > 0
    assert resumen.valor > Decimal("0")


def test_aplicar_rollover_marca_el_saldo_y_eliminar_lo_libera(bd) -> None:
    """Guardar el periodo aplica el saldo; eliminarlo lo deja pendiente otra vez."""
    id_usuario = _id_admin(bd)
    registro_incapacidades.registrar_incapacidad(
        bd,
        id_usuario,
        date(2026, 11, 28),
        date(2026, 12, 3),
        Decimal("2960000"),
    )
    resumen = periodos.resumen_rollover(bd, id_usuario, 2026, 12)
    assert resumen.hay_saldo

    periodo = periodos.guardar_liquidacion(
        bd,
        id_usuario,
        2026,
        12,
        0,
        liquidar_periodo(Decimal("2960000"), deduccion_incapacidad=resumen.valor),
        {},
        ids_saldos=resumen.ids,
    )
    saldos = list(
        bd.scalars(
            select(SaldoIncapacidad).where(
                SaldoIncapacidad.id_periodo_aplicado == periodo.id_periodo
            )
        )
    )
    assert saldos and all(saldo.aplicado for saldo in saldos)

    assert periodos.eliminar_periodo(bd, id_usuario, periodo.id_periodo) is True
    bd.expire_all()
    liberados = list(bd.scalars(select(SaldoIncapacidad)))
    assert liberados and all(not saldo.aplicado for saldo in liberados)


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
