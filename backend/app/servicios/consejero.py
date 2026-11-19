"""Consejero financiero del excedente mensual (SRS v1.7, bloque G).

Responsabilidad
---------------
- Analizar si conviene amortizar deudas o alimentar metas de ahorro cuando el
  excedente consolidado del mes (quincenas más trabajos extras) supera los
  $300.000.
- Comparar las dos estrategias de amortización: bola de nieve (deuda más pequeña
  primero) y avalancha (tasa más alta primero), y recomendar la que menos
  intereses cuesta en doce meses.
- Entregar la serie mensual «base frente a optimizado» para la gráfica.

Reglas:
- El consejero solo se activa con un excedente **mayor** que el umbral; por
  debajo, el usuario primero debe equilibrar su presupuesto.
- La simulación trabaja en meses: una deuda quincenal convierte su tasa y su
  cuota a equivalente mensual. Los intereses se redondean a pesos.
- En modo deuda, «base» paga solo las cuotas mínimas y «optimizado» aplica todo
  el excedente a la deuda elegida, pasando a la siguiente cuando se termina.
- En modo ahorro, «base» acumula solo lo ya planeado en metas y «optimizado»
  suma el excedente. Si no hay metas, se sugiere crear una.
- Es una proyección educativa, no una promesa: supone ingreso y cuotas estables.

Este módulo no escribe en la base de datos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import formatear_cop
from app.modelos import Deuda
from app.servicios import ahorro as servicio_ahorro
from app.servicios import capacidad as servicio_capacidad
from app.servicios import deudas as servicio_deudas

CERO = Decimal("0")
CIEN = Decimal("100")
MESES = 12
UMBRAL_ACTIVACION = Decimal("300000")

MODO_DEUDA = "DEUDA"
MODO_AHORRO = "AHORRO"

ESTRATEGIA_AVALANCHA = "AVALANCHA"
ESTRATEGIA_BOLA = "BOLA_DE_NIEVE"
ESTRATEGIA_METAS = "METAS"
ESTRATEGIA_SIN_METAS = "SIN_METAS"


@dataclass(frozen=True)
class Consejo:
    """Recomendación del consejero y su comparación a doce meses.

    Attributes:
        activo: `True` solo si el excedente supera el umbral.
        alias: Nombre visible del usuario para el saludo.
        excedente: Dinero disponible del mes (quincenas + extras).
        umbral: Monto mínimo para activarse.
        modo: `DEUDA` si hay pasivos, `AHORRO` si no los hay.
        estrategia: `AVALANCHA`, `BOLA_DE_NIEVE`, `METAS` o `SIN_METAS`.
        titulo: Saludo con el alias.
        mensaje: Recomendación principal en lenguaje natural.
        pasos: Acciones concretas sugeridas.
        deuda_objetivo: Acreedor que concentra el excedente, si aplica.
        interes_base: Intereses pagados a doce meses sin aplicar el excedente.
        interes_optimizado: Intereses pagados con la estrategia recomendada.
        ahorro_base: Ahorro acumulado sin aplicar el excedente.
        ahorro_optimizado: Ahorro acumulado aplicando el excedente.
        meses_liquidacion: Mes en que la deuda llega a cero, si ocurre.
        serie: Doce filas con la comparación y sus alturas de barra.
        maximo: Valor mayor de la serie, base de las alturas relativas.
    """

    activo: bool
    alias: str
    excedente: Decimal
    umbral: Decimal
    modo: str = MODO_AHORRO
    estrategia: str = ESTRATEGIA_SIN_METAS
    titulo: str = ""
    mensaje: str = ""
    pasos: list[str] = field(default_factory=list)
    deuda_objetivo: str | None = None
    interes_base: Decimal = CERO
    interes_optimizado: Decimal = CERO
    ahorro_base: Decimal = CERO
    ahorro_optimizado: Decimal = CERO
    meses_liquidacion: int | None = None
    serie: list[dict[str, object]] = field(default_factory=list)
    maximo: Decimal = CERO


@dataclass
class _EstadoDeuda:
    """Deuda con su saldo vivo durante una simulación.

    Attributes:
        deuda: Registro original, del que se toman el acreedor y la tasa.
        saldo: Capital pendiente en el mes simulado.
        tasa: Tasa mensual equivalente como fracción.
        cuota: Cuota mensual equivalente.
    """

    deuda: Deuda
    saldo: Decimal
    tasa: Decimal
    cuota: Decimal


def _tasa_mensual(deuda: Deuda) -> Decimal:
    """Convierte la tasa de una deuda a equivalente mensual.

    Args:
        deuda: Deuda activa.

    Returns:
        Tasa mensual como fracción; cero si la deuda no tiene plan válido.
    """
    tasa = deuda.tasa_interes
    if tasa is None:
        try:
            tasa = servicio_deudas.tasa_implicita(
                deuda.saldo_total,
                deuda.cuota_mensual or CERO,
                max(deuda.cuotas_pendientes, 1),
            )
        except (ValueError, ArithmeticError):
            tasa = CERO
    if deuda.periodicidad == servicio_deudas.PERIODICIDAD_QUINCENAL:
        # Dos pagos por mes: la tasa compuesta mensual es (1 + r)² − 1.
        return (1 + tasa) ** 2 - 1
    return tasa


def _estados(deudas: list[Deuda]) -> list[_EstadoDeuda]:
    """Construye los estados simulables de las deudas activas.

    Args:
        deudas: Deudas del usuario.

    Returns:
        Lista con saldo y cuota mensual de cada deuda vigente.
    """
    estados: list[_EstadoDeuda] = []
    for deuda in deudas:
        if deuda.estado != servicio_deudas.ESTADO_ACTIVA:
            continue
        saldo = redondear_dinero(deuda.saldo_total)
        cuota = servicio_deudas.cuota_mensual_equivalente(deuda)
        if saldo <= CERO or cuota <= CERO:
            continue
        estados.append(
            _EstadoDeuda(
                deuda=deuda,
                saldo=saldo,
                tasa=_tasa_mensual(deuda),
                cuota=cuota,
            )
        )
    return estados


def _ordenar(estados: list[_EstadoDeuda], estrategia: str) -> list[_EstadoDeuda]:
    """Ordena las deudas según la estrategia de amortización.

    Args:
        estados: Deudas simulables.
        estrategia: `AVALANCHA` (tasa más alta) o `BOLA_DE_NIEVE` (saldo menor).

    Returns:
        Lista ordenada de la primera a la última deuda a atacar.
    """
    if estrategia == ESTRATEGIA_BOLA:
        return sorted(estados, key=lambda estado: (estado.saldo, -estado.tasa))
    return sorted(estados, key=lambda estado: (-estado.tasa, estado.saldo))


def _simular(
    estados: list[_EstadoDeuda],
    excedente: Decimal,
    estrategia: str | None = None,
    aplicar_excedente: bool = True,
) -> tuple[Decimal, list[Decimal], int | None]:
    """Simula doce meses de pagos sobre un conjunto de deudas.

    Args:
        estados: Deudas de partida; no se modifican.
        excedente: Dinero extra que se aplica cada mes.
        estrategia: Orden de ataque cuando se aplica el excedente.
        aplicar_excedente: `False` simula solo las cuotas mínimas (base).

    Returns:
        Tupla `(intereses_totales, saldo_restante_por_mes, mes_liquidacion)`.
    """
    copia = [
        _EstadoDeuda(estado.deuda, estado.saldo, estado.tasa, estado.cuota)
        for estado in estados
    ]
    orden = _ordenar(copia, estrategia) if estrategia else []
    intereses = CERO
    serie: list[Decimal] = []
    liquidacion: int | None = None

    for avance in range(MESES):
        for estado in copia:
            if estado.saldo <= CERO:
                continue
            interes = redondear_dinero(estado.saldo * estado.tasa)
            estado.saldo = redondear_dinero(estado.saldo + interes)
            intereses = redondear_dinero(intereses + interes)

        for estado in copia:
            if estado.saldo <= CERO:
                continue
            pago = min(estado.cuota, estado.saldo)
            estado.saldo = redondear_dinero(estado.saldo - pago)

        if aplicar_excedente and excedente > CERO:
            resto = excedente
            for estado in orden:
                if resto <= CERO:
                    break
                if estado.saldo <= CERO:
                    continue
                pago = min(resto, estado.saldo)
                estado.saldo = redondear_dinero(estado.saldo - pago)
                resto = redondear_dinero(resto - pago)

        total = redondear_dinero(sum((estado.saldo for estado in copia), start=CERO))
        serie.append(total)
        if liquidacion is None and total <= CERO:
            liquidacion = avance + 1

    return intereses, serie, liquidacion


def _altura(valor: Decimal, maximo: Decimal) -> Decimal:
    """Convierte un monto en porcentaje de altura para la barra.

    Args:
        valor: Monto de la barra.
        maximo: Valor mayor de la serie.

    Returns:
        Porcentaje entre 0 y 100 redondeado a un decimal.
    """
    if maximo <= CERO:
        return CERO
    proporcion = max(valor, CERO) / maximo * CIEN
    return min(proporcion, CIEN).quantize(Decimal("0.1"))


def _serie_comparada(
    base: list[Decimal],
    optimizado: list[Decimal],
    etiquetas: list[str],
) -> tuple[list[dict[str, object]], Decimal]:
    """Arma las filas de la gráfica comparativa.

    Args:
        base: Saldo o ahorro mes a mes del escenario base.
        optimizado: Valores del escenario con el excedente aplicado.
        etiquetas: Rótulo corto de cada mes.

    Returns:
        Tupla `(filas, maximo)` con `base`, `optimizado` y sus alturas.
    """
    maximo = max(
        [CERO, *base, *optimizado],
    )
    filas: list[dict[str, object]] = []
    for indice, etiqueta in enumerate(etiquetas):
        valor_base = base[indice]
        valor_optimo = optimizado[indice]
        filas.append(
            {
                "etiqueta": etiqueta,
                "base": valor_base,
                "optimizado": valor_optimo,
                "base_pct": _altura(valor_base, maximo),
                "optimizado_pct": _altura(valor_optimo, maximo),
            }
        )
    return filas, maximo


def _consejo_deuda(
    estados: list[_EstadoDeuda],
    excedente: Decimal,
    alias: str,
    etiquetas: list[str],
) -> Consejo:
    """Recomienda bola de nieve o avalancha y compara contra el pago mínimo.

    Args:
        estados: Deudas activas del usuario.
        excedente: Dinero extra mensual.
        alias: Nombre visible para el saludo.
        etiquetas: Rótulos de los doce meses.

    Returns:
        El consejo configurado en modo deuda.
    """
    interes_base, serie_base, _ = _simular(estados, excedente, aplicar_excedente=False)
    interes_aval, serie_aval, meses_aval = _simular(
        estados, excedente, ESTRATEGIA_AVALANCHA
    )
    interes_bola, serie_bola, meses_bola = _simular(
        estados, excedente, ESTRATEGIA_BOLA
    )

    if interes_aval <= interes_bola:
        estrategia = ESTRATEGIA_AVALANCHA
        interes_optimo, serie_optima, meses = interes_aval, serie_aval, meses_aval
        nombre = "avalancha"
        criterio = "la deuda con la tasa más alta"
    else:
        estrategia = ESTRATEGIA_BOLA
        interes_optimo, serie_optima, meses = interes_bola, serie_bola, meses_bola
        nombre = "bola de nieve"
        criterio = "la deuda más pequeña"

    orden = _ordenar(estados, estrategia)
    objetivo = orden[0].deuda.acreedor if orden else None
    ahorro_intereses = max(redondear_dinero(interes_base - interes_optimo), CERO)
    serie, maximo = _serie_comparada(serie_base, serie_optima, etiquetas)

    if meses:
        cierre = f"Con este ritmo quedarías libre de deudas en {meses} meses."
    else:
        cierre = (
            "En doce meses tu saldo pendiente bajaría a "
            f"{formatear_cop(serie_optima[-1])}."
        )

    pasos = [
        f"Concentra el excedente de {formatear_cop(excedente)} en {objetivo} "
        f"({criterio})."
    ]
    if len(orden) > 1:
        siguientes = ", ".join(estado.deuda.acreedor for estado in orden[1:3])
        pasos.append(f"Cuando esa deuda cierre, sigue con {siguientes}.")
    mayor = max(estados, key=lambda estado: estado.saldo)
    pasos.append(
        f"Tu deuda más grande es {mayor.deuda.acreedor}, con "
        f"{formatear_cop(mayor.saldo)} de saldo."
    )
    pasos.append(cierre)

    mensaje = (
        f"{alias}, con {formatear_cop(excedente)} de excedente te conviene la "
        f"estrategia {nombre}: ataca primero {objetivo}. Aplicarla ahorra "
        f"{formatear_cop(ahorro_intereses)} en intereses frente a pagar solo lo "
        "mínimo."
    )

    return Consejo(
        activo=True,
        alias=alias,
        excedente=excedente,
        umbral=UMBRAL_ACTIVACION,
        modo=MODO_DEUDA,
        estrategia=estrategia,
        titulo=f"Hola, {alias}: esto es lo que haría con tu excedente",
        mensaje=mensaje,
        pasos=pasos,
        deuda_objetivo=objetivo,
        interes_base=interes_base,
        interes_optimizado=interes_optimo,
        meses_liquidacion=meses,
        serie=serie,
        maximo=maximo,
    )


def _consejo_ahorro(
    bd: Session,
    id_usuario: str,
    excedente: Decimal,
    alias: str,
    etiquetas: list[str],
) -> Consejo:
    """Recomienda dirigir el excedente a las metas de ahorro.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las metas.
        excedente: Dinero extra mensual.
        alias: Nombre visible para el saludo.
        etiquetas: Rótulos de los doce meses.

    Returns:
        El consejo configurado en modo ahorro.
    """
    metas = servicio_ahorro.resumen_metas(bd, id_usuario)
    planeado = redondear_dinero(
        sum(
            (servicio_ahorro.valor_mensual_efectivo(meta.proyeccion) for meta in metas),
            start=CERO,
        )
    )
    objetivo = redondear_dinero(
        sum(
            (
                max((meta.total_proyectado or CERO) - meta.acumulado, CERO)
                for meta in metas
            ),
            start=CERO,
        )
    )

    serie_base: list[Decimal] = []
    serie_optima: list[Decimal] = []
    acumulado_base = CERO
    acumulado_optimo = CERO
    for _ in range(MESES):
        acumulado_base = redondear_dinero(acumulado_base + planeado)
        acumulado_optimo = redondear_dinero(acumulado_optimo + planeado + excedente)
        serie_base.append(acumulado_base)
        serie_optima.append(acumulado_optimo)

    serie, maximo = _serie_comparada(serie_base, serie_optima, etiquetas)

    if metas:
        estrategia = ESTRATEGIA_METAS
        primera = metas[0]
        ritmo = redondear_dinero(planeado + excedente)
        restante = max((primera.total_proyectado or CERO) - primera.acumulado, CERO)
        meses_meta = (
            int(math.ceil(restante / ritmo)) if ritmo > CERO and restante > CERO else 1
        )
        mensaje = (
            f"{alias}, no tienes deudas activas: tu excedente de "
            f"{formatear_cop(excedente)} puede acelerar tus metas. Dirigido a "
            f"«{primera.proyeccion.descripcion}», la completarías en unos "
            f"{meses_meta} meses."
        )
        pasos = [
            f"Asigna {formatear_cop(excedente)} al mes a «{primera.proyeccion.descripcion}».",
            "Mantén el check de pago al día: cada ✔ registra el abono de la meta.",
            "Cuando termines una meta, pasa el mismo monto a la siguiente.",
        ]
    else:
        estrategia = ESTRATEGIA_SIN_METAS
        mensaje = (
            f"{alias}, no tienes deudas ni metas activas. Tu excedente de "
            f"{formatear_cop(excedente)} puede convertirse en ahorro: crea una "
            "meta en Gastos y Presupuesto para darle un destino."
        )
        pasos = [
            "Crea una meta con su cuota mensual y su periodo.",
            "Asigna el excedente a esa meta desde el primer mes.",
            "Revisa el diagnóstico cada mes y ajusta la cuota si cambia tu ingreso.",
        ]

    return Consejo(
        activo=True,
        alias=alias,
        excedente=excedente,
        umbral=UMBRAL_ACTIVACION,
        modo=MODO_AHORRO,
        estrategia=estrategia,
        titulo=f"Hola, {alias}: esto es lo que haría con tu excedente",
        mensaje=mensaje,
        pasos=pasos,
        ahorro_base=serie_base[-1],
        ahorro_optimizado=serie_optima[-1],
        serie=serie,
        maximo=maximo,
    )


def consejo_financiero(
    bd: Session,
    id_usuario: str,
    alias: str,
    excedente: Decimal | int | str,
    hoy: date | None = None,
) -> Consejo:
    """Genera el consejo financiero del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deudas y metas.
        alias: Nombre visible del usuario.
        excedente: Disponible consolidado del mes (quincenas + trabajos extras).
        hoy: Mes de partida de la comparación; por defecto, el actual.

    Returns:
        El `Consejo` activo con su recomendación y su gráfica, o uno inactivo si
        el excedente no supera el umbral.
    """
    monto = redondear_dinero(Decimal(str(excedente or CERO)))
    if monto <= UMBRAL_ACTIVACION:
        return Consejo(
            activo=False,
            alias=alias,
            excedente=monto,
            umbral=UMBRAL_ACTIVACION,
            titulo=f"Hola, {alias}",
            mensaje=(
                "El consejero se activa cuando tu excedente supera los "
                f"{formatear_cop(UMBRAL_ACTIVACION)}. Hoy tienes "
                f"{formatear_cop(monto)}: primero equilibra gastos y deudas."
            ),
        )

    referencia = hoy or date.today()
    etiquetas = [
        etiqueta
        for _anio, _mes, etiqueta in servicio_capacidad.meses_siguientes(
            referencia.year, referencia.month
        )
    ]
    estados = _estados(servicio_deudas.listar_deudas(bd, id_usuario))
    if estados:
        return _consejo_deuda(estados, monto, alias, etiquetas)
    return _consejo_ahorro(bd, id_usuario, monto, alias, etiquetas)
