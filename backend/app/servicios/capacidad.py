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
- SRS v1.9: los egresos se agrupan en las ocho categorías cerradas del catálogo.
  La categoría 8 («Créditos y Obligaciones») se alimenta con la cuota mensual de
  las deudas activas. Un gasto o deducción con `id_deuda` NO se suma como egreso
  propio: su dinero ya está dentro de esa categoría (anti-duplicación).

Este módulo no escribe en la base de datos: solo lee y calcula.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core import categorias as catalogo
from app.core.numeros import redondear_dinero
from app.modelos import Deuda, DeduccionFija, Gasto, PerfilFinanciero
from app.servicios import deducciones_fijas as servicio_deducciones
from app.servicios import deudas as servicio_deudas
from app.servicios import gastos as servicio_gastos
from app.servicios import quincenas as servicio_quincenas
from app.servicios import trabajos as servicio_trabajos
from app.servicios.gastos import valor_computable

CERO = Decimal("0")
CIEN = Decimal("100")
MESES_PROYECCION = 12
CUOTAS_POR_TERMINAR = 3
# SRS v1.8: reserva mensual de supervivencia. El dinero libre que no supere este
# monto no se ofrece para abonos ni metas; solo el remanente se considera
# capacidad real de abono.
BASE_MINIMA_LIQUIDEZ = Decimal("300000")
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
        base_minima: Parte del libre reservada como base mínima de liquidez.
        disponible_abono: Remanente del libre que sí puede abonarse o ahorrarse.
        categorias: Las ocho categorías cerradas con su valor, color y peso.
        arcos_categoria: Segmentos de la dona por categoría, con los colores
            exactos del catálogo, más la base mínima y lo disponible.
        base_global: Base de la dona global (sueldo + ingresos brutos de extras).
        gastos_globales: Suma de las categorías consolidadas de ambos orígenes.
        porcentaje_libre_global: Peso del libre sobre la base global.
        categorias_globales: Categorías sumadas de Mis Finanzas y Trabajos Extras.
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
    libre_salario: Decimal = CERO
    libre_extras: Decimal = CERO
    base_minima: Decimal = CERO
    disponible_abono: Decimal = CERO
    categorias: list[dict[str, object]] = field(default_factory=list)
    arcos_categoria: list[dict[str, object]] = field(default_factory=list)
    # SRS v4.5: campos de la dona global; la dona de Trabajos Extras no los usa.
    base_global: Decimal = CERO
    gastos_globales: Decimal = CERO
    porcentaje_libre_global: Decimal = CERO
    categorias_globales: list[dict[str, object]] = field(default_factory=list)


def base_minima_de(perfil: PerfilFinanciero | None) -> Decimal:
    """Devuelve la base mínima de liquidez configurada por el usuario.

    SRS §5: la reserva ya no es una constante global. El valor digitado en el
    onboarding manda; la constante de $300.000 solo sirve de respaldo para
    perfiles antiguos o ausentes. Nunca devuelve un número negativo.

    Args:
        perfil: Perfil financiero del usuario, o `None` si aún no existe.

    Returns:
        Monto mínimo a reservar, redondeado y no negativo.
    """
    if perfil is None:
        return BASE_MINIMA_LIQUIDEZ
    valor = getattr(perfil, "monto_minimo_liquidez", None)
    if valor is None:
        return BASE_MINIMA_LIQUIDEZ
    return max(redondear_dinero(Decimal(str(valor))), CERO)


def repartir_libre(
    libre: Decimal, base_minima: Decimal | None = None
) -> tuple[Decimal, Decimal]:
    """Separa el dinero libre entre la base mínima y el disponible para abonar.

    SRS v1.8 y §5: la base mínima de liquidez se reserva completa en cuanto el
    libre la alcance; si el libre es menor, todo él queda como base y no hay
    disponible. Un libre negativo no reserva nada. El monto reservado es el que
    configuró cada usuario (con respaldo de $300.000).

    Args:
        libre: Dinero que queda después de gastos y cuotas (puede ser negativo).
        base_minima: Monto a reservar; si se omite, se usa el respaldo global.

    Returns:
        Tupla `(base_minima, disponible_abono)` con ambos montos redondeados.
    """
    reserva = base_minima if base_minima is not None else BASE_MINIMA_LIQUIDEZ
    reserva = max(redondear_dinero(Decimal(str(reserva))), CERO)
    positivo = max(redondear_dinero(libre), CERO)
    base = min(positivo, reserva)
    disponible = max(redondear_dinero(positivo - reserva), CERO)
    return redondear_dinero(base), redondear_dinero(disponible)


