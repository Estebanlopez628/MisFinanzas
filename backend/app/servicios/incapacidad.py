"""Incapacidades laborales y arrastre de saldos entre meses (Tarea 4).

Responsabilidad
---------------
Calcular el descuento que asume el trabajador durante una incapacidad de origen
común y repartir los días por mes calendario, generando el **saldo arrastrado**
(*rollover*) que se aplicará en el periodo siguiente.

Reglas de negocio (SRS y `MEMORY.md`):
- Días 1 y 2 de la incapacidad: pagados al 100% por el empleador → **sin descuento**.
- Del día 3 en adelante: cubiertos al 66.67% por la EPS → **descuento del 33.33%**
  sobre el valor del día.
- El valor del día se obtiene del sueldo básico mensual dividido entre 30.
- Si el rango de fechas cruza de mes, se liquida la parte del mes activo y el
  remanente se devuelve como `SaldoIncapacidad` para el mes siguiente.

Las funciones son puras: no persisten ni conocen HTTP. La persistencia de
`saldos_incapacidad` (ver `diccionario_datos.md`, §6) se realizará en la fase de
base de datos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.core.config import ParametrosNomina, obtener_parametros
from app.core.numeros import a_decimal, redondear_dinero, redondear_hora, sumar_dinero

# El mes laboral colombiano se liquida sobre 30 días para efectos de valor diario.
DIAS_BASE_MES = Decimal("30")
CERO = Decimal("0")
UN_DIA = timedelta(days=1)


@dataclass
class _AcumuladorMes:
    """Estructura interna y mutable para agrupar días por mes.

    Se usa solo durante el recorrido día por día; nunca se expone fuera del
    módulo. Al finalizar se convierte en `TramoMensual` (inmutable).

    Attributes:
        anio: Año del grupo.
        mes: Mes del grupo.
        inicio: Primer día del grupo.
        fin: Último día del grupo.
        dias: Días acumulados.
        dias_100: Días sin descuento.
        dias_66: Días con descuento.
        valor: Descuento acumulado sin redondear.
    """

    anio: int
    mes: int
    inicio: date
    fin: date
    dias: int = 0
    dias_100: int = 0
    dias_66: int = 0
    valor: Decimal = CERO


@dataclass(frozen=True)
class TramoMensual:
    """Porción de una incapacidad que cae dentro de un mes calendario.

    Attributes:
        anio: Año del tramo.
        mes: Mes del tramo (1–12).
        fecha_inicio: Primer día del tramo.
        fecha_fin: Último día del tramo.
        dias: Días calendario incluidos.
        dias_al_100: Días pagados íntegramente por el empleador.
        dias_al_66: Días cubiertos por la EPS al 66.67%.
        valor_descontado: Descuento al trabajador por este tramo.
    """

    anio: int
    mes: int
    fecha_inicio: date
    fecha_fin: date
    dias: int
    dias_al_100: int
    dias_al_66: int
    valor_descontado: Decimal


@dataclass(frozen=True)
class SaldoIncapacidad:
    """Saldo pendiente de una incapacidad para el periodo siguiente (rollover).

    Attributes:
        anio: Año del periodo destino.
        mes: Mes del periodo destino (1–12).
        dias_pendientes: Días por liquidar.
        valor_pendiente: Descuento ya calculado que se aplicará en el destino.
        fecha_inicio: Primer día pendiente.
        fecha_fin: Último día pendiente.
        dias_liquidados_previos: Días de la incapacidad ya liquidados antes de
            este saldo; permite auditar la continuidad del día 3.
    """

    anio: int
    mes: int
    dias_pendientes: int
    valor_pendiente: Decimal
    fecha_inicio: date
    fecha_fin: date
    dias_liquidados_previos: int


@dataclass(frozen=True)
class LiquidacionIncapacidad:
    """Resultado completo del cálculo de una incapacidad.

    Attributes:
        fecha_inicio: Inicio del rango registrado.
        fecha_fin: Fin del rango registrado (inclusive).
        dias_totales: Días calendario de la incapacidad.
        dias_al_100: Días pagados al 100% por el empleador.
        dias_al_66: Días cubiertos al 66.67% por la EPS.
        valor_dia: Sueldo básico dividido entre 30.
        valor_descontado: Descuento total al trabajador.
        tramos: Desglose por mes calendario, en orden cronológico.
    """

    fecha_inicio: date
    fecha_fin: date
    dias_totales: int
    dias_al_100: int
    dias_al_66: int
    valor_dia: Decimal
    valor_descontado: Decimal
    tramos: tuple[TramoMensual, ...]


@dataclass(frozen=True)
class ResultadoMesIncapacidad:
    """Liquidación de la porción de una incapacidad que corresponde a un mes.

    Attributes:
        anio: Año liquidado.
        mes: Mes liquidado (1–12).
        dias_liquidados: Días de la incapacidad dentro de ese mes.
        dias_al_100: Días sin descuento dentro del mes.
        dias_al_66: Días con descuento dentro del mes.
        valor_descontado: Descuento a aplicar en el periodo.
        dias_arrastrados: Días que quedan para meses posteriores.
        valor_arrastrado: Descuento correspondiente a los días arrastrados.
        saldos_pendientes: Saldos por mes destino, listos para persistir.
    """

    anio: int
    mes: int
    dias_liquidados: int
    dias_al_100: int
    dias_al_66: int
    valor_descontado: Decimal
    dias_arrastrados: int
    valor_arrastrado: Decimal
    saldos_pendientes: tuple[SaldoIncapacidad, ...]


def _validar_rango(fecha_inicio: date, fecha_fin: date) -> None:
    """Valida tipos y coherencia del rango de fechas.

    Args:
        fecha_inicio: Fecha inicial del rango.
        fecha_fin: Fecha final del rango.

    Raises:
        TypeError: Si alguna fecha no es un objeto `date`.
        ValueError: Si la fecha final es anterior a la inicial.
    """
    if not isinstance(fecha_inicio, date) or not isinstance(fecha_fin, date):
        raise TypeError("Las fechas de la incapacidad deben ser objetos 'date'.")
    if fecha_fin < fecha_inicio:
        raise ValueError(
            f"La fecha final ({fecha_fin.isoformat()}) no puede ser anterior a la "
            f"fecha inicial ({fecha_inicio.isoformat()})."
        )


def calcular_incapacidad(
    fecha_inicio: date,
    fecha_fin: date,
    sueldo_basico: Decimal | int | float | str,
    parametros: ParametrosNomina | None = None,
) -> LiquidacionIncapacidad:
    """Calcula el descuento total de una incapacidad y su reparto por mes.

    Recorre día por día el rango para asignar correctamente el pago del 100% en
    los primeros días y el descuento del 33.33% desde el día 3, incluso cuando
    la incapacidad cruza de mes o de año.

    Args:
        fecha_inicio: Primer día de la incapacidad.
        fecha_fin: Último día de la incapacidad (inclusive).
        sueldo_basico: Sueldo básico mensual del trabajador.
        parametros: Parámetros de nómina; si es `None` se usan los vigentes.

    Returns:
        `LiquidacionIncapacidad` con totales y tramos mensuales.

    Raises:
        TypeError: Si las fechas no son `date`.
        ValueError: Si el rango es incoherente o el sueldo es negativo.
    """
    _validar_rango(fecha_inicio, fecha_fin)

    parametros_efectivos = parametros if parametros is not None else obtener_parametros()
    sueldo = a_decimal(sueldo_basico, "sueldo básico")
    if sueldo < CERO:
        raise ValueError(f"El campo 'sueldo básico' no puede ser negativo; se recibió {sueldo}.")

    valor_dia = redondear_hora(sueldo / DIAS_BASE_MES)
    descuento_pct = parametros_efectivos.porcentaje_descuento_incapacidad
    dias_empleador = parametros_efectivos.dias_incapacidad_empleador

    # Acumulador por mes: la clave es (año, mes).
    acumulado: dict[tuple[int, int], _AcumuladorMes] = {}

    dia = fecha_inicio
    indice = 1
    while dia <= fecha_fin:
        clave = (dia.year, dia.month)
        grupo = acumulado.setdefault(
            clave,
            _AcumuladorMes(anio=dia.year, mes=dia.month, inicio=dia, fin=dia),
        )
        grupo.dias += 1

        if indice <= dias_empleador:
            # Primeros días: pago íntegro del empleador, sin descuento.
            grupo.dias_100 += 1
        else:
            # Desde el día 3: la EPS cubre el 66.67% y el trabajador asume el resto.
            grupo.valor += valor_dia * descuento_pct / Decimal("100")
            grupo.dias_66 += 1

        grupo.fin = dia
        dia += UN_DIA
        indice += 1

    tramos = [
        TramoMensual(
            anio=grupo.anio,
            mes=grupo.mes,
            fecha_inicio=grupo.inicio,
            fecha_fin=grupo.fin,
            dias=grupo.dias,
            dias_al_100=grupo.dias_100,
            dias_al_66=grupo.dias_66,
            valor_descontado=redondear_dinero(grupo.valor),
        )
        for _, grupo in sorted(acumulado.items())
    ]

    return LiquidacionIncapacidad(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        dias_totales=sum(tramo.dias for tramo in tramos),
        dias_al_100=sum(tramo.dias_al_100 for tramo in tramos),
        dias_al_66=sum(tramo.dias_al_66 for tramo in tramos),
        valor_dia=valor_dia,
        valor_descontado=sumar_dinero(*(tramo.valor_descontado for tramo in tramos)),
        tramos=tuple(tramos),
    )


def liquidar_mes_incapacidad(
    fecha_inicio: date,
    fecha_fin: date,
    sueldo_basico: Decimal | int | float | str,
    anio: int | None = None,
    mes: int | None = None,
    parametros: ParametrosNomina | None = None,
) -> ResultadoMesIncapacidad:
    """Liquida la parte de una incapacidad que corresponde a un mes concreto.

    Es la operación que usará la interfaz: el usuario registra el rango de fechas
    y el sistema descuenta solo los días del mes activo, dejando el remanente
    como saldo para el mes siguiente.

    Args:
        fecha_inicio: Primer día de la incapacidad.
        fecha_fin: Último día de la incapacidad (inclusive).
        sueldo_basico: Sueldo básico mensual del trabajador.
        anio: Año a liquidar. Si es `None`, se usa el de `fecha_inicio`.
        mes: Mes a liquidar (1–12). Si es `None`, se usa el de `fecha_inicio`.
        parametros: Parámetros de nómina; si es `None` se usan los vigentes.

    Returns:
        `ResultadoMesIncapacidad` con el descuento del mes y los saldos que se
        arrastran a los meses siguientes.

    Raises:
        TypeError: Si las fechas no son `date`.
        ValueError: Si el rango es incoherente, el mes está fuera de 1–12 o el
            sueldo es negativo.
    """
    liquidacion = calcular_incapacidad(fecha_inicio, fecha_fin, sueldo_basico, parametros)

    anio_destino = fecha_inicio.year if anio is None else anio
    mes_destino = fecha_inicio.month if mes is None else mes
    if not 1 <= mes_destino <= 12:
        raise ValueError(f"El mes debe estar entre 1 y 12; se recibió {mes_destino}.")

    clave_destino = (anio_destino, mes_destino)
    indice_actual = next(
        (
            posicion
            for posicion, tramo in enumerate(liquidacion.tramos)
            if (tramo.anio, tramo.mes) == clave_destino
        ),
        None,
    )

    if indice_actual is None:
        actual = None
        posteriores = [t for t in liquidacion.tramos if (t.anio, t.mes) > clave_destino]
        dias_previos = 0
    else:
        actual = liquidacion.tramos[indice_actual]
        posteriores = list(liquidacion.tramos[indice_actual + 1 :])
        dias_previos = sum(t.dias for t in liquidacion.tramos[: indice_actual + 1])

    saldos: list[SaldoIncapacidad] = []
    acumulado_previo = dias_previos
    for tramo in posteriores:
        saldos.append(
            SaldoIncapacidad(
                anio=tramo.anio,
                mes=tramo.mes,
                dias_pendientes=tramo.dias,
                valor_pendiente=tramo.valor_descontado,
                fecha_inicio=tramo.fecha_inicio,
                fecha_fin=tramo.fecha_fin,
                dias_liquidados_previos=acumulado_previo,
            )
        )
        acumulado_previo += tramo.dias

    return ResultadoMesIncapacidad(
        anio=anio_destino,
        mes=mes_destino,
        dias_liquidados=actual.dias if actual is not None else 0,
        dias_al_100=actual.dias_al_100 if actual is not None else 0,
        dias_al_66=actual.dias_al_66 if actual is not None else 0,
        valor_descontado=actual.valor_descontado if actual is not None else CERO,
        dias_arrastrados=sum(tramo.dias for tramo in posteriores),
        valor_arrastrado=sumar_dinero(*(tramo.valor_descontado for tramo in posteriores)),
        saldos_pendientes=tuple(saldos),
    )
