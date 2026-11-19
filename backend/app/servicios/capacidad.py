"""Capacidad de endeudamiento y proyección a doce meses (SRS v1.7, bloque F).

Responsabilidad
---------------
- Repartir el ingreso del mes entre gastos fijos, cuota de deudas y dinero libre,
  para dibujar una dona con semáforo de endeudamiento.
- Listar las deudas que están a punto de terminar (tres cuotas o menos).
- Proyectar doce meses de cuota y saldo libre, teniendo en cuenta que cada deuda
  deja de pesarlo cuando se termina.

Reglas:
- El ingreso base son los pagos del mes (`quincenas.resumen_quincenas`) más el
  neto cobrado de trabajos extras, igual que el diagnóstico de presupuesto.
- Los gastos fijos incluyen gastos, deducciones de ley y deducciones fijas del
  salario; las cuotas de deuda se muestran aparte para que se vea su peso.
- El semáforo mira el porcentaje de la cuota de deuda sobre el ingreso: hasta
  20 % verde, hasta 35 % ámbar y por encima rojo.
- La proyección supone el mismo ingreso y los mismos gastos fijos: solo cambia la
  cuota de deuda al terminar cada obligación. Es una estimación, no un cierre.

Este módulo no escribe en la base de datos: solo lee y calcula.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.modelos import Deuda, PerfilFinanciero
from app.servicios import deudas as servicio_deudas
from app.servicios import quincenas as servicio_quincenas
from app.servicios import trabajos as servicio_trabajos

CERO = Decimal("0")
CIEN = Decimal("100")
MESES_PROYECCION = 12
CUOTAS_POR_TERMINAR = 3

# Umbrales del semáforo, en porcentaje del ingreso mensual.
UMBRAL_VERDE = Decimal("20")
UMBRAL_AMBAR = Decimal("35")

ESTADO_VERDE = "verde"
ESTADO_AMBAR = "ambar"
ESTADO_ROJO = "rojo"
ESTADO_SIN_DATOS = "sin-datos"

MESES_CORTOS = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


@dataclass(frozen=True)
class Capacidad:
    """Reparto del ingreso del mes y su proyección a doce meses.

    Attributes:
        ingreso: Ingreso mensual consolidado (sueldo del mes + extras cobrados).
        gastos: Gastos fijos, deducciones de ley y deducciones fijas del salario.
        deudas: Cuota mensual equivalente de las deudas activas.
        libre: Dinero que queda después de gastos y deudas; puede ser negativo.
        porcentaje_gastos: Peso de los gastos fijos sobre el ingreso.
        porcentaje_deudas: Peso real de las deudas sobre el ingreso (semáforo).
        porcentaje_libre: Porcentaje que queda libre sobre el ingreso.
        semaforo: `verde`, `ambar`, `rojo` o `sin-datos`.
        mensaje: Explicación del semáforo en lenguaje natural.
        arcos: Segmentos de la dona, normalizados para que sumen 100.
        por_terminar: Deudas con tres cuotas o menos por pagar.
        proyeccion: Doce meses de cuota y saldo libre estimados.
    """

    ingreso: Decimal
    gastos: Decimal
    deudas: Decimal
    libre: Decimal
    porcentaje_gastos: Decimal
    porcentaje_deudas: Decimal
    porcentaje_libre: Decimal
    semaforo: str
    mensaje: str
    arcos: list[dict[str, object]] = field(default_factory=list)
    por_terminar: list[dict[str, object]] = field(default_factory=list)
    proyeccion: list[dict[str, object]] = field(default_factory=list)


def _porcentaje(valor: Decimal, total: Decimal) -> Decimal:
    """Calcula el porcentaje de un valor sobre un total, sin superar cero.

    Args:
        valor: Monto a expresar.
        total: Base de comparación.

    Returns:
        Porcentaje redondeado a un decimal; cero si el total no es positivo.
    """
    if total <= CERO:
        return CERO
    return redondear_dinero(max(valor, CERO) / total * CIEN)


def _repartir_arcos(
    gastos: Decimal,
    deudas: Decimal,
    libre: Decimal,
    ingreso: Decimal,
) -> list[dict[str, object]]:
    """Construye los tres arcos de la dona de capacidad.

    Cuando gastos y deudas superan el ingreso, el dibujo se escala de forma
    proporcional para que la circunferencia cierre y el segmento libre quede en
    cero; así el gráfico no muestra arcos mayores que la vuelta completa.

    Args:
        gastos: Gastos fijos del mes.
        deudas: Cuota mensual de deudas.
        libre: Dinero restante (puede ser negativo).
        ingreso: Ingreso mensual consolidado.

    Returns:
        Lista de diccionarios con etiqueta, valor, porcentaje, longitud,
        desplazamiento y color para el SVG.
    """
    if ingreso <= CERO:
        return []

    porcentaje_gastos = _porcentaje(gastos, ingreso)
    porcentaje_deudas = _porcentaje(deudas, ingreso)
    # `_porcentaje` devuelve cero con montos negativos: un saldo libre negativo
    # no dibuja arco, pero se conserva en `libre` para el texto de alerta.
    porcentaje_libre = _porcentaje(libre, ingreso)

    if porcentaje_gastos + porcentaje_deudas + porcentaje_libre > CIEN:
        # El ingreso no alcanza: se reparte la vuelta completa entre gastos y
        # deudas sin dibujar un segmento libre que no existe.
        total_comprometido = porcentaje_gastos + porcentaje_deudas
        if total_comprometido > CERO:
            porcentaje_gastos = porcentaje_gastos / total_comprometido * CIEN
            porcentaje_deudas = CIEN - porcentaje_gastos
        else:
            porcentaje_gastos = CERO
            porcentaje_deudas = CERO
        porcentaje_libre = CERO

    arcos: list[dict[str, object]] = []
    avance = CERO
    for etiqueta, valor, porcentaje, color in (
        ("Gastos fijos", gastos, porcentaje_gastos, "var(--accent-blue)"),
        ("Cuota de deudas", deudas, porcentaje_deudas, "var(--accent-red)"),
        ("Libre", max(libre, CERO), porcentaje_libre, "var(--accent-green)"),
    ):
        if porcentaje <= CERO:
            continue
        longitud = redondear_dinero(porcentaje)
        arcos.append(
            {
                "etiqueta": etiqueta,
                "valor": redondear_dinero(valor),
                "porcentaje": (porcentaje.quantize(Decimal("0.1"))),
                "longitud": longitud,
                "desplazamiento": redondear_dinero(-avance),
                "color": color,
            }
        )
        avance += porcentaje
    return arcos


def _meses_equivalentes(deuda: Deuda) -> int:
    """Traduce las cuotas pendientes a meses de pago.

    Una deuda quincenal paga dos cuotas por mes; la última fracción cuenta como
    un mes completo porque la cuota todavía pesa en el presupuesto.

    Args:
        deuda: Deuda activa.

    Returns:
        Número de meses en los que la deuda seguirá descontándose.
    """
    cuotas = max(deuda.cuotas_pendientes, 0)
    if cuotas <= 0:
        return 0
    if deuda.periodicidad == servicio_deudas.PERIODICIDAD_QUINCENAL:
        return int(math.ceil(cuotas / 2))
    return cuotas


def _etiqueta_mes(anio: int, mes: int) -> str:
    """Devuelve el rótulo corto de un mes.

    Args:
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Texto tipo «ene 2027».
    """
    return f"{MESES_CORTOS[mes - 1]} {anio}"


def _mover_mes(anio: int, mes: int, avance: int) -> tuple[int, int]:
    """Desplaza un mes un número de posiciones.

    Args:
        anio: Año de partida.
        mes: Mes de partida (1–12).
        avance: Meses a sumar.

    Returns:
        Tupla `(anio, mes)` resultante.
    """
    total = (anio * 12) + (mes - 1) + avance
    return total // 12, (total % 12) + 1


def meses_siguientes(
    anio: int, mes: int, cantidad: int = MESES_PROYECCION
) -> list[tuple[int, int, str]]:
    """Lista los próximos meses con su rótulo corto.

    Args:
        anio: Año de partida.
        mes: Mes de partida (1–12).
        cantidad: Número de meses a devolver.

    Returns:
        Lista de tuplas `(anio, mes, etiqueta)` desde el mes de partida.
    """
    return [
        (a, m, _etiqueta_mes(a, m))
        for a, m in (_mover_mes(anio, mes, avance) for avance in range(cantidad))
    ]


def deudas_por_terminar(
    bd: Session,
    id_usuario: str,
    maximo: int = CUOTAS_POR_TERMINAR,
) -> list[dict[str, object]]:
    """Lista las deudas activas con pocas cuotas pendientes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.
        maximo: Número máximo de cuotas para considerar que está por terminar.

    Returns:
        Lista de diccionarios ordenada por cuotas restantes y fecha estimada de
        la última cuota. Las deudas ya pagadas no aparecen.
    """
    pagos_por_deuda = servicio_deudas.listar_pagos(bd, id_usuario)
    filas: list[dict[str, object]] = []
    for deuda in servicio_deudas.listar_deudas(bd, id_usuario):
        if deuda.estado != servicio_deudas.ESTADO_ACTIVA:
            continue
        if deuda.cuotas_pendientes <= 0 or deuda.cuotas_pendientes > maximo:
            continue
        pagos = pagos_por_deuda.get(deuda.id_deuda, [])
        desde = pagos[-1].fecha_aplicacion if pagos else None
        cuotas = servicio_deudas.proyeccion_deuda(deuda, desde)
        fecha_fin = cuotas[-1].fecha if cuotas else None
        filas.append(
            {
                "acreedor": deuda.acreedor,
                "descripcion": deuda.descripcion or "",
                "saldo": redondear_dinero(deuda.saldo_total),
                "cuota": servicio_deudas.cuota_mensual_equivalente(deuda),
                "cuotas_pendientes": deuda.cuotas_pendientes,
                "periodicidad": deuda.periodicidad,
                "fecha_fin": fecha_fin,
            }
        )
    filas.sort(
        key=lambda fila: (
            fila["cuotas_pendientes"],
            fila["fecha_fin"] or date.max,
        )
    )
    return filas


def proyeccion_capacidad(
    ingreso: Decimal,
    gastos: Decimal,
    deudas: list[Deuda],
    hoy: date | None = None,
) -> list[dict[str, object]]:
    """Estima doce meses de cuota de deuda y saldo libre.

    Args:
        ingreso: Ingreso mensual consolidado que se mantiene constante.
        gastos: Gastos fijos mensuales que se mantienen constantes.
        deudas: Deudas activas del usuario.
        hoy: Mes de partida; por defecto, el mes actual.

    Returns:
        Lista de doce diccionarios con etiqueta, cuota, libre, porcentaje de
        deuda y la lista de deudas que terminan ese mes.
    """
    referencia = hoy or date.today()
    activas = [
        (deuda, _meses_equivalentes(deuda), servicio_deudas.cuota_mensual_equivalente(deuda))
        for deuda in deudas
        if deuda.estado == servicio_deudas.ESTADO_ACTIVA and deuda.cuotas_pendientes > 0
    ]

    filas: list[dict[str, object]] = []
    for avance, (_anio, _mes, etiqueta) in enumerate(
        meses_siguientes(referencia.year, referencia.month)
    ):
        cuota = redondear_dinero(
            sum(
                (
                    valor
                    for _deuda, meses, valor in activas
                    if meses > avance
                ),
                start=CERO,
            )
        )
        libre = redondear_dinero(ingreso - gastos - cuota)
        porcentaje_deuda = _porcentaje(cuota, ingreso)
        filas.append(
            {
                "etiqueta": etiqueta,
                "deuda": cuota,
                "libre": libre,
                "porcentaje_deuda": porcentaje_deuda,
                "porcentaje_libre": _porcentaje(libre, ingreso),
                "terminan": [
                    deuda.acreedor
                    for deuda, meses, _valor in activas
                    if meses == avance + 1
                ],
            }
        )
    return filas


def _mensaje_semaforo(estado: str, porcentaje_deudas: Decimal) -> str:
    """Redacta la explicación del semáforo de endeudamiento.

    Args:
        estado: Resultado del semáforo.
        porcentaje_deudas: Peso real de las deudas sobre el ingreso.

    Returns:
        Texto listo para la interfaz.
    """
    if estado == ESTADO_VERDE:
        return (
            f"Tus deudas consumen el {porcentaje_deudas} % del ingreso; hay margen "
            "para asumir una cuota nueva con cuidado."
        )
    if estado == ESTADO_AMBAR:
        return (
            f"Tus deudas consumen el {porcentaje_deudas} % del ingreso; evita "
            "adquirir obligaciones nuevas hasta bajarlas."
        )
    if estado == ESTADO_ROJO:
        return (
            f"Tus deudas consumen el {porcentaje_deudas} % del ingreso; prioriza "
            "pagarlas antes de proyectar gastos nuevos."
        )
    return (
        "Completa tu perfil financiero para calcular cuánto de tu ingreso está "
        "comprometido."
    )


def capacidad_endeudamiento(
    bd: Session,
    id_usuario: str,
    perfil: PerfilFinanciero | None,
    anio: int,
    mes: int,
    hoy: date | None = None,
) -> Capacidad:
    """Calcula la capacidad de endeudamiento del mes y su proyección.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos, deudas y trabajos.
        perfil: Perfil financiero del usuario.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).
        hoy: Fecha de referencia para la proyección; por defecto, hoy.

    Returns:
        Un `Capacidad` con el reparto del ingreso, el semáforo, las deudas por
        terminar y la proyección a doce meses.
    """
    resumen = servicio_quincenas.resumen_quincenas(bd, id_usuario, perfil, anio, mes)
    ingreso_base = redondear_dinero(sum((fila.ingreso for fila in resumen), start=CERO))
    extras = servicio_trabajos.extras_cobrados_mes(bd, id_usuario, anio, mes)
    ingreso = redondear_dinero(ingreso_base + extras)

    gastos = redondear_dinero(
        sum(
            (fila.gastos + fila.deducciones + fila.deducciones_fijas for fila in resumen),
            start=CERO,
        )
    )
    deudas = list(servicio_deudas.listar_deudas(bd, id_usuario))
    cuota_deudas = redondear_dinero(
        servicio_deudas.resumen_deudas(bd, id_usuario)["cuota_mensual"]
    )
    libre = redondear_dinero(ingreso - gastos - cuota_deudas)

    if ingreso <= CERO:
        estado = ESTADO_SIN_DATOS
        porcentaje_deudas = CERO
    else:
        porcentaje_deudas = redondear_dinero(cuota_deudas / ingreso * CIEN)
        if porcentaje_deudas <= UMBRAL_VERDE:
            estado = ESTADO_VERDE
        elif porcentaje_deudas <= UMBRAL_AMBAR:
            estado = ESTADO_AMBAR
        else:
            estado = ESTADO_ROJO

    return Capacidad(
        ingreso=ingreso,
        gastos=gastos,
        deudas=cuota_deudas,
        libre=libre,
        porcentaje_gastos=_porcentaje(gastos, ingreso),
        porcentaje_deudas=porcentaje_deudas,
        porcentaje_libre=_porcentaje(libre, ingreso),
        semaforo=estado,
        mensaje=_mensaje_semaforo(estado, porcentaje_deudas),
        arcos=_repartir_arcos(gastos, cuota_deudas, libre, ingreso),
        por_terminar=deudas_por_terminar(bd, id_usuario),
        proyeccion=proyeccion_capacidad(ingreso, gastos, deudas, hoy),
    )