def es_credito(descripcion: str) -> bool:
    """Indica si una deducción fija es un crédito (por ejemplo, una libranza).

    Ignora tildes y mayúsculas: «Crédito», «CREDITOS» y «credito» cuentan.

    Args:
        descripcion: Texto que escribió la usuaria.

    Returns:
        `True` si la descripción contiene la palabra crédito o créditos.
    """
    return catalogo.es_credito(descripcion)


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


def agrupar_por_categoria(
    gastos: list[Gasto],
    deducciones: list[DeduccionFija],
    cuota_obligaciones: Decimal,
    deducciones_ley: Decimal = CERO,
) -> dict[str, Decimal]:
    """Reparte los egresos entre las ocho categorías cerradas del catálogo.

    Los gastos y deducciones con categoría «Créditos y Obligaciones» se omiten:
    esa categoría se calcula sola con la cuota de las deudas activas. Así, un
    gasto o deducción vinculado mediante `id_deuda` no se suma dos veces.

    Args:
        gastos: Gastos fijos del mes, ya sin los vinculados a deudas.
        deducciones: Deducciones fijas vigentes, sin las vinculadas a deudas.
        cuota_obligaciones: Cuota mensual de las deudas activas y créditos de
            nómina heredados; alimenta la categoría 8.
        deducciones_ley: Salud y pensión del mes; no son categorías propias, por
            lo que se agrupan con «Otros Gastos Fijos» para que la dona cuadre.

    Returns:
        Diccionario con los ocho nombres canónicos y su total redondeado.
    """
    totales = {categoria.nombre: CERO for categoria in catalogo.CATEGORIAS}
    creditos_registrados = CERO
    for gasto in gastos:
        nombre = catalogo.normalizar_categoria(gasto.categoria)
        if nombre == catalogo.CATEGORIA_CREDITOS:
            # SRS v4.4: la cuota del gasto vinculado se cuenta aquí, una sola vez.
            creditos_registrados = redondear_dinero(
                creditos_registrados + servicio_gastos.valor_computable(gasto)
            )
            continue
        totales[nombre] = redondear_dinero(
            totales[nombre] + servicio_gastos.valor_computable(gasto)
        )
    for fija in deducciones:
        nombre = catalogo.normalizar_categoria(fija.categoria)
        if nombre == catalogo.CATEGORIA_CREDITOS:
            creditos_registrados = redondear_dinero(creditos_registrados + fija.valor)
            continue
        totales[nombre] = redondear_dinero(totales[nombre] + fija.valor)
    totales[catalogo.CATEGORIA_OTROS] = redondear_dinero(
        totales[catalogo.CATEGORIA_OTROS] + deducciones_ley
    )
    # SRS v4.4, sección 1: la dona se alimenta solo de gastos registrados en el
    # módulo. La cuota suelta de la tabla de deudas NO se dibuja; el compromiso
    # sigue reportándose en `deudas` para el semáforo.
    totales[catalogo.CATEGORIA_CREDITOS] = redondear_dinero(creditos_registrados)
    return totales


def resumen_categorias(
    totales: dict[str, Decimal],
    ingreso: Decimal,
) -> list[dict[str, object]]:
    """Prepara las ocho categorías para la plantilla y el JavaScript de la dona.

    Args:
        totales: Total por categoría calculado por `agrupar_por_categoria`.
        ingreso: Ingreso mensual, base de los porcentajes.

    Returns:
        Lista de ocho diccionarios con `nombre`, `color`, `valor`,
        `porcentaje` y `es_obligacion`, en el orden oficial del catálogo.
    """
    filas: list[dict[str, object]] = []
    for categoria in catalogo.CATEGORIAS:
        valor = redondear_dinero(totales.get(categoria.nombre, CERO))
        filas.append(
            {
                "nombre": categoria.nombre,
                "color": categoria.color,
                "valor": valor,
                "porcentaje": _porcentaje(valor, ingreso),
                "es_obligacion": categoria.nombre == catalogo.CATEGORIA_CREDITOS,
            }
        )
    return filas


