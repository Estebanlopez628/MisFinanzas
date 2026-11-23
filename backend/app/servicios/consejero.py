"""Consejero financiero del excedente mensual (SRS v1.8).

Responsabilidad
---------------
- Decidir si el dinero libre del mes supera la base mínima de liquidez
  ($300.000) y, solo con el remanente, sugerir abonos o metas.
- En deudas, ordenar por **liberación de flujo de caja**: primero la deuda que
  el excedente pueda cancelar completa y que deje más cuotas por delante (la de
  12 meses antes que la de 5); si ninguna se puede cancelar de una vez, la de
  menor saldo, que es la que se cierra antes.
- Entregar la serie mensual «base frente a optimizado» para la gráfica.

Reglas:
- Sin intereses: el saldo de cada deuda baja con su cuota mínima y con el
  excedente. No se prometen ahorros de intereses que el sistema no puede
  comprobar.
- La base mínima de liquidez se descuenta antes de calcular el excedente: si el
  libre son $500.000, quedan $200.000 para abonar.
- Si el libre no supera la base, el consejo se apaga con un mensaje que invita a
  crear una meta de emergencia con lo mínimo que se pueda ahorrar.
- En modo ahorro, «base» acumula solo lo ya planeado en metas y «optimizado»
  suma el excedente. Si no hay metas, se sugiere crear una.
- Es una proyección educativa, no una promesa: supone ingreso y cuotas estables.

Este módulo no escribe en la base de datos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
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
# SRS v1.8: el consejero solo opina sobre el dinero que supera la reserva de
# supervivencia; por debajo de ella no se sugiere abonar ni proyectar.
UMBRAL_ACTIVACION = servicio_capacidad.BASE_MINIMA_LIQUIDEZ

MODO_DEUDA = "DEUDA"
MODO_AHORRO = "AHORRO"

ESTRATEGIA_FLUJO = "FLUJO_DE_CAJA"
ESTRATEGIA_METAS = "METAS"
ESTRATEGIA_SIN_METAS = "SIN_METAS"


@dataclass(frozen=True)
class Consejo:
    """Recomendación del consejero y su comparación a doce meses.

    Attributes:
        activo: `True` solo si el dinero libre supera la base mínima.
        alias: Nombre visible del usuario para el saludo.
        excedente: Dinero disponible para abonar (libre − base mínima).
        umbral: Base mínima de liquidez que debe superarse.
        modo: `DEUDA` si hay pasivos, `AHORRO` si no los hay.
        estrategia: `FLUJO_DE_CAJA`, `METAS` o `SIN_METAS`.
        titulo: Saludo con el alias.
        mensaje: Recomendación principal en lenguaje natural.
        pasos: Acciones concretas sugeridas.
        deuda_objetivo: Acreedor que concentra el excedente, si aplica.
        meses_base: Meses para quedar libre de deudas pagando solo lo mínimo.
        meses_optimizado: Meses con el excedente aplicado.
        cuota_liberada: Cuota mensual que deja de pesarte al cerrar deudas.
        ahorro_base: Ahorro acumulado sin aplicar el excedente.
        ahorro_optimizado: Ahorro acumulado aplicando el excedente.
        meses_liquidacion: Mes en que la deuda llega a cero, si ocurre.
        serie: Doce filas con la comparación y sus alturas de barra.
        maximo: Valor mayor de la serie, base de las alturas relativas.
        cierre: Datos de la gráfica unificada «Comparativa de cierre de deuda».
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
    meses_base: int | None = None
    meses_optimizado: int | None = None
    cuota_liberada: Decimal = CERO
    ahorro_base: Decimal = CERO
    ahorro_optimizado: Decimal = CERO
    meses_liquidacion: int | None = None
    serie: list[dict[str, object]] = field(default_factory=list)
    maximo: Decimal = CERO
    cierre: dict[str, object] = field(default_factory=dict)


@dataclass
class _EstadoDeuda:
    """Deuda con su saldo vivo durante una simulación.

    Attributes:
        deuda: Registro original, del que se toma el acreedor.
        saldo: Capital pendiente en el mes simulado.
        saldo_inicial: Capital pendiente al iniciar la simulación.
        cuota: Cuota mensual equivalente.
        cuotas: Cuotas que faltan, expresadas en meses de pago.
    """

    deuda: Deuda
    saldo: Decimal
    saldo_inicial: Decimal = CERO
    cuota: Decimal = CERO
    cuotas: int = 1


def _cuotas_mensuales(deuda: Deuda) -> int:
    """Expresa las cuotas pendientes en meses de pago.

    Una deuda quincenal tiene dos vencimientos por mes; para comparar plazos con
    las mensuales se redondea hacia arriba la mitad de sus cuotas.

    Args:
        deuda: Deuda consultada.

    Returns:
        Número de meses de pago que le quedan; al menos uno si sigue activa.
    """
    pendientes = max(int(deuda.cuotas_pendientes or 0), 0)
    if deuda.periodicidad == servicio_deudas.PERIODICIDAD_QUINCENAL:
        return max(int(math.ceil(pendientes / 2)), 1)
    return max(pendientes, 1)


