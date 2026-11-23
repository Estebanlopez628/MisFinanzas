"""Pasivos del usuario y amortización automática ("Registro y Detalles de deudas").

Responsabilidad
---------------
- Registrar deudas con seis datos: acreedor, descripción, total adeudado, cuota,
  cuotas pendientes y periodicidad (`QUINCENAL` o `MENSUAL`).
- Validar que `cuota × cuotas` **no sea menor** al total adeudado; el excedente
  se acepta como interés implícito y se cuadra en una amortización interna.
- Aplicar las cuotas vencidas al abrir el módulo, registrando cada pago en
  `pagos_deuda` (idempotente por `UNIQUE(id_deuda, numero_cuota)`).
- Proyectar las cuotas restantes y resumir la cartera.

Reglas (SRS v1.8 y v1.9, sección 2.2):
- Solo se rechaza un plan cuando `cuota × cuotas < saldo_total`: ni siquiera se
  cubre el capital. El mensaje es único y pide volver a digitar los datos.
- Cuando `cuota × cuotas >= saldo_total`, se deriva por bisección una tasa
  **ficticia** y se construye una amortización interna que cierra en cero. Esa
  tasa nunca se guarda, se muestra ni se usa en tablas o recomendaciones: los
  pagos reales siguen abonando capital y su columna `interes` queda en cero.
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
from app.core.texto import parsear_monto
from app.modelos import DeduccionFija, Deuda, Gasto, PagoDeuda

CERO = Decimal("0")
ESTADO_ACTIVA = "ACTIVA"
ESTADO_PAGADA = "PAGADA"

PERIODICIDAD_QUINCENAL = "QUINCENAL"
PERIODICIDAD_MENSUAL = "MENSUAL"
PERIODICIDADES = (PERIODICIDAD_QUINCENAL, PERIODICIDAD_MENSUAL)
DIAS_QUINCENA = 15
CUOTAS_MAXIMAS = 600

# SRS v1.9, sección 2.2: único mensaje de validación permitido para el plan de
# pagos. Se usa cuando la suma de cuotas no alcanza ni el capital adeudado.
MENSAJE_CUOTAS_INSUFICIENTES = (
    "El número de cuotas por el valor de cuota no alcanza a cubrir el valor "
    "total de la deuda. Revisa los datos y digítalos nuevamente."
)


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


def _validar_datos_plan(
    saldo: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas: int | str,
) -> tuple[Decimal, Decimal, int]:
    """Normaliza y comprueba los datos básicos de un plan de pagos.

    No exige que ``cuota × cuotas`` cuadre con el total: eso lo decide
    `validar_plan` para los planes que se van a registrar. La simulación de
    tasa implícita necesita esta validación más laxa para poder derivar una
    tasa cuando el total pagado supera el capital.

    Args:
        saldo: Total adeudado.
        cuota: Valor de cada pago.
        cuotas: Número de pagos restantes.

    Returns:
        Tupla ``(total_adeudado, cuota, cuotas)`` normalizada.

    Raises:
        ValueError: Si algún dato es inválido.
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
        raise ValueError(f"Las cuotas pendientes deben estar entre 1 y {CUOTAS_MAXIMAS}.")
    return total, pago, restantes


def validar_plan(
    saldo: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas: int | str,
) -> tuple[Decimal, Decimal, int]:
    """Valida el plan de pagos con interés implícito permitido.

    SRS v1.9, sección 2.2: ``cuota × cuotas`` puede ser mayor al total adeudado;
    ese excedente es interés implícito y se cuadra internamente. El único plan
    inválido es el que ni siquiera cubre el capital, y tiene un mensaje fijo.

    Args:
        saldo: Total adeudado.
        cuota: Valor de cada pago.
        cuotas: Número de pagos restantes.

    Returns:
        Tupla ``(total_adeudado, cuota, cuotas)`` normalizada.

    Raises:
        ValueError: Si algún dato es inválido o las cuotas no cubren el capital.
    """
    total, pago, restantes = _validar_datos_plan(saldo, cuota, cuotas)

    if redondear_dinero(pago * restantes) < total:
        raise ValueError(MENSAJE_CUOTAS_INSUFICIENTES)
    return total, pago, restantes