def _arcos_categoria(
    totales: dict[str, Decimal],
    base: Decimal,
    disponible: Decimal,
    ingreso: Decimal,
) -> list[dict[str, object]]:
    """Construye los arcos de la dona por categoría con sus colores exactos.

    Args:
        totales: Total por categoría del catálogo.
        base: Parte del libre reservada como liquidez mínima.
        disponible: Remanente del libre.
        ingreso: Ingreso mensual; si no es positivo no hay dona.

    Returns:
        Arcos con etiqueta, valor, porcentaje, longitud, desplazamiento y color,
        con la base y lo disponible al final como en la dona clásica.
    """
    if ingreso <= CERO:
        return []

    candidatos: list[tuple[str, Decimal, str, str]] = []
    for categoria in catalogo.CATEGORIAS:
        valor = redondear_dinero(totales.get(categoria.nombre, CERO))
        if valor > CERO:
            candidatos.append(
                (categoria.nombre, valor, categoria.color, "valor-negativo")
            )
    if base > CERO:
        candidatos.append(
            ("Base mínima de liquidez", base, catalogo.COLOR_BASE_MINIMA, "valor-positivo")
        )
    if disponible > CERO:
        candidatos.append(
            ("Disponible para abonar", disponible, catalogo.COLOR_DINERO_LIBRE, "valor-positivo")
        )
    if not candidatos:
        return []

    # Si los egresos superan el ingreso, el dibujo se escala sobre el total para
    # que la circunferencia cierre y no aparezcan arcos mayores de 100 %.
    comprometido = redondear_dinero(sum((fila[1] for fila in candidatos), start=CERO))
    denominador = max(ingreso, comprometido)
    porcentajes = [_porcentaje(fila[1], denominador) for fila in candidatos]
    redondeados = [valor.quantize(Decimal("0.1")) for valor in porcentajes]
    diferencia = CIEN - sum(redondeados, start=CERO)
    if redondeados:
        mayor = max(range(len(redondeados)), key=lambda indice: porcentajes[indice])
        redondeados[mayor] += diferencia

    arcos: list[dict[str, object]] = []
    avance = CERO
    for (etiqueta, valor, color, clase), porcentaje in zip(candidatos, redondeados):
        arcos.append(
            {
                "etiqueta": etiqueta,
                "valor": redondear_dinero(valor),
                "porcentaje": porcentaje,
                "longitud": redondear_dinero(porcentaje),
                "desplazamiento": redondear_dinero(-avance),
                "color": color,
                "clase": clase,
            }
        )
        avance += porcentaje
    return arcos


