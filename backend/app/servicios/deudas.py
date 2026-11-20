"""Pasivos del usuario y amortización automática ("Resumen de Deudas").

Responsabilidad
---------------
- Registrar deudas con seis datos: acreedor, descripción, total adeudado, cuota,
  cuotas pendientes y periodicidad (`QUINCENAL` o `MENSUAL`).
- Validar que cuota × cuotas coincida con el total adeudado, con una tolerancia
  de un peso por cuota para absorber redondeos.
- Aplicar las cuotas vencidas al abrir el módulo, registrando cada pago en
  `pagos_deuda` (idempotente por `UNIQUE(id_deuda, numero_cuota)`).
- Proyectar las cuotas restantes y resumir la cartera.

Reglas (SRS v1.8):
- Sin intereses: no se captura tasa, no se deriva por bisección y no se simulan
  intereses. La cuota es fija y la última se ajusta para dejar el saldo en cero.
- Una cuota solo se aplica cuando su fecha de vencimiento ya pasó; abrir el
  módulo dos veces el mismo día no descuenta dos veces.
- `saldo_total` guarda el capital pendiente y se reduce con cada cuota aplicada.

Las tablas están documentadas en `diccionario_datos.md` §8 y §8.1.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import formatear_cop, parsear_monto
from app.modelos import Deuda, PagoDeuda

CERO = Decimal("0")
ESTADO_ACTIVA = "ACTIVA"
ESTADO_PAGADA = "PAGADA"

PERIODICIDAD_QUINCENAL = "QUINCENAL"
PERIODICIDAD_MENSUAL = "MENSUAL"
PERIODICIDADES = (PERIODICIDAD_QUINCENAL, PERIODICIDAD_MENSUAL)
DIAS_QUINCENA = 15
CUOTAS_MAXIMAS = 600

# SRS v1.8: la cuota y las cuotas deben reconstruir el total adeudado. Se acepta
# un peso de diferencia por cuota para absorber redondeos de centavos; cualquier
# diferencia mayor se rechaza con un mensaje que pide revisar los datos.
TOLERANCIA_POR_CUOTA = Decimal("1")


@dataclass(frozen=True)
class CuotaProyectada:
    """Cuota futura de la línea de amortización de una deuda.

    Attributes:
        numero: Número consecutivo de la cuota.
        fecha: Fecha de vencimiento estimada.
        valor: Valor de la cuota; la última se ajusta al saldo exacto.
        abono_capital: Porción que reduce el capital (la cuota completa).
        saldo_despues: Saldo pendiente después de esta cuota.
        ultima: `True` si es la cuota que cierra la deuda.
    """

    numero: int
    fecha: date
    valor: Decimal
    abono_capital: Decimal
    saldo_despues: Decimal
    ultima: bool = False


def _limpiar_periodicidad(periodicidad: str) -> str:
    """Normaliza y valida la periodicidad de una deuda.

    Args:
        periodicidad: Texto recibido del formulario.

    Returns:
        `QUINCENAL` o `MENSUAL`.

    Raises:
        ValueError: Si el valor no corresponde a ninguna periodicidad válida.
    """
    normalizada = (periodicidad or PERIODICIDAD_MENSUAL).strip().upper()
    if normalizada not in PERIODICIDADES:
        raise ValueError("La periodicidad debe ser QUINCENAL o MENSUAL.")
    return normalizada


def _sumar_periodo(fecha: date, periodicidad: str) -> date:
    """Suma un periodo de pago a una fecha.

    Args:
        fecha: Fecha de partida.
        periodicidad: `QUINCENAL` (15 días) o `MENSUAL` (un mes calendario).

    Returns:
        La fecha del siguiente vencimiento.
    """
    if periodicidad == PERIODICIDAD_QUINCENAL:
        return fecha + timedelta(days=DIAS_QUINCENA)
    anio = fecha.year + (1 if fecha.month == 12 else 0)
    mes = 1 if fecha.month == 12 else fecha.month + 1
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(fecha.day, ultimo_dia))


def _periodos_transcurridos(desde: date, hasta: date, periodicidad: str) -> int:
    """Cuenta los periodos de pago completos entre dos fechas.

    Args:
        desde: Fecha de referencia (creación de la deuda o último pago).
        hasta: Fecha de hoy.
        periodicidad: `QUINCENAL` o `MENSUAL`.

    Returns:
        Número de vencimientos ya cumplidos; cero si `hasta` es anterior.
    """
    if hasta < desde:
        return 0
    cuenta = 0
    cursor = desde
    while cuenta < CUOTAS_MAXIMAS:
        siguiente = _sumar_periodo(cursor, periodicidad)
        if siguiente > hasta:
            break
        cuenta += 1
        cursor = siguiente
    return cuenta


def validar_plan(
    saldo: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas: int | str,
) -> tuple[Decimal, Decimal, int]:
    """Comprueba que la cuota y las cuotas reconstruyan el total adeudado.

    SRS v1.8: como no se capturan intereses, el plan es coherente cuando
    ``cuota × cuotas`` coincide con el total adeudado. La tolerancia es de un
    peso por cuota para absorber redondeos; un error de digitación mayor se
    rechaza con un mensaje que muestra las cuentas.

    Args:
        saldo: Total adeudado.
        cuota: Valor de cada pago.
        cuotas: Número de pagos restantes.

    Returns:
        Tupla ``(total_adeudado, cuota, cuotas)`` normalizada.

    Raises:
        ValueError: Si algún dato es inválido o el plan no coincide con el total.
    """
    total = redondear_dinero(parsear_monto(str(saldo)))
    if total <= CERO:
        raise ValueError("El total adeudado debe ser mayor que cero.")

    pago = redondear_dinero(parsear_monto(str(cuota)))
    if pago <= CERO:
        raise ValueError("La cuota debe ser mayor que cero.")

    try:
        restantes = int(str(cuotas).strip())
    except (TypeError, ValueError) as error:
        raise ValueError("Las cuotas pendientes deben ser un número entero.") from error
    if restantes < 1 or restantes > CUOTAS_MAXIMAS:
        raise ValueError(
            f"Las cuotas pendientes deben estar entre 1 y {CUOTAS_MAXIMAS}."
        )

    calculado = redondear_dinero(pago * restantes)
    tolerancia = TOLERANCIA_POR_CUOTA * restantes
    if calculado > total + tolerancia:
        raise ValueError(
            f"Los datos no cuadran: {formatear_cop(pago)} × {restantes} cuotas "
            f"darían {formatear_cop(calculado)}, más que el total adeudado de "
            f"{formatear_cop(total)}. Revisa los datos e ingrésalos de nuevo."
        )
    if calculado < total - tolerancia:
        raise ValueError(
            f"Los datos no cuadran: {formatear_cop(pago)} × {restantes} cuotas "
            f"darían {formatear_cop(calculado)}, menos que el total adeudado de "
            f"{formatear_cop(total)}. Revisa los datos e ingrésalos de nuevo."
        )
    return total, pago, restantes


def crear_deuda(
    bd: Session,
    id_usuario: str,
    acreedor: str,
    saldo_total: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas_pendientes: int | str,
    periodicidad: str = PERIODICIDAD_MENSUAL,
    descripcion: str | None = None,
) -> Deuda:
    """Registra una deuda con su plan de pagos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda.
        acreedor: Entidad o persona acreedora.
        saldo_total: Capital pendiente inicial.
        cuota: Valor de cada pago.
        cuotas_pendientes: Número de pagos que faltan.
        periodicidad: `QUINCENAL` o `MENSUAL`.
        descripcion: Detalle opcional.

    Returns:
        La deuda persistida, lista para aplicar sus cuotas.

    Raises:
        ValueError: Si falta el acreedor, algún monto es inválido o la cuota por
            el número de pagos no coincide con el total adeudado.
    """
    acreedor_limpio = acreedor.strip()
    if not acreedor_limpio:
        raise ValueError("El acreedor es obligatorio.")

    capital, pago, restantes = validar_plan(saldo_total, cuota, cuotas_pendientes)
    frecuencia = _limpiar_periodicidad(periodicidad)

    deuda = Deuda(
        id_usuario=id_usuario,
        acreedor=acreedor_limpio[:100],
        descripcion=(descripcion or "").strip()[:150] or None,
        saldo_total=capital,
        cuota_mensual=pago,
        cuotas_pendientes=restantes,
        periodicidad=frecuencia,
        fecha_limite=None,
        estado=ESTADO_ACTIVA,
    )
    bd.add(deuda)
    bd.commit()
    bd.refresh(deuda)
    return deuda


def listar_deudas(bd: Session, id_usuario: str) -> list[Deuda]:
    """Lista las deudas del usuario, activas primero.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.

    Returns:
        Lista ordenada por estado y acreedor.
    """
    consulta = (
        select(Deuda)
        .where(Deuda.id_usuario == id_usuario)
        .order_by(Deuda.estado, Deuda.acreedor)
    )
    return list(bd.scalars(consulta))


def listar_pagos(bd: Session, id_usuario: str) -> dict[str, list[PagoDeuda]]:
    """Agrupa los pagos aplicados por deuda.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.

    Returns:
        Diccionario ``id_deuda → pagos`` ordenado por número de cuota.
    """
    consulta = (
        select(PagoDeuda)
        .join(Deuda, PagoDeuda.id_deuda == Deuda.id_deuda)
        .where(Deuda.id_usuario == id_usuario)
        .order_by(PagoDeuda.id_deuda, PagoDeuda.numero_cuota)
    )
    agrupados: dict[str, list[PagoDeuda]] = {}
    for pago in bd.scalars(consulta):
        agrupados.setdefault(pago.id_deuda, []).append(pago)
    return agrupados


def _aplicar_pago(
    bd: Session,
    deuda: Deuda,
    numero: int,
    fecha: date,
) -> bool:
    """Registra una cuota de la deuda y actualiza su saldo.

    Args:
        bd: Sesión de base de datos.
        deuda: Deuda a la que se aplica el pago.
        numero: Número consecutivo de la cuota.
        fecha: Fecha de vencimiento de la cuota.

    Returns:
        `True` si se registró; `False` si la deuda no tiene plan de pagos.
    """
    saldo = redondear_dinero(deuda.saldo_total)
    pago = redondear_dinero(deuda.cuota_mensual or CERO)
    if pago <= CERO or saldo <= CERO:
        return False

    # SRS v1.8: sin intereses. La cuota reduce capital y la última absorbe el
    # redondeo para dejar el saldo exacto en cero.
    ultima = deuda.cuotas_pendientes <= 1
    valor = saldo if ultima else min(pago, saldo)
    capital = valor

    saldo_nuevo = redondear_dinero(max(saldo - capital, CERO))
    bd.add(
        PagoDeuda(
            id_deuda=deuda.id_deuda,
            numero_cuota=numero,
            fecha_aplicacion=fecha,
            valor_cuota=valor,
            abono_capital=capital,
            interes=CERO,
            saldo_despues=saldo_nuevo,
        )
    )
    deuda.saldo_total = saldo_nuevo
    deuda.cuotas_pendientes = max(deuda.cuotas_pendientes - 1, 0)
    if saldo_nuevo == CERO or deuda.cuotas_pendientes == 0:
        deuda.estado = ESTADO_PAGADA
    return True


def aplicar_cuotas_vencidas(
    bd: Session, id_usuario: str, hoy: date | None = None
) -> int:
    """Aplica las cuotas cuya fecha de vencimiento ya pasó.

    Se invoca al abrir el módulo. El ancla del calendario es el último pago
    registrado o, si no hay, la fecha de creación de la deuda. Como cada pago
    queda en `pagos_deuda` con su número de cuota, repetir la operación el mismo
    día no duplica nada.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.
        hoy: Fecha de referencia; por defecto la de hoy.

    Returns:
        Número de cuotas aplicadas.
    """
    referencia = hoy or date.today()
    aplicadas = 0

    for deuda in listar_deudas(bd, id_usuario):
        if deuda.estado != ESTADO_ACTIVA or deuda.cuotas_pendientes <= 0:
            continue
        if not deuda.cuota_mensual or deuda.cuota_mensual <= CERO:
            continue

        pagos = list(
            bd.scalars(
                select(PagoDeuda)
                .where(PagoDeuda.id_deuda == deuda.id_deuda)
                .order_by(PagoDeuda.numero_cuota)
            )
        )
        ancla = pagos[-1].fecha_aplicacion if pagos else deuda.fecha_creacion.date()
        numero = pagos[-1].numero_cuota if pagos else 0

        pendientes = _periodos_transcurridos(ancla, referencia, deuda.periodicidad)
        # Nunca se aplican más cuotas de las que quedan en el plan.
        pendientes = min(pendientes, deuda.cuotas_pendientes)
        fecha = ancla
        for _ in range(pendientes):
            fecha = _sumar_periodo(fecha, deuda.periodicidad)
            numero += 1
            if not _aplicar_pago(bd, deuda, numero, fecha):
                break
            aplicadas += 1

    if aplicadas:
        bd.commit()
    return aplicadas


def proyeccion_deuda(deuda: Deuda, desde: date | None = None) -> list[CuotaProyectada]:
    """Calcula las cuotas que faltan por pagar.

    Args:
        deuda: Deuda con su saldo y plan vigentes.
        desde: Fecha del último pago; si es `None` se usa la de creación de la
            deuda, de modo que el calendario siga el mismo ancla que la
            amortización automática.

    Returns:
        Lista de cuotas futuras; vacía si la deuda ya está pagada.
    """
    saldo = redondear_dinero(deuda.saldo_total)
    pago = redondear_dinero(deuda.cuota_mensual or CERO)
    restantes = deuda.cuotas_pendientes
    if saldo <= CERO or pago <= CERO or restantes <= 0:
        return []

    ancla = desde or deuda.fecha_creacion.date()
    fecha = _sumar_periodo(ancla, deuda.periodicidad)

    cuotas: list[CuotaProyectada] = []
    numero = 1
    while restantes > 0 and saldo > CERO:
        # Sin intereses: cada cuota abona capital y la última cierra el saldo.
        ultima = restantes == 1
        valor = saldo if ultima else min(pago, saldo)
        saldo = redondear_dinero(max(saldo - valor, CERO))
        cuotas.append(
            CuotaProyectada(
                numero=numero,
                fecha=fecha,
                valor=valor,
                abono_capital=valor,
                saldo_despues=saldo,
                ultima=ultima,
            )
        )
        restantes -= 1
        numero += 1
        fecha = _sumar_periodo(fecha, deuda.periodicidad)
    return cuotas


def cuota_mensual_equivalente(deuda: Deuda) -> Decimal:
    """Expresa la cuota de la deuda como gasto mensual.

    Args:
        deuda: Deuda consultada.

    Returns:
        La cuota tal cual si es mensual, o el doble si es quincenal.
    """
    pago = redondear_dinero(deuda.cuota_mensual or CERO)
    if deuda.periodicidad == PERIODICIDAD_QUINCENAL:
        return redondear_dinero(pago * 2)
    return pago


def eliminar_deuda(bd: Session, id_usuario: str, id_deuda: str) -> bool:
    """Elimina una deuda y sus pagos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda.
        id_deuda: Deuda a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    deuda = bd.get(Deuda, id_deuda)
    if deuda is None or deuda.id_usuario != id_usuario:
        return False
    bd.delete(deuda)
    bd.commit()
    return True


def resumen_deudas(bd: Session, id_usuario: str) -> dict[str, Decimal | int]:
    """Calcula los totales del módulo de deudas.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.

    Returns:
        Diccionario con saldo pendiente, cuota mensual comprometida, cuotas
        pendientes, número de activas y número de pagadas.
    """
    deudas = listar_deudas(bd, id_usuario)
    activas = [deuda for deuda in deudas if deuda.estado == ESTADO_ACTIVA]
    return {
        "saldo_total": redondear_dinero(
            sum((deuda.saldo_total for deuda in activas), start=CERO)
        ),
        "cuota_mensual": redondear_dinero(
            sum((cuota_mensual_equivalente(deuda) for deuda in activas), start=CERO)
        ),
        "cuotas_pendientes": sum(deuda.cuotas_pendientes for deuda in activas),
        "activas": len(activas),
        "pagadas": len(deudas) - len(activas),
    }