# SRS v1.9: la tasa se SIMULA para validar el plan, no se guarda ni se cobra.
# La amortización sigue sin intereses (ADR-53): cada cuota abona capital.
PRECISION_TASA = Decimal("0.0000000001")
TASA_MAXIMA_SIMULADA = Decimal("1000")
MAXIMO_INTENTOS_TASA = 240


def _valor_presente(cuota: Decimal, tasa: Decimal, cuotas: int) -> Decimal:
    """Calcula el valor presente de una anualidad de cuotas fijas.

    Args:
        cuota: Pago mensual.
        tasa: Tasa implícita por periodo.
        cuotas: Número de pagos.

    Returns:
        Valor presente de las cuotas; con tasa cero es ``cuota × cuotas``.
    """
    if tasa <= CERO:
        return cuota * cuotas
    return cuota * (1 - (1 + tasa) ** -cuotas) / tasa


def tasa_implicita_simulada(
    saldo: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas: int | str,
) -> Decimal:
    """Deriva, solo para validar, la tasa mensual que implica un plan de pagos.

    Es una simulación pura (SRS v1.9, sección 2.2): **no se guarda en la base de
    datos, no se muestra y no se aplica a los pagos reales**. Usa `validar_plan`
    para rechazar los planes que no cubren el capital. Si ``cuota × cuotas``
    coincide con el saldo, la tasa es cero; si el total pagado es mayor, se
    resuelve por bisección ``saldo = cuota × (1 − (1+r)^−n) / r`` con diez
    decimales de precisión.

    Args:
        saldo: Total adeudado informado.
        cuota: Valor de cada pago.
        cuotas: Número de pagos restantes.

    Returns:
        Tasa mensual simulada, redondeada a diez decimales; cero cuando el plan
        no implica intereses o cuando la cuota no supera el capital por cuota.

    Raises:
        ValueError: Si el plan no cubre el capital o si no existe una tasa
            positiva que lo explique.
    """
    from decimal import localcontext

    total, pago, restantes = validar_plan(saldo, cuota, cuotas)
    if pago * restantes <= total:
        return Decimal("0").quantize(PRECISION_TASA)

    with localcontext() as contexto:
        contexto.prec = 40
        bajo = CERO
        alto = Decimal("0.01")
        while _valor_presente(pago, alto, restantes) > total and alto < TASA_MAXIMA_SIMULADA:
            alto *= 2
        if _valor_presente(pago, alto, restantes) > total:
            raise ValueError("No se puede derivar una tasa implícita para este plan de pagos.")
        for _intento in range(MAXIMO_INTENTOS_TASA):
            medio = (bajo + alto) / 2
            if _valor_presente(pago, medio, restantes) > total:
                bajo = medio
            else:
                alto = medio
            if alto - bajo < PRECISION_TASA:
                break
        return ((bajo + alto) / 2).quantize(PRECISION_TASA)


def amortizacion_simulada(
    saldo: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas: int | str,
) -> tuple[Decimal, list[dict[str, object]]]:
    """Cuadra el plan con una amortización ficticia. **Uso interno exclusivo.**

    SRS v1.9, sección 2.2: cuando ``cuota × cuotas`` supera el capital, esta
    función reparte cada cuota entre interés simulado y abono a capital, con la
    última cuota ajustada para dejar el saldo exactamente en cero. Es la
    comprobación matemática del modelo; **no se persiste, no se muestra en
    pantallas, tablas ni recibos, y no alimenta recomendaciones**. Los pagos
    reales siguen abonando capital completo con `interes = 0`.

    Args:
        saldo: Capital adeudado.
        cuota: Valor de cada pago.
        cuotas: Número de pagos del plan.

    Returns:
        Tupla ``(tasa_simulada, cuotas)``; cada cuota trae número, pago,
        interés ficticio, abono a capital y saldo resultante.

    Raises:
        ValueError: Si el plan no cubre el capital o la tasa no se puede derivar.
    """
    from decimal import localcontext

    total, pago, restantes = validar_plan(saldo, cuota, cuotas)
    tasa = tasa_implicita_simulada(total, pago, restantes)

    with localcontext() as contexto:
        contexto.prec = 40
        capital = total
        filas: list[dict[str, object]] = []
        for numero in range(1, restantes + 1):
            interes = redondear_dinero(capital * tasa)
            ultima = numero == restantes
            abono = capital if ultima else min(redondear_dinero(pago - interes), capital)
            capital = redondear_dinero(max(capital - abono, CERO))
            filas.append(
                {
                    "numero": numero,
                    "pago": redondear_dinero(interes + abono),
                    "interes": interes,
                    "abono_capital": abono,
                    "saldo_despues": capital,
                }
            )
    return tasa, filas