def _arcos_categoria_global(
    totales_finanzas: dict[str, Decimal],
    totales_extras: dict[str, Decimal],
    libre: Decimal,
    libre_salario: Decimal,
    libre_extras: Decimal,
    ingreso_global: Decimal,
) -> list[dict[str, object]]:
    """Construye los arcos de la dona global con categorías homólogas sumadas.

    SRS v4.5, sección 1: una categoría presente en Mis Finanzas y en Trabajos
    Extras se dibuja como **una sola tajada** con el color canónico. El dinero
    libre de ambos orígenes también se dibuja una sola vez, como «Total libre».
    Cada arco lleva un `desglose` con el valor y el porcentaje de cada origen
    para que la leyenda pueda mostrar la trazabilidad jerárquica.

    Args:
        totales_finanzas: Valor de cada categoría en Mis Finanzas.
        totales_extras: Valor de cada categoría en Trabajos Extras.
        libre: Saldo libre consolidado de ambos orígenes.
        libre_salario: Parte del libre que viene de Mis Finanzas.
        libre_extras: Parte del libre que viene de Trabajos Extras.
        ingreso_global: Base global (sueldo + ingresos brutos de extras).

    Returns:
        Arcos con etiqueta, valor, porcentaje, color y desglose por origen.
    """
    if ingreso_global <= CERO:
        return []

    totales: dict[str, Decimal] = {}
    for categoria in catalogo.CATEGORIAS:
        nombre = categoria.nombre
        totales[nombre] = redondear_dinero(
            redondear_dinero(totales_finanzas.get(nombre, CERO))
            + redondear_dinero(totales_extras.get(nombre, CERO))
        )

    candidatos: list[tuple[str, Decimal, str, str]] = []
    for categoria in catalogo.CATEGORIAS:
        valor = totales[categoria.nombre]
        if valor > CERO:
            candidatos.append(
                (categoria.nombre, valor, categoria.color, "valor-negativo")
            )
    if libre > CERO:
        candidatos.append(
            ("Total libre", redondear_dinero(libre), catalogo.COLOR_DINERO_LIBRE, "valor-positivo")
        )
    if not candidatos:
        return []

    comprometido = redondear_dinero(sum((fila[1] for fila in candidatos), start=CERO))
    denominador = max(ingreso_global, comprometido)
    porcentajes = [_porcentaje(fila[1], denominador) for fila in candidatos]
    redondeados = [valor.quantize(Decimal("0.1")) for valor in porcentajes]
    diferencia = CIEN - sum(redondeados, start=CERO)
    if redondeados:
        mayor = max(range(len(redondeados)), key=lambda indice: porcentajes[indice])
        redondeados[mayor] += diferencia

    desgloses: dict[str, list[dict[str, object]]] = {}
    for categoria in catalogo.CATEGORIAS:
        nombre = categoria.nombre
        valor_finanzas = redondear_dinero(totales_finanzas.get(nombre, CERO))
        valor_extras = redondear_dinero(totales_extras.get(nombre, CERO))
        # Una sola origen no necesita sub-ítems: evitar redundancia en la leyenda.
        if valor_finanzas > CERO and valor_extras > CERO:
            desgloses[nombre] = [
                {
                    "origen": "Mis Finanzas",
                    "valor": valor_finanzas,
                    "porcentaje": _porcentaje(valor_finanzas, denominador),
                },
                {
                    "origen": "Trabajos Extras",
                    "valor": valor_extras,
                    "porcentaje": _porcentaje(valor_extras, denominador),
                },
            ]
    if libre > CERO:
        desgloses["Total libre"] = [
            {
                "origen": "Mis Finanzas",
                "valor": redondear_dinero(libre_salario),
                "porcentaje": _porcentaje(libre_salario, denominador),
            },
            {
                "origen": "Trabajos Extras",
                "valor": redondear_dinero(libre_extras),
                "porcentaje": _porcentaje(libre_extras, denominador),
            },
        ]

    arcos: list[dict[str, object]] = []
    avance = CERO
    for (etiqueta, valor, color, clase), porcentaje in zip(candidatos, redondeados):
        arcos.append(
            {
                "etiqueta": etiqueta,
                "valor": redondear_dinero(valor),
                "porcentaje": porcentaje,
                "longitud": redondear_dinero(porcentaje),
                "desplazamiento": redondear_dinero(-avance),
                "color": color,
                "clase": clase,
                "desglose": desgloses.get(etiqueta, []),
            }
        )
        avance += porcentaje
    return arcos


