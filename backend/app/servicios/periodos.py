"""Persistencia y consulta de periodos de nómina.

Responsabilidad
---------------
- Guardar (o actualizar) una liquidación en `periodos_nomina` y su detalle de
  recargos en `registros_horas_extra`.
- Consultar el historial y los periodos puntuales.
- Eliminar periodos del historial.

SRS v1.5: el rollover de incapacidades se retiró. El descuento de cada mes sale
de su propio tramo calendario, que se recalcula desde las fechas registradas
(`servicios/registro_incapacidades`). Por eso este módulo ya no marca saldos.

Toda la aritmética llega ya resuelta desde `servicios/nomina`; aquí solo se
traduce a filas y se conservan las invariantes del diccionario.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modelos import (
    PeriodoNomina,
    RegistroHorasExtra,
)
from app.servicios.nomina import LiquidacionNomina

CERO = Decimal("0")


def obtener_periodo(
    bd: Session, id_usuario: str, anio: int, mes: int, quincena: int
) -> PeriodoNomina | None:
    """Busca el periodo exacto de un usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del periodo.
        anio: Año del periodo.
        mes: Mes (1–12).
        quincena: `0` mensual, `1` o `2` quincenal.

    Returns:
        El periodo guardado o `None`.
    """
    return bd.scalar(
        select(PeriodoNomina).where(
            PeriodoNomina.id_usuario == id_usuario,
            PeriodoNomina.anio == anio,
            PeriodoNomina.mes == mes,
            PeriodoNomina.quincena == quincena,
        )
    )


def listar_periodos(bd: Session, id_usuario: str) -> list[PeriodoNomina]:
    """Devuelve el historial de liquidaciones, de la más reciente a la más antigua.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los periodos.

    Returns:
        Lista de periodos ordenada por año, mes y quincena descendente.
    """
    consulta = (
        select(PeriodoNomina)
        .where(PeriodoNomina.id_usuario == id_usuario)
        .order_by(
            PeriodoNomina.anio.desc(),
            PeriodoNomina.mes.desc(),
            PeriodoNomina.quincena.desc(),
        )
    )
    return list(bd.scalars(consulta))


def horas_del_periodo(bd: Session, id_periodo: str) -> dict[str, Decimal]:
    """Recupera las horas registradas por tipo en un periodo guardado.

    Args:
        bd: Sesión de base de datos.
        id_periodo: Periodo consultado.

    Returns:
        Diccionario ``tipo_hora → horas``; vacío si no hay detalle.
    """
    registros = bd.scalars(
        select(RegistroHorasExtra).where(RegistroHorasExtra.id_periodo == id_periodo)
    )
    return {registro.tipo_hora: registro.cantidad_horas for registro in registros}


def guardar_liquidacion(
    bd: Session,
    id_usuario: str,
    anio: int,
    mes: int,
    quincena: int,
    liquidacion: LiquidacionNomina,
    horas_por_tipo: dict[str, Decimal],
    total_gastos: Decimal = CERO,
) -> PeriodoNomina:
    """Guarda o actualiza la liquidación de un periodo.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del periodo.
        anio: Año del periodo.
        mes: Mes (1–12).
        quincena: `0` mensual, `1` o `2` quincenal.
        liquidacion: Resultado del motor de nómina.
        horas_por_tipo: Horas registradas por tipo (para el detalle).
        total_gastos: Gastos del mes que se dejan registrados junto al periodo.

    Returns:
        El periodo persistido.

    Raises:
        ValueError: Si el mes o la quincena están fuera de rango.
    """
    if not 1 <= mes <= 12:
        raise ValueError("El mes debe estar entre 1 y 12.")
    if quincena not in (0, 1, 2):
        raise ValueError("La quincena debe ser 0 (mensual), 1 o 2.")

    periodo = obtener_periodo(bd, id_usuario, anio, mes, quincena)
    if periodo is None:
        periodo = PeriodoNomina(id_usuario=id_usuario, anio=anio, mes=mes, quincena=quincena)
        bd.add(periodo)

    periodo.sueldo_basico_periodo = liquidacion.sueldo_basico
    periodo.valor_hora_ordinaria = liquidacion.valor_hora_ordinaria
    periodo.total_horas_extra = liquidacion.total_horas_extra
    periodo.total_recargos = liquidacion.total_recargos
    periodo.deduccion_salud = liquidacion.deducciones_ley.salud
    periodo.deduccion_pension = liquidacion.deducciones_ley.pension
    periodo.auxilio_transporte = liquidacion.auxilio_transporte
    periodo.deduccion_incapacidad = liquidacion.deduccion_incapacidad
    periodo.total_gastos = total_gastos
    periodo.total_devengado = liquidacion.total_devengado
    periodo.total_deducciones = liquidacion.total_deducciones
    periodo.saldo_bolsillo = liquidacion.saldo_bolsillo
    periodo.estado = "CALCULADO"
    bd.flush()

    # El detalle se reemplaza para que recalcular no duplique filas.
    bd.execute(
        delete(RegistroHorasExtra).where(
            RegistroHorasExtra.id_periodo == periodo.id_periodo
        )
    )
    for item in liquidacion.detalle_recargos:
        bd.add(
            RegistroHorasExtra(
                id_periodo=periodo.id_periodo,
                tipo_hora=item.tipo_hora,
                cantidad_horas=horas_por_tipo.get(item.tipo_hora, item.cantidad_horas),
                factor_aplicado=item.factor,
                valor_hora_base=item.valor_hora,
                valor_total=item.valor_total,
            )
        )

    bd.commit()
    bd.refresh(periodo)
    return periodo


def eliminar_periodo(bd: Session, id_usuario: str, id_periodo: str) -> bool:
    """Elimina un periodo del historial.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del periodo (evita borrar datos ajenos).
        id_periodo: Periodo a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    periodo = bd.get(PeriodoNomina, id_periodo)
    if periodo is None or periodo.id_usuario != id_usuario:
        return False

    bd.delete(periodo)
    bd.commit()
    return True