def deuda_vinculable(bd: Session, id_usuario: str, id_deuda: str | None) -> Deuda | None:
    """Busca una deuda que pueda vincularse a un gasto o deducción fija.

    SRS v1.9, sección 3.2: se pueden vincular **todas** las deudas propias
    activas, con periodicidad mensual o quincenal. No se guarda ningún interés:
    el gasto o descuento toma el valor de la cuota registrada.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda.
        id_deuda: Identificador elegido; vacío o `None` significa sin vínculo.

    Returns:
        La deuda vinculable, o `None` si no se pidió vínculo.

    Raises:
        ValueError: Si la deuda no existe, es ajena o ya está pagada.
    """
    texto = (id_deuda or "").strip()
    if not texto:
        return None
    deuda = bd.get(Deuda, texto)
    if deuda is None or deuda.id_usuario != id_usuario:
        raise ValueError("La deuda elegida no existe.")
    if deuda.estado != ESTADO_ACTIVA:
        raise ValueError("Esa deuda ya está pagada; no se puede vincular.")
    return deuda


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
        ValueError: Si falta el acreedor, algún monto es inválido o las cuotas
            no cubren el capital adeudado.
    """
    acreedor_limpio = acreedor.strip()
    if not acreedor_limpio:
        raise ValueError("El acreedor es obligatorio.")

    capital, pago, restantes = validar_plan(saldo_total, cuota, cuotas_pendientes)
    # Comprobación matemática interna: cuadra el plan con interés ficticio. El
    # resultado se descarta; jamás se persiste ni se muestra al usuario.
    amortizacion_simulada(capital, pago, restantes)
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


def actualizar_deuda(
    bd: Session,
    id_usuario: str,
    id_deuda: str,
    acreedor: str,
    saldo_total: Decimal | str | int | float,
    cuota: Decimal | str | int | float,
    cuotas_pendientes: int | str,
    periodicidad: str = PERIODICIDAD_MENSUAL,
    descripcion: str | None = None,
) -> Deuda | None:
    """Corrige el plan de una deuda propia con la misma validación del alta.

    El historial de `pagos_deuda` no se reescribe: los pagos ya aplicados
    conservan su número, fecha y valor. El saldo y las cuotas que llegan en el
    formulario pasan a ser la referencia del plan a partir de ahora.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda (evita editar datos ajenos).
        id_deuda: Identificador de la deuda.
        acreedor: Entidad o persona acreedora.
        saldo_total: Capital pendiente inicial.
        cuota: Valor de cada pago.
        cuotas_pendientes: Número de pagos restantes.
        periodicidad: `QUINCENAL` o `MENSUAL`.
        descripcion: Detalle opcional.

    Returns:
        La deuda actualizada, o `None` si no existe o es de otro usuario.

    Raises:
        ValueError: Si faltan datos, la periodicidad es inválida o las cuotas
            no cubren el capital adeudado.
    """
    deuda = bd.get(Deuda, id_deuda)
    if deuda is None or deuda.id_usuario != id_usuario:
        return None
    acreedor_limpio = acreedor.strip()
    if not acreedor_limpio:
        raise ValueError("El acreedor es obligatorio.")

    capital, pago, restantes = validar_plan(saldo_total, cuota, cuotas_pendientes)
    # Igual que en el alta: comprobación matemática privada, sin persistirla.
    amortizacion_simulada(capital, pago, restantes)
    frecuencia = _limpiar_periodicidad(periodicidad)

    deuda.acreedor = acreedor_limpio[:100]
    deuda.descripcion = (descripcion or "").strip()[:150] or None
    deuda.saldo_total = capital
    deuda.cuota_mensual = pago
    deuda.cuotas_pendientes = restantes
    deuda.periodicidad = frecuencia
    deuda.estado = ESTADO_ACTIVA
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


MODULO_FINANZAS = "Finanzas"
MODULO_TRABAJOS = "Trabajos Extras"


def vinculaciones_de_deudas(bd: Session, id_usuario: str) -> dict[str, dict[str, object]]:
    """Indica qué deuda paga cada gasto o deducción del usuario (SRS v4.4, 5.1).

    Un gasto fijo con `id_trabajo` pertenece a Trabajos Extras; los demás gastos
    y todas las deducciones fijas pertenecen a Finanzas. Una deuda puede estar
    vinculada a varios módulos a la vez, por eso se devuelve la lista ordenada.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas y de los vínculos.

    Returns:
        Diccionario por `id_deuda` con `esta_vinculada` y `modulos_vinculados`.
    """
    modulos: dict[str, set[str]] = {}

    gastos = bd.scalars(
        select(Gasto).where(Gasto.id_usuario == id_usuario, Gasto.id_deuda.is_not(None))
    )
    for gasto in gastos:
        modulo = MODULO_TRABAJOS if gasto.id_trabajo else MODULO_FINANZAS
        modulos.setdefault(str(gasto.id_deuda), set()).add(modulo)

    deducciones = bd.scalars(
        select(DeduccionFija).where(
            DeduccionFija.id_usuario == id_usuario, DeduccionFija.id_deuda.is_not(None)
        )
    )
    for deduccion in deducciones:
        modulos.setdefault(str(deduccion.id_deuda), set()).add(MODULO_FINANZAS)

    return {
        id_deuda: {
            "esta_vinculada": True,
            "modulos_vinculados": sorted(
                nombres,
                key=lambda nombre: 0 if nombre == MODULO_FINANZAS else 1,
            ),
        }
        for id_deuda, nombres in modulos.items()
    }


def vinculacion_de_deuda(
    bd: Session, id_usuario: str, id_deuda: str
) -> dict[str, object]:
    """Devuelve la vinculación de una sola deuda (SRS v4.4, sección 5.1).

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deuda.
        id_deuda: Deuda consultada.

    Returns:
        Diccionario con `esta_vinculada` y `modulos_vinculados`.
    """
    return vinculaciones_de_deudas(bd, id_usuario).get(
        id_deuda, {"esta_vinculada": False, "modulos_vinculados": []}
    )


def listar_vinculables(bd: Session, id_usuario: str) -> list[Deuda]:
    """Lista todas las deudas activas que se pueden vincular (SRS v1.9, 3.2).

    Se ofrecen deudas propias activas con cuotas pendientes, sin importar su
    periodicidad: el selector debe mostrar «todas las deudas activas
    registradas», tal como pide la especificación.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas.

    Returns:
        Deudas vinculables, ordenadas por acreedor.
    """
    consulta = (
        select(Deuda)
        .where(
            Deuda.id_usuario == id_usuario,
            Deuda.estado == ESTADO_ACTIVA,
            Deuda.cuotas_pendientes > 0,
        )
        .order_by(Deuda.acreedor)
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

    # SRS v1.9: los pagos reales siguen sin intereses visibles. El interés
    # simulado solo existe en `amortizacion_simulada` y nunca llega aquí.
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
    deuda.cuotas_pendientes = (
        0 if saldo_nuevo == CERO else max(deuda.cuotas_pendientes - 1, 0)
    )
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
    # SRS v1.9: la deducción vinculada sigue existiendo como descuento normal. Se
    # desvincula en la sesión, además de en la base, para que los cálculos de esta
    # misma sesión no la sigan viendo como cuota de la deuda borrada.
    for deduccion in bd.scalars(select(DeduccionFija).where(DeduccionFija.id_deuda == id_deuda)):
        deduccion.id_deuda = None
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