def _repartir_arcos(
    gastos: Decimal,
    deudas: Decimal,
    libre: Decimal,
    ingreso: Decimal,
    base_minima: Decimal | None = None,
) -> list[dict[str, object]]:
    """Construye los arcos de la dona de capacidad.

    Cuando gastos y deudas superan el ingreso, el dibujo se escala de forma
    proporcional para que la circunferencia cierre y el segmento libre quede en
    cero; así el gráfico no muestra arcos mayores que la vuelta completa.

    SRS v1.8 y §5: el dinero libre se parte en «Base mínima de liquidez» (hasta
    el monto configurado por el usuario) y «Disponible para abonar» (el
    remanente). Si el libre no alcanza la base, solo se dibuja el arco de la base.

    Args:
        gastos: Gastos fijos del mes.
        deudas: Cuota mensual de deudas.
        libre: Dinero restante (puede ser negativo).
        ingreso: Ingreso mensual consolidado.
        base_minima: Reserva configurada por el usuario (SRS §5).

    Returns:
        Lista de diccionarios con etiqueta, valor, porcentaje, longitud,
        desplazamiento, color para el SVG y `clase` de color de la cifra
        (verde para el dinero a favor, rojo para gastos y deudas).
    """
    if ingreso <= CERO:
        return []

    base, disponible = repartir_libre(libre, base_minima)
    gastos_positivos = max(gastos, CERO)
    deudas_positivas = max(deudas, CERO)

    # La decisión de escalar se toma con dinero, no con porcentajes redondeados:
    # dos decimales pueden sumar 100,01 y dibujar un arco libre inexistente.
    if gastos_positivos + deudas_positivas + base + disponible > ingreso:
        # El ingreso no alcanza: se reparte la vuelta completa entre gastos y
        # deudas sin dibujar un segmento libre que no existe.
        comprometido = gastos_positivos + deudas_positivas
        if comprometido > CERO:
            porcentaje_gastos = gastos_positivos / comprometido * CIEN
            porcentaje_deudas = CIEN - porcentaje_gastos
        else:
            porcentaje_gastos = CERO
            porcentaje_deudas = CERO
        porcentaje_base = CERO
        porcentaje_disponible = CERO
    else:
        porcentaje_gastos = _porcentaje(gastos_positivos, ingreso)
        porcentaje_deudas = _porcentaje(deudas_positivas, ingreso)
        porcentaje_base = _porcentaje(base, ingreso)
        porcentaje_disponible = _porcentaje(disponible, ingreso)

    # `clase` pinta la cifra de la leyenda con la paleta de referencia: rojo para
    # lo que sale del bolsillo (gastos y deudas) y verde para lo que queda a favor
    # (base mínima y disponible). El color del arco se conserva como guía visual.
    # Todos los colores salen del catálogo centralizado (SRS v3.4): dentro de
    # cada dona no se repite ningún HEX y la leyenda lee el mismo valor.
    candidatos = [
        ("Gastos fijos", gastos_positivos, porcentaje_gastos, catalogo.COLOR_VIVIENDA, "valor-negativo"),
        ("Cuota de deudas", deudas_positivas, porcentaje_deudas, catalogo.COLOR_CREDITOS, "valor-negativo"),
        ("Base mínima de liquidez", base, porcentaje_base, catalogo.COLOR_BASE_MINIMA, "valor-positivo"),
        ("Disponible para abonar", disponible, porcentaje_disponible, catalogo.COLOR_DINERO_LIBRE, "valor-positivo"),
    ]

    # Los porcentajes se muestran con un decimal; el redondeo de cada uno puede
    # dejar la suma en 99,9 o 100,1. El ajuste va al arco mayor para que la dona
    # cierre exactamente en 100 % sin mover los montos.
    visibles = [fila for fila in candidatos if fila[2] > CERO]
    if visibles:
        redondeados = [fila[2].quantize(Decimal("0.1")) for fila in visibles]
        diferencia = CIEN - sum(redondeados, start=CERO)
        mayor = max(range(len(visibles)), key=lambda indice: visibles[indice][2])
        redondeados[mayor] += diferencia
    else:
        redondeados = []

    arcos: list[dict[str, object]] = []
    avance = CERO
    for (etiqueta, valor, _pct, color, clase), porcentaje in zip(visibles, redondeados):
        longitud = redondear_dinero(porcentaje)
        arcos.append(
            {
                "etiqueta": etiqueta,
                "valor": redondear_dinero(valor),
                "porcentaje": porcentaje,
                "longitud": longitud,
                "desplazamiento": redondear_dinero(-avance),
                "color": color,
                "clase": clase,
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
    creditos: Decimal = CERO,
) -> list[dict[str, object]]:
    """Estima doce meses de cuota de deuda y saldo libre.

    Args:
        ingreso: Ingreso mensual consolidado que se mantiene constante.
        gastos: Gastos fijos mensuales que se mantienen constantes.
        deudas: Deudas activas del usuario.
        hoy: Mes de partida; por defecto, el mes actual.
        creditos: Deducciones fijas que son créditos; se cobran cada mes de la
            proyección, porque una deducción no tiene fecha de fin.

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
            + creditos
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


def capacidad_trabajos(
    bd: Session,
    id_usuario: str,
    anio: int,
    mes: int,
) -> Capacidad:
    """Calcula la dona de Trabajos Extras con solo sus datos.

    El ingreso son los valores de pago de trabajos extras del mes, cobrados o no; los gastos son los
    gastos fijos puestos dentro de esos trabajos. No cuentan el sueldo, las quincenas
    de Mis Finanzas ni las deudas.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los trabajos.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Un `Capacidad` con ingreso, gastos fijos, libre y arcos de la dona.
    """
    bloques = servicio_trabajos.pagos_del_mes(bd, id_usuario, anio, mes)
    ingreso = redondear_dinero(sum((bloque["ingreso"] for bloque in bloques), start=CERO))
    gastos = redondear_dinero(sum((bloque["gastos_total"] for bloque in bloques), start=CERO))
    libre = redondear_dinero(ingreso - gastos)
    # La base mínima de liquidez ($300.000) solo aplica al salario (Mis Finanzas).
    # Trabajos Extras no la reserva: todo el libre queda disponible para abonar.
    base = CERO
    disponible = max(libre, CERO)
    totales = agrupar_por_categoria(
        [
            gasto
            for bloque in bloques
            for periodo in bloque["periodos"]
            for gasto in periodo["gastos"]
        ],
        [],
        CERO,
    )
    return Capacidad(
        ingreso=ingreso,
        gastos=gastos,
        deudas=CERO,
        libre=libre,
        porcentaje_gastos=_porcentaje(gastos, ingreso),
        porcentaje_deudas=CERO,
        porcentaje_libre=_porcentaje(libre, ingreso),
        semaforo=ESTADO_VERDE,
        mensaje="",
        # Extras no reserva colchón: se pasa CERO para que los arcos coincidan
        # con el reparto del dataclass (SRS v4.4, respetado por SRS §5).
        arcos=_repartir_arcos(gastos, CERO, libre, ingreso, CERO),
        base_minima=base,
        disponible_abono=disponible,
        categorias=resumen_categorias(totales, ingreso),
        arcos_categoria=_arcos_categoria(totales, base, disponible, ingreso),
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

    # Trabajos extras: entran por su valor de pago y salen con sus gastos fijos.
    # Su libre se muestra aparte del libre del salario.
    bloques = servicio_trabajos.pagos_del_mes(bd, id_usuario, anio, mes)
    # SRS v4.5, sección 1: la dona global usa los ingresos BRUTOS de Trabajos
    # Extras como base y suma también sus gastos. El Consejero sigue tomando el
    # libre consolidado, que es algebraicamente el mismo de la v4.4.
    ingresos_extras = redondear_dinero(
        sum((bloque["ingreso"] for bloque in bloques), start=CERO)
    )
    libre_extras = servicio_trabajos.libre_neto_mes(bd, id_usuario, anio, mes)
    ingreso = redondear_dinero(ingreso_base + libre_extras)
    base_global = redondear_dinero(ingreso_base + ingresos_extras)
    gastos_extras = [
        gasto
        for bloque in bloques
        for periodo in bloque["periodos"]
        for gasto in periodo["gastos"]
    ]

    # SRS v4.4: las deducciones del módulo cuentan aunque estén vinculadas a una
    # deuda; su valor es la cuota y ya no se añade como tajada suelta.
    fijas = servicio_deducciones.listar_vigentes(bd, id_usuario)
    creditos = servicio_deducciones.total_creditos_sin_vinculo(bd, id_usuario)
    # Todos los gastos fijos del módulo, incluidos los vinculados a deuda: su
    # cuota se cuenta una sola vez aquí, dentro de su categoría.
    gastos_modelo = servicio_gastos.listar_gastos(bd, id_usuario, anio, mes)

    deducciones_fijas_total = redondear_dinero(
        sum((fija.valor for fija in fijas), start=CERO)
    )
    deducciones_ley = redondear_dinero(sum((fila.deducciones for fila in resumen), start=CERO))
    gastos = redondear_dinero(
        sum((valor_computable(gasto) for gasto in gastos_modelo), start=CERO)
        + deducciones_ley
        + deducciones_fijas_total
    )
    # El semáforo sigue informando de la cuota comprometida, pero esa cuota ya
    # no se suma como tajada suelta: las categorías cuadran con `gastos`.
    cuota_deudas = redondear_dinero(
        servicio_deudas.resumen_deudas(bd, id_usuario)["cuota_mensual"] + creditos
    )
    deudas = list(servicio_deudas.listar_deudas(bd, id_usuario))
    libre = redondear_dinero(ingreso - gastos)
    libre_salario = redondear_dinero(libre - libre_extras)
    # SRS §5: la reserva la elige cada usuario en su perfil; los perfiles sin
    # valor conservan los $300.000 históricos mediante `base_minima_de`.
    reserva = base_minima_de(perfil)
    base, disponible = repartir_libre(libre, reserva)

    # SRS v4.5: las deducciones de crédito también alimentan la categoría 8 del
    # módulo, para que el desglose por origen de la dona global cuadre con los
    # gastos realmente registrados.
    totales_finanzas = agrupar_por_categoria(
        gastos_modelo,
        fijas,
        CERO,
        deducciones_ley,
    )
    # Los créditos vinculados de Trabajos Extras se cuentan en su categoría,
    # igual que en la dona individual (que no se modifica).
    totales_extras = agrupar_por_categoria(gastos_extras, [], CERO)
    totales = {
        nombre: redondear_dinero(
            redondear_dinero(totales_finanzas.get(nombre, CERO))
            + redondear_dinero(totales_extras.get(nombre, CERO))
        )
        for nombre in (categoria.nombre for categoria in catalogo.CATEGORIAS)
    }
    gastos_globales = redondear_dinero(sum(totales.values(), start=CERO))
    categorias_globales = resumen_categorias(totales, base_global)
    # Las categorías de Mis Finanzas se conservan para los consumidores de la
    # v4.4; la dona global usa `categorias_globales`.
    categorias = resumen_categorias(totales_finanzas, ingreso)
    arcos_categoria = _arcos_categoria_global(
        totales_finanzas,
        totales_extras,
        libre,
        libre_salario,
        libre_extras,
        base_global,
    )

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
        # Informativo/semáforo: las cuotas NO se suman como tajada suelta en la
        # dona (SRS v4.4), pero el campo sigue reportando el compromiso mensual.
        deudas=cuota_deudas,
        libre=libre,
        porcentaje_gastos=_porcentaje(gastos, ingreso),
        porcentaje_deudas=porcentaje_deudas,
        porcentaje_libre=_porcentaje(libre, ingreso),
        semaforo=estado,
        mensaje=_mensaje_semaforo(estado, porcentaje_deudas),
        arcos=_repartir_arcos(gastos, CERO, libre, ingreso, reserva),
        por_terminar=deudas_por_terminar(bd, id_usuario),
        # La proyección mantiene constantes los gastos y aplica el calendario de
        # cada deuda: cuando una termina, su cuota deja de pesar en ese mes.
        proyeccion=proyeccion_capacidad(ingreso, gastos, deudas, hoy, creditos),
        libre_salario=libre_salario,
        libre_extras=libre_extras,
        base_minima=base,
        disponible_abono=disponible,
        categorias=categorias,
        arcos_categoria=arcos_categoria,
        # SRS v4.5: base y categorías globales para la dona consolidada.
        base_global=base_global,
        gastos_globales=gastos_globales,
        porcentaje_libre_global=_porcentaje(libre, base_global),
        categorias_globales=categorias_globales,
    )