def _estados(deudas: list[Deuda]) -> list[_EstadoDeuda]:
    """Construye los estados simulables de las deudas activas.

    Args:
        deudas: Deudas del usuario.

    Returns:
        Lista con saldo, cuota mensual y plazo de cada deuda vigente.
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
                saldo_inicial=saldo,
                cuota=cuota,
                cuotas=_cuotas_mensuales(deuda),
            )
        )
    return estados


def _ordenar(estados: list[_EstadoDeuda], excedente: Decimal) -> list[_EstadoDeuda]:
    """Ordena las deudas para liberar cuotas lo antes posible.

    SRS v1.8: si el excedente alcanza para cancelar una deuda completa, se ataca
    primero la que tenga más cuotas por delante (la de 12 meses antes que la de
    5), porque libera la cuota durante más tiempo. Si no alcanza para ninguna,
    se empieza por la de menor saldo, que es la que se cierra antes.

    Args:
        estados: Deudas simulables.
        excedente: Dinero mensual disponible para abonar.

    Returns:
        Lista ordenada de la primera a la última deuda a atacar.
    """
    cancelables = [estado for estado in estados if estado.saldo <= excedente]
    resto = [estado for estado in estados if estado.saldo > excedente]
    cancelables.sort(key=lambda estado: (-estado.cuotas, -estado.saldo))
    resto.sort(key=lambda estado: (estado.saldo, -estado.cuotas))
    return cancelables + resto


def _simular(
    estados: list[_EstadoDeuda],
    excedente: Decimal,
    aplicar_excedente: bool = True,
) -> tuple[list[Decimal], int | None, Decimal, list[dict[str, object]]]:
    """Simula doce meses de pagos sobre un conjunto de deudas.

    Sin intereses: cada mes se paga la cuota mínima de todas las deudas y, si se
    aplica el excedente, el remanente se dirige a la primera de la lista hasta
    agotarlo.

    Args:
        estados: Deudas de partida; no se modifican.
        excedente: Dinero extra que se aplica cada mes.
        aplicar_excedente: `False` simula solo las cuotas mínimas (base).

    Returns:
        Tupla `(saldo_restante_por_mes, mes_liquidacion, cuota_liberada,
        detalle)`. El detalle lista nombre, saldo y cuota de cada deuda que
        cierra, para que el Consejero pueda explicar la suma sin intereses.
    """
    copia = [
        _EstadoDeuda(
            estado.deuda, estado.saldo, estado.saldo_inicial, estado.cuota, estado.cuotas
        )
        for estado in estados
    ]
    orden = _ordenar(copia, excedente) if aplicar_excedente else []
    cerradas: set[str] = set()
    detalle: list[dict[str, object]] = []
    liberada = CERO
    serie: list[Decimal] = []
    liquidacion: int | None = None

    for avance in range(MESES):
        for estado in copia:
            if estado.saldo <= CERO:
                continue
            pago = min(estado.cuota, estado.saldo)
            estado.saldo = redondear_dinero(estado.saldo - pago)
            if estado.saldo <= CERO and estado.deuda.id_deuda not in cerradas:
                cerradas.add(estado.deuda.id_deuda)
                liberada = redondear_dinero(liberada + estado.cuota)
                detalle.append(
                    {
                        "nombre": estado.deuda.acreedor,
                        "saldo": estado.saldo_inicial,
                        "cuota": estado.cuota,
                    }
                )

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
                if estado.saldo <= CERO and estado.deuda.id_deuda not in cerradas:
                    cerradas.add(estado.deuda.id_deuda)
                    liberada = redondear_dinero(liberada + estado.cuota)
                    detalle.append(
                        {
                            "nombre": estado.deuda.acreedor,
                            "saldo": estado.saldo_inicial,
                            "cuota": estado.cuota,
                        }
                    )

        total = redondear_dinero(sum((estado.saldo for estado in copia), start=CERO))
        serie.append(total)
        if liquidacion is None and total <= CERO:
            liquidacion = avance + 1

    return serie, liquidacion, liberada, detalle


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


# SRS v4.13: nombres completos en español, con inicial mayúscula, en web y móvil.
_MESES_COMPLETOS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def _fecha_cierre(referencia: date, offset_meses: int) -> str:
    """Devuelve «Mes Año» con el nombre completo del mes (SRS v4.13).

    Args:
        referencia: Mes de partida de la proyección.
        offset_meses: Cuántos meses después cae el cierre.

    Returns:
        Etiqueta como «Mayo 2030».
    """
    indice = (referencia.month - 1 + max(0, offset_meses)) % 12
    anio = referencia.year + (referencia.month - 1 + max(0, offset_meses)) // 12
    return f"{_MESES_COMPLETOS[indice]} {anio}"


def _datos_cierre(
    estados: list[_EstadoDeuda],
    consejo: Consejo,
    etiquetas: list[str],
    referencia: date,
    cuotas_liberadas_detalle: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Prepara la proyección de la gráfica unificada de cierre de deuda.

    Args:
        estados: Deudas activas con su saldo y cuota vigentes.
        consejo: Consejo ya calculado, cuya serie se reutiliza.
        etiquetas: Rótulos de los doce meses.
        referencia: Mes de partida.
        cuotas_liberadas_detalle: Deudas que cierran con su saldo y cuota.

    Returns:
        Diccionario con puntos, hitos y totales para la plantilla SVG.
    """
    deuda_inicial = redondear_dinero(sum((estado.saldo for estado in estados), start=CERO))
    cuota = redondear_dinero(sum((estado.cuota for estado in estados), start=CERO))
    extra = redondear_dinero(consejo.excedente)
    serie_base = [fila["base"] for fila in consejo.serie]
    serie_optima = [fila["optimizado"] for fila in consejo.serie]

    meses_base = math.ceil(deuda_inicial / cuota) if cuota > CERO else 0
    ritmo_optimo = cuota + extra
    meses_optimo = math.ceil(deuda_inicial / ritmo_optimo) if ritmo_optimo > CERO else 0
    meses_ahorrados = max(0, meses_base - meses_optimo)
    ahorro_saldo = max(CERO, redondear_dinero(serie_base[-1] - serie_optima[-1]))

    mes_libre: int | None = None
    if deuda_inicial > CERO:
        for indice, saldo in enumerate(serie_optima):
            if saldo <= CERO:
                mes_libre = indice
                break

    puntos: list[dict[str, object]] = []
    for indice, _etiqueta in enumerate(etiquetas):
        posicion = referencia.month - 1 + indice
        puntos.append(
            {
                "index": indice,
                "mes": _MESES_COMPLETOS[posicion % 12],
                "anio": str(referencia.year + posicion // 12),
                "base": serie_base[indice],
                "optimizado": serie_optima[indice],
            }
        )

    # SRS v4.13: solo cifras verificables. La reducción a 12 meses es la
    # diferencia real entre ambas curvas; nunca se inventan intereses.
    return {
        "deuda_inicial": deuda_inicial,
        "saldo_actual": deuda_inicial,
        "cuota_mensual": cuota,
        "excedente_mensual": extra,
        "puntos": puntos,
        "mes_libre_index": mes_libre,
        "meses_minimo": meses_base,
        "meses_con_excedente": meses_optimo,
        "meses_ahorrados": meses_ahorrados,
        "reduccion_capital_12m": ahorro_saldo,
        "ahorro_mostrado": ahorro_saldo,
        "fecha_cierre_base": _fecha_cierre(referencia, meses_base),
        "fecha_cierre_opt": _fecha_cierre(referencia, meses_optimo),
        "deudas_detalle": [
            {
                "nombre": estado.deuda.acreedor,
                "saldo": estado.saldo_inicial,
                "cuota": estado.cuota,
            }
            for estado in estados
        ],
        "cuotas_liberadas_detalle": cuotas_liberadas_detalle or [],
        "costo_total_base": deuda_inicial,
        "costo_total_opt": deuda_inicial,
    }


def _consejo_deuda(
    estados: list[_EstadoDeuda],
    excedente: Decimal,
    alias: str,
    etiquetas: list[str],
    referencia: date | None = None,
) -> Consejo:
    """Recomienda a qué deuda dirigir el excedente para liberar la cuota.

    Args:
        estados: Deudas activas del usuario.
        excedente: Dinero disponible después de la base mínima de liquidez.
        alias: Nombre visible para el saludo.
        etiquetas: Rótulos de los doce meses.
        referencia: Mes de partida de la proyección.

    Returns:
        El consejo configurado en modo deuda.
    """
    serie_base, _liquidacion_base, _liberada_base, _detalle_base = _simular(
        estados, excedente, aplicar_excedente=False
    )
    serie_optima, _liquidacion, liberada, detalle_cerradas = _simular(
        estados, excedente
    )
    orden = _ordenar(estados, excedente)
    objetivo = orden[0]
    cancela_completa = objetivo.saldo <= excedente

    if cancela_completa:
        criterio = (
            f"es la que puedes cancelar completa y te libera la cuota por más "
            f"tiempo ({objetivo.cuotas} cuota(s) por delante)"
        )
    else:
        criterio = "es la de menor saldo y la cierras antes"

    # SRS v4.13: plazos exactos hasta saldo cero, sin la frase «más de 12 meses».
    referencia_efectiva = referencia or date.today()
    deuda_inicial = redondear_dinero(sum((e.saldo for e in estados), start=CERO))
    cuota_total = redondear_dinero(sum((e.cuota for e in estados), start=CERO))
    ritmo = redondear_dinero(cuota_total + excedente)
    meses_minimo = math.ceil(deuda_inicial / cuota_total) if cuota_total > CERO else 0
    meses_excedente = math.ceil(deuda_inicial / ritmo) if ritmo > CERO else 0
    fecha_minimo = _fecha_cierre(referencia_efectiva, meses_minimo)
    fecha_excedente = _fecha_cierre(referencia_efectiva, meses_excedente)
    meses_antes = max(0, meses_minimo - meses_excedente)

    serie, maximo = _serie_comparada(serie_base, serie_optima, etiquetas)
    objetivo_detalle = (
        f"saldo: {formatear_cop(objetivo.saldo_inicial)} · "
        f"cuota: {formatear_cop(objetivo.cuota)}/mes"
    )

    pasos = [
        f"Concentra el excedente de {formatear_cop(excedente)} en "
        f"{objetivo.deuda.acreedor} ({objetivo_detalle}): {criterio}."
    ]
    if len(orden) > 1:
        siguientes = "; ".join(
            f"{estado.deuda.acreedor} (saldo: {formatear_cop(estado.saldo_inicial)} · "
            f"cuota: {formatear_cop(estado.cuota)}/mes)"
            for estado in orden[1:3]
        )
        pasos.append(f"Cuando esa deuda cierre, sigue con {siguientes}.")
    if liberada > CERO:
        desglose = "; ".join(
            f"{fila['nombre']} {formatear_cop(fila['cuota'])}"
            for fila in detalle_cerradas
        )
        detalle_texto = f" ({desglose})" if desglose else ""
        pasos.append(
            f"Al cerrar esas deudas liberarás {formatear_cop(liberada)} de cuota "
            f"mensual para tus metas{detalle_texto}."
        )
    pasos.append(
        f"Pagando solo lo mínimo quedarías libre en {meses_minimo} meses "
        f"({fecha_minimo}); con tu excedente bajas a {meses_excedente} meses "
        f"({fecha_excedente})."
    )

    mensaje = (
        f"{alias}, con {formatear_cop(excedente)} de excedente te conviene atacar "
        f"primero {objetivo.deuda.acreedor} ({objetivo_detalle}). Con ese ritmo "
        f"quedarías libre de deudas en {meses_excedente} meses ({fecha_excedente}), "
        f"{meses_antes} meses antes que pagando solo lo mínimo "
        f"({meses_minimo} meses · {fecha_minimo})."
    )

    resultado = Consejo(
        activo=True,
        alias=alias,
        excedente=excedente,
        umbral=UMBRAL_ACTIVACION,
        modo=MODO_DEUDA,
        estrategia=ESTRATEGIA_FLUJO,
        titulo=f"Hola, {alias}: esto es lo que haría con tu excedente",
        mensaje=mensaje,
        pasos=pasos,
        deuda_objetivo=objetivo.deuda.acreedor,
        meses_base=meses_minimo,
        meses_optimizado=meses_excedente,
        cuota_liberada=liberada,
        meses_liquidacion=meses_excedente,
        serie=serie,
        maximo=maximo,
    )
    cierre = _datos_cierre(
        estados,
        resultado,
        etiquetas,
        referencia_efectiva,
        detalle_cerradas,
    )
    return replace(resultado, cierre=cierre)


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
        excedente: Dinero disponible después de la base mínima de liquidez.
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
        excedente: Dinero libre del mes (quincenas + trabajos extras − gastos).
        hoy: Mes de partida de la comparación; por defecto, el actual.

    Returns:
        El `Consejo` activo con su recomendación y su gráfica, o uno inactivo si
        el dinero libre no supera la base mínima de liquidez.
    """
    libre = redondear_dinero(Decimal(str(excedente or CERO)))
    disponible = max(redondear_dinero(libre - UMBRAL_ACTIVACION), CERO)
    if libre <= UMBRAL_ACTIVACION:
        return Consejo(
            activo=False,
            alias=alias,
            excedente=CERO,
            umbral=UMBRAL_ACTIVACION,
            titulo=f"Hola, {alias}",
            mensaje=(
                "Tienes el valor de la base mínima de liquidez. No puedo "
                "ofrecerte un consejo financiero sobre tus deudas en este "
                "momento, pero podrías empezar creando una meta para crear un "
                "colchón de emergencias, con lo mínimo que puedas ahorrar."
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
        return _consejo_deuda(estados, disponible, alias, etiquetas, referencia)
    return _consejo_ahorro(bd, id_usuario, disponible, alias, etiquetas)
