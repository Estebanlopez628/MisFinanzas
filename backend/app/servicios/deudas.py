"""Pasivos del usuario y amortización automática ("Resumen de Deudas").

Responsabilidad
---------------
- Registrar deudas con seis datos: acreedor, descripción, saldo, cuota, cuotas
  pendientes y periodicidad (`QUINCENAL` o `MENSUAL`).
- Derivar la tasa de interés implícita del saldo, la cuota y el número de pagos.
- Aplicar las cuotas vencidas al abrir el módulo, registrando cada pago en
  `pagos_deuda` (idempotente por `UNIQUE(id_deuda, numero_cuota)`).
- Proyectar las cuotas restantes y resumir la cartera.

Reglas (SRS v1.5):
- El usuario no captura tasa de interés, fecha límite ni abonos: la cuota es
  fija y la última se ajusta para dejar el saldo exactamente en cero.
- Una cuota solo se aplica cuando su fecha de vencimiento ya pasó; abrir el
  módulo dos veces el mismo día no descuenta dos veces.
- `saldo_total` guarda el capital pendiente y se reduce con cada cuota aplicada.

Las tablas están documentadas en `diccionario_datos.md` §8 y §8.1.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import Deuda, PagoDeuda

CERO = Decimal("0")
ESTADO_ACTIVA = "ACTIVA"
ESTADO_PAGADA = "PAGADA"

PERIODICIDAD_QUINCENAL = "QUINCENAL"
PERIODICIDAD_MENSUAL = "MENSUAL"
PERIODICIDADES = (PERIODICIDAD_QUINCENAL, PERIODICIDAD_MENSUAL)
DIAS_QUINCENA = 15
CUOTAS_MAXIMAS = 600

# La bisección busca la tasa por periodo en [0, 100 %]. Cien iteraciones sobran
# para la precisión de diez decimales que se guarda en la base; con menos, el
# redondeo de los intereses acumula centavos y la última cuota se desvía.
TASA_MAXIMA = Decimal("1")
PRECISION_TASA = Decimal("0.0000000001")
ITERACIONES_TASA = 100


@dataclass(frozen=True)
class CuotaProyectada:
    """Cuota futura de la línea de amortización de una deuda.

    Attributes:
        numero: Número consecutivo de la cuota.
        fecha: Fecha de vencimiento estimada.
        valor: Valor de la cuota; la última se ajusta al saldo exacto.
        interes: Porción de la cuota destinada a intereses.
        abono_capital: Porción que reduce el capital.
        saldo_despues: Saldo pendiente después de esta cuota.
        ultima: `True` si es la cuota que cierra la deuda.
    """

    numero: int
    fecha: date
    valor: Decimal
    interes: Decimal
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


def tasa_implicita(
    saldo: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas: int | str,
) -> Decimal:
    """Deriva la tasa de interés por periodo que hace coherente la deuda.

    Resuelve por bisección `saldo = cuota × (1 − (1 + r)^−n) / r`, la fórmula de
    una anualidad. Así el usuario solo informa saldo, cuota y número de pagos; la
    tasa queda implícita en esos tres datos.

    Args:
        saldo: Capital pendiente.
        cuota: Valor de cada pago.
        cuotas: Número de pagos restantes.

    Returns:
        Tasa por periodo como fracción (`0.013709` equivale a 1,3709 %).

    Raises:
        ValueError: Si algún dato no es positivo o la cuota no alcanza a cubrir
            el saldo en el número de cuotas indicado.
    """
    capital = redondear_dinero(parsear_monto(str(saldo)))
    pago = redondear_dinero(parsear_monto(str(cuota)))
    try:
        numero = int(cuotas)
    except (TypeError, ValueError) as error:
        raise ValueError("El número de cuotas debe ser un entero.") from error

    if numero <= 0:
        raise ValueError("El número de cuotas debe ser mayor que cero.")
    if capital < CERO:
        raise ValueError("El saldo total no puede ser negativo.")
    if pago <= CERO:
        raise ValueError("La cuota debe ser mayor que cero.")
    if capital == CERO:
        return CERO

    total = pago * numero
    if total < capital:
        raise ValueError(
            "La cuota y el número de cuotas no alcanzan a cubrir el saldo total."
        )
    if total == capital:
        # Sin intereses: la tasa implícita es cero.
        return CERO

    def valor_presente(tasa: Decimal) -> Decimal:
        """Valor presente de la anualidad a una tasa dada.

        Args:
            tasa: Tasa por periodo como fracción.

        Returns:
            Suma descontada de las cuotas.
        """
        if tasa == CERO:
            return pago * numero
        return pago * (1 - (1 + tasa) ** -numero) / tasa

    bajo, alto = CERO, TASA_MAXIMA
    for _ in range(ITERACIONES_TASA):
        medio = (bajo + alto) / 2
        if valor_presente(medio) > capital:
            # Con esta tasa las cuotas valen más que la deuda: hay que subirla.
            bajo = medio
        else:
            alto = medio
    return ((bajo + alto) / 2).quantize(PRECISION_TASA, rounding=ROUND_HALF_UP)


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
        La deuda persistida, con la tasa implícita ya calculada.

    Raises:
        ValueError: Si falta el acreedor, algún monto es inválido o el plan de
            pagos no cubre el saldo.
    """
    acreedor_limpio = acreedor.strip()
    if not acreedor_limpio:
        raise ValueError("El acreedor es obligatorio.")

    capital = redondear_dinero(parsear_monto(str(saldo_total)))
    if capital <= CERO:
        raise ValueError("El saldo total debe ser mayor que cero.")

    pago = redondear_dinero(parsear_monto(str(cuota)))
    if pago <= CERO:
        raise ValueError("La cuota debe ser mayor que cero.")

    try:
        restantes = int(cuotas_pendientes)
    except (TypeError, ValueError) as error:
        raise ValueError("Las cuotas pendientes deben ser un número entero.") from error
    if restantes < 1 or restantes > CUOTAS_MAXIMAS:
        raise ValueError(
            f"Las cuotas pendientes deben estar entre 1 y {CUOTAS_MAXIMAS}."
        )

    frecuencia = _limpiar_periodicidad(periodicidad)
    tasa = tasa_implicita(capital, pago, restantes)

    deuda = Deuda(
        id_usuario=id_usuario,
        acreedor=acreedor_limpio[:100],
        descripcion=(descripcion or "").strip()[:150] or None,
        saldo_total=capital,
        cuota_mensual=pago,
        cuotas_pendientes=restantes,
        periodicidad=frecuencia,
        tasa_interes=tasa,
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

    tasa = deuda.tasa_interes
    if tasa is None:
        # Deudas migradas desde el modelo anterior: la tasa se deriva ahora.
        tasa = tasa_implicita(saldo, pago, max(deuda.cuotas_pendientes, 1))
        deuda.tasa_interes = tasa

    interes = redondear_dinero(saldo * tasa)
    ultima = deuda.cuotas_pendientes <= 1
    if ultima:
        # La última cuota absorbe el redondeo y deja el saldo exacto en cero.
        valor = redondear_dinero(saldo + interes)
        capital = saldo
    else:
        valor = pago
        capital = redondear_dinero(pago - interes)

    if capital <= CERO:
        # Cuota menor que los intereses: no amortiza y la deuda no avanzaría.
        raise ValueError(
            "La cuota no cubre los intereses del periodo; revisa el plan de pagos."
        )

    saldo_nuevo = redondear_dinero(max(saldo - capital, CERO))
    bd.add(
        PagoDeuda(
            id_deuda=deuda.id_deuda,
            numero_cuota=numero,
            fecha_aplicacion=fecha,
            valor_cuota=valor,
            abono_capital=capital,
            interes=interes,
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
    tasa = deuda.tasa_interes
    if saldo <= CERO or pago <= CERO or restantes <= 0:
        return []
    if tasa is None:
        tasa = tasa_implicita(saldo, pago, restantes)

    ancla = desde or deuda.fecha_creacion.date()
    fecha = _sumar_periodo(ancla, deuda.periodicidad)

    cuotas: list[CuotaProyectada] = []
    numero = 1
    while restantes > 0 and saldo > CERO:
        interes = redondear_dinero(saldo * tasa)
        ultima = restantes == 1
        if ultima:
            valor = redondear_dinero(saldo + interes)
            capital = saldo
        else:
            valor = pago
            capital = redondear_dinero(pago - interes)
        if capital <= CERO:
            break
        saldo = redondear_dinero(max(saldo - capital, CERO))
        cuotas.append(
            CuotaProyectada(
                numero=numero,
                fecha=fecha,
                valor=valor,
                interes=interes,
                abono_capital=capital,
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
