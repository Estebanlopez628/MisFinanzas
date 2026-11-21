"""Ingresos independientes ("Trabajos Extras").

Responsabilidad
---------------
- Registrar contratos de trabajo por fuera del salario: descripción, cliente, valor
  del pago, tipo de contrato y frecuencia.
- Generar, de forma idempotente, el pago del mes (mensual) o los dos pagos de la
  quincena 1 y 2 (quincenal) dentro de la ventana del contrato.
- Guardar esos pagos como filas de `gastos` con `id_trabajo` y categoría
  `CATEGORIA_TRABAJO`, para reutilizar la fila con check de los gastos fijos.
- Registrar los **gastos fijos del propio trabajo** (también `gastos` con
  `id_trabajo`, pero con otra categoría). Solo se ven en Trabajos Extras.
- Calcular el disponible de cada periodo: cobrado menos gastos fijos del trabajo.
  Ese disponible es el que suma el diagnóstico de «Gastos y Presupuesto».
- Eliminar el contrato con sus pagos y gastos en cascada.

Reglas
------
- Ningún gasto con `id_trabajo` aparece en las quincenas ni en los totales de
  Mis Finanzas: `gastos.listar_gastos` los excluye.
- Mensual: el valor del pago es el monto del mes. Solo se pregunta fecha de inicio
  y fecha del primer pago (y fecha final si es término fijo).
- Quincenal: el valor del pago es el total del mes. Si la usuaria conoce los
  porcentajes de cada quincena, los escribe (suman 100 %). Si no, escribe el valor
  de una quincena y el sistema calcula la otra y los porcentajes.
- Contrato `INDEFINIDO`: ventana móvil de 12 meses que se extiende al abrir el
  módulo. Contrato `TERMINO_FIJO`: termina en `fecha_fin`.
- Un pago generado nunca se borra desde la interfaz: la × lo inhabilita 15 días.
- Los trabajos anteriores a la SRS v1.7 se migran como término fijo de un solo mes.

La tabla `trabajos_extras` está documentada en `diccionario_datos.md` §12.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.categorias import CATEGORIA_TRABAJO
from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto, parsear_porcentaje
from app.modelos import Gasto, TrabajoExtra
from app.servicios.gastos import crear_gasto, valor_computable

CERO = Decimal("0")
CIEN = Decimal("100")
ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_COBRADO = "COBRADO"
ESTADOS_VALIDOS = (ESTADO_PENDIENTE, ESTADO_COBRADO)

CONTRATO_INDEFINIDO = "INDEFINIDO"
CONTRATO_TERMINO_FIJO = "TERMINO_FIJO"
CONTRATOS_VALIDOS = (CONTRATO_INDEFINIDO, CONTRATO_TERMINO_FIJO)

FRECUENCIA_MENSUAL = "MENSUAL"
FRECUENCIA_QUINCENAL = "QUINCENAL"
FRECUENCIAS_VALIDAS = (FRECUENCIA_MENSUAL, FRECUENCIA_QUINCENAL)

# Ventana móvil de un contrato indefinido (SRS v1.7). Al abrir el módulo se
# extiende hasta cubrir doce meses desde el mes visible.
MESES_VENTANA = 12
# Días de cada quincena para un contrato quincenal.
DIAS_QUINCENA = ((1, 15), (2, 30))
# Categoría de las filas que son pagos del contrato. Los gastos fijos del trabajo
# llevan otra categoría y `id_trabajo`, pero nunca esta. La constante vive en
# `core.categorias` para que la migración de datos la respete (ADR-60).
PREFIJO_TRABAJO = "Trabajo · "


# ---------------------------------------------------------------------------
# Utilidades de calendario
# ---------------------------------------------------------------------------


def _posicion(anio: int, mes: int) -> int:
    """Convierte un mes en un número consecutivo para compararlos.

    Args:
        anio: Año.
        mes: Mes (1–12).

    Returns:
        Índice mensual que crece de uno en uno.
    """
    return anio * 12 + (mes - 1)


def _desde_posicion(posicion: int) -> tuple[int, int]:
    """Convierte un índice mensual de vuelta a `(anio, mes)`.

    Args:
        posicion: Índice devuelto por `_posicion`.

    Returns:
        Tupla `(anio, mes)`.
    """
    return posicion // 12, posicion % 12 + 1


def _rango_del_mes(anio: int, mes: int) -> tuple[date, date]:
    """Calcula el primer día del mes y el primer día del mes siguiente.

    Args:
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Tupla `(inicio, fin_exclusivo)` para filtrar fechas.
    """
    inicio = date(anio, mes, 1)
    fin = date(anio + (mes // 12), (mes % 12) + 1, 1)
    return inicio, fin


def _fecha_con_dia(anio: int, mes: int, dia: int) -> date:
    """Construye una fecha ajustando el día al último del mes.

    Evita desbordes como «31 de febrero»: si el día pedido no existe en el mes,
    se usa el último día disponible (28, 29 o 30).

    Args:
        anio: Año de la fecha.
        mes: Mes (1–12).
        dia: Día deseado (1–31).

    Returns:
        Fecha válida dentro del mes.
    """
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(dia, ultimo))


# ---------------------------------------------------------------------------
# Validación y reparto
# ---------------------------------------------------------------------------


def _normalizar_contrato(valor: str | None) -> str:
    """Valida el tipo de contrato de un trabajo extra.

    Args:
        valor: Texto del formulario.

    Returns:
        `INDEFINIDO` o `TERMINO_FIJO`.

    Raises:
        ValueError: Si el valor no pertenece al catálogo.
    """
    limpio = (valor or CONTRATO_INDEFINIDO).strip().upper()
    if limpio not in CONTRATOS_VALIDOS:
        raise ValueError(
            "El tipo de contrato debe ser Indefinido o Término fijo."
        )
    return limpio


def _normalizar_frecuencia(valor: str | None) -> str:
    """Valida la frecuencia de pago de un trabajo extra.

    Args:
        valor: Texto del formulario.

    Returns:
        `MENSUAL` o `QUINCENAL`.

    Raises:
        ValueError: Si el valor no pertenece al catálogo.
    """
    limpio = (valor or FRECUENCIA_MENSUAL).strip().upper()
    if limpio not in FRECUENCIAS_VALIDAS:
        raise ValueError("La frecuencia debe ser Mensual o Quincenal.")
    return limpio


def _normalizar_quincena(valor: int | str | None) -> int:
    """Valida una quincena (1 o 2) escrita en un formulario.

    Args:
        valor: `1` o `2` (texto o número).

    Returns:
        `1` o `2`.

    Raises:
        ValueError: Si el valor no es 1 ni 2.
    """
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError) as error:
        raise ValueError("Elige la quincena 1 o la quincena 2.") from error
    if numero not in (1, 2):
        raise ValueError("Elige la quincena 1 o la quincena 2.")
    return numero


def _monto_opcional(valor: str | int | Decimal | None) -> Decimal | None:
    """Convierte un monto opcional en `Decimal` a pesos.

    Args:
        valor: Texto del formulario o número; vacío significa «no escrito».

    Returns:
        Monto redondeado a pesos, o `None` si no se escribió.

    Raises:
        ValueError: Si el texto no es un monto válido o es negativo.
    """
    if valor is None or str(valor).strip() == "":
        return None
    monto = redondear_dinero(parsear_monto(str(valor)))
    if monto < CERO:
        raise ValueError("Los montos no pueden ser negativos.")
    return monto


def _porcentaje_opcional(valor: str | None) -> Decimal | None:
    """Convierte un porcentaje escrito por la usuaria.

    Args:
        valor: Texto del formulario (acepta «60», «60 %» y «60,5»); vacío
            significa «no escrito».

    Returns:
        Porcentaje entre 0 y 100, o `None` si no se escribió.

    Raises:
        ValueError: Si no es un número o está fuera de 0–100.
    """
    if valor is None or str(valor).strip() == "":
        return None
    numero = parsear_porcentaje(valor, "El porcentaje")
    if numero < CERO or numero > CIEN:
        raise ValueError("El porcentaje debe estar entre 0 y 100.")
    return numero


def reparto_por_porcentajes(
    total: Decimal, porcentaje_1: Decimal, porcentaje_2: Decimal
) -> tuple[Decimal, Decimal]:
    """Reparte el total mensual según los porcentajes que conoce la usuaria.

    La quincena 2 es el resto del total, así las dos suman exacto aunque haya
    centavos de redondeo.

    Args:
        total: Valor del pago mensual (las dos quincenas).
        porcentaje_1: Porcentaje de la quincena 1.
        porcentaje_2: Porcentaje de la quincena 2.

    Returns:
        Tupla `(quincena_1, quincena_2)` en pesos.

    Raises:
        ValueError: Si los porcentajes no suman 100 %.
    """
    if porcentaje_1 + porcentaje_2 != CIEN:
        raise ValueError("Los porcentajes de las dos quincenas deben sumar 100 %.")
    quincena_1 = redondear_dinero(total * porcentaje_1 / CIEN)
    return quincena_1, redondear_dinero(total - quincena_1)


def reparto_quincenal(
    total: Decimal, quincena_digitada: int, valor_quincena: Decimal
) -> tuple[Decimal, Decimal]:
    """Calcula las dos quincenas cuando la usuaria escribe el valor de una.

    La otra quincena es el total menos la escrita. Así se obtiene también su
    porcentaje, que la vista muestra junto a cada tabla.

    Args:
        total: Valor del pago mensual (las dos quincenas).
        quincena_digitada: `1` o `2`, la quincena a la que corresponde el valor.
        valor_quincena: Valor escrito para esa quincena.

    Returns:
        Tupla `(quincena_1, quincena_2)` en pesos.

    Raises:
        ValueError: Si la quincena escrita supera el total.
    """
    if valor_quincena > total:
        raise ValueError("El valor de la quincena no puede superar el valor del pago del mes.")
    otra = redondear_dinero(total - valor_quincena)
    if quincena_digitada == 1:
        return valor_quincena, otra
    return otra, valor_quincena


def porcentaje_del_total(valor: Decimal | None, total: Decimal) -> Decimal | None:
    """Calcula qué porcentaje del total representa un valor.

    Args:
        valor: Monto de una quincena.
        total: Valor del pago mensual.

    Returns:
        Porcentaje con un decimal, o `None` si no hay datos suficientes.
    """
    if valor is None or total <= CERO:
        return None
    return (valor / total * CIEN).quantize(Decimal("0.1"))


def valor_del_pago(trabajo: TrabajoExtra, quincena: int | None) -> Decimal:
    """Indica cuánto vale un pago generado de un contrato.

    Args:
        trabajo: Contrato dueño del pago.
        quincena: `1` o `2` en contratos quincenales; `None` en mensuales.

    Returns:
        Monto del pago; cae en `valor` si el contrato no tiene montos por quincena.
    """
    if trabajo.frecuencia == FRECUENCIA_QUINCENAL:
        if quincena == 1 and trabajo.valor_quincena_1 is not None:
            return trabajo.valor_quincena_1
        if quincena == 2 and trabajo.valor_quincena_2 is not None:
            return trabajo.valor_quincena_2
    return trabajo.valor


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------


def crear_trabajo(
    bd: Session,
    id_usuario: str,
    descripcion: str,
    valor: Decimal | str | int | float,
    fecha: date,
    cliente: str | None = None,
    *,
    tipo_contrato: str | None = CONTRATO_INDEFINIDO,
    frecuencia: str | None = FRECUENCIA_MENSUAL,
    fecha_fin: date | None = None,
    fecha_pago: date | None = None,
    conoce_porcentaje: bool = False,
    fecha_pago_quincena_2: date | None = None,
    porcentaje_quincena_1: str | None = None,
    porcentaje_quincena_2: str | None = None,
    quincena_digitada: int | str | None = None,
    valor_quincena: str | None = None,
) -> TrabajoExtra:
    """Registra un trabajo extra como contrato recurrente.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro.
        descripcion: Trabajo o servicio realizado.
        valor: Valor del pago. Mensual: el monto del mes. Quincenal: el total del mes.
        fecha: Fecha de inicio del contrato.
        cliente: Persona o empresa que contrató.
        tipo_contrato: `INDEFINIDO` o `TERMINO_FIJO`.
        frecuencia: `MENSUAL` (un pago) o `QUINCENAL` (dos pagos).
        fecha_fin: Final del contrato; obligatorio en término fijo.
        fecha_pago: Fecha del primer pago; si falta se usa la fecha de inicio.
        conoce_porcentaje: En quincenal, `True` si la usuaria escribe los porcentajes.
        porcentaje_quincena_1: Porcentaje de la quincena 1 (si conoce el reparto).
        porcentaje_quincena_2: Porcentaje de la quincena 2 (si conoce el reparto).
        quincena_digitada: Quincena a la que corresponde `valor_quincena`.
        valor_quincena: Valor escrito de una de las quincenas (si no conoce el reparto).

    Returns:
        El trabajo persistido.

    Raises:
        ValueError: Si faltan datos obligatorios, un monto o porcentaje es inválido,
            el catálogo no es válido o las fechas se contradicen.
    """
    descripcion_limpia = descripcion.strip()
    if not descripcion_limpia:
        raise ValueError("La descripción del trabajo es obligatoria.")

    monto = _monto_opcional(valor)
    if monto is None or monto <= CERO:
        raise ValueError("Escribe el valor del pago.")

    contrato = _normalizar_contrato(tipo_contrato)
    ritmo = _normalizar_frecuencia(frecuencia)
    primer_pago = fecha_pago or fecha
    if primer_pago < fecha:
        raise ValueError(
            "La fecha de pago no puede ser anterior al inicio del contrato."
        )

    final: date | None = None
    if contrato == CONTRATO_TERMINO_FIJO:
        if fecha_fin is None:
            raise ValueError("Un contrato a término fijo necesita fecha final.")
        if fecha_fin < primer_pago:
            raise ValueError(
                "La fecha final no puede ser anterior a la fecha de pago."
            )
        final = fecha_fin
    elif fecha_fin is not None and fecha_fin < fecha:
        raise ValueError("La fecha final no puede ser anterior al inicio.")

    quincena_1: Decimal | None = None
    quincena_2: Decimal | None = None
    segunda_fecha: date | None = None
    if ritmo == FRECUENCIA_QUINCENAL:
        if fecha_pago_quincena_2 is None:
            raise ValueError("Escribe la fecha de pago de la quincena 2.")
        if fecha_pago_quincena_2 < fecha:
            raise ValueError("La fecha de pago de la quincena 2 no puede ser anterior al inicio.")
        segunda_fecha = fecha_pago_quincena_2
        if conoce_porcentaje:
            porcentaje_1 = _porcentaje_opcional(porcentaje_quincena_1)
            porcentaje_2 = _porcentaje_opcional(porcentaje_quincena_2)
            if porcentaje_1 is None or porcentaje_2 is None:
                raise ValueError("Escribe los porcentajes de la quincena 1 y de la 2.")
            quincena_1, quincena_2 = reparto_por_porcentajes(monto, porcentaje_1, porcentaje_2)
        else:
            digitada = _normalizar_quincena(quincena_digitada)
            escrita = _monto_opcional(valor_quincena)
            if escrita is None:
                raise ValueError("Escribe el valor de una de las quincenas.")
            quincena_1, quincena_2 = reparto_quincenal(monto, digitada, escrita)

    trabajo = TrabajoExtra(
        id_usuario=id_usuario,
        descripcion=descripcion_limpia[:150],
        cliente=(cliente or "").strip()[:100] or None,
        valor=monto,
        fecha=fecha,
        tipo_contrato=contrato,
        frecuencia=ritmo,
        fecha_fin=final,
        fecha_pago=primer_pago,
        valor_quincena_1=quincena_1,
        valor_quincena_2=quincena_2,
        fecha_pago_quincena_2=segunda_fecha,
        estado=ESTADO_PENDIENTE,
    )
    bd.add(trabajo)
    bd.commit()
    bd.refresh(trabajo)
    return trabajo


def listar_trabajos(bd: Session, id_usuario: str) -> list[TrabajoExtra]:
    """Lista los trabajos extra del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los registros.

    Returns:
        Lista ordenada por fecha de inicio descendente.
    """
    consulta = (
        select(TrabajoExtra)
        .where(TrabajoExtra.id_usuario == id_usuario)
        .order_by(TrabajoExtra.fecha.desc(), TrabajoExtra.descripcion)
    )
    return list(bd.scalars(consulta))


def cambiar_estado(
    bd: Session, id_usuario: str, id_trabajo: str, estado: str
) -> TrabajoExtra:
    """Marca un trabajo como pendiente o cobrado a nivel de contrato.

    Se conserva por compatibilidad con el flujo anterior. El cobro real se
    registra pago a pago con el check de la fila.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro.
        id_trabajo: Trabajo a modificar.
        estado: `PENDIENTE` o `COBRADO`.

    Returns:
        El trabajo actualizado.

    Raises:
        ValueError: Si el estado no es válido o el trabajo no pertenece al
            usuario.
    """
    estado_limpio = estado.strip().upper()
    if estado_limpio not in ESTADOS_VALIDOS:
        raise ValueError("El estado debe ser PENDIENTE o COBRADO.")

    trabajo = bd.get(TrabajoExtra, id_trabajo)
    if trabajo is None or trabajo.id_usuario != id_usuario:
        raise ValueError("El trabajo no existe.")

    trabajo.estado = estado_limpio
    bd.commit()
    bd.refresh(trabajo)
    return trabajo


def eliminar_trabajo(bd: Session, id_usuario: str, id_trabajo: str) -> bool:
    """Elimina un trabajo extra con sus pagos y sus gastos fijos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro.
        id_trabajo: Trabajo a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    trabajo = bd.get(TrabajoExtra, id_trabajo)
    if trabajo is None or trabajo.id_usuario != id_usuario:
        return False
    # Borrado explícito además de la cascada de la base: deja la operación
    # correcta incluso en motores donde las claves foráneas no están activas.
    for fila in bd.scalars(select(Gasto).where(Gasto.id_trabajo == id_trabajo)):
        bd.delete(fila)
    bd.delete(trabajo)
    bd.commit()
    return True


# ---------------------------------------------------------------------------
# Gastos fijos del trabajo (solo viven en Trabajos Extras)
# ---------------------------------------------------------------------------


def gastos_fijos_trabajo(bd: Session, id_trabajo: str) -> list[Gasto]:
    """Lista los gastos fijos que la usuaria registró dentro de un trabajo.

    Args:
        bd: Sesión de base de datos.
        id_trabajo: Contrato dueño de los gastos.

    Returns:
        Gastos fijos ordenados por descripción; nunca incluye los pagos.
    """
    consulta = (
        select(Gasto)
        .where(Gasto.id_trabajo == id_trabajo, Gasto.categoria != CATEGORIA_TRABAJO)
        .order_by(Gasto.descripcion)
    )
    return list(bd.scalars(consulta))


def crear_gasto_trabajo(
    bd: Session,
    id_usuario: str,
    id_trabajo: str,
    categoria: str,
    descripcion: str,
    valor: str | int | float | Decimal,
    quincena: int | str | None = None,
    id_deuda: str | None = None,
) -> Gasto:
    """Registra un gasto fijo dentro de un trabajo extra.

    El gasto se guarda con `id_trabajo`, así que no aparece en las quincenas de Mis
    Finanzas. En un contrato mensual el gasto es del mes completo (sin quincena); en
    uno quincenal debe indicar la quincena 1 o 2.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del trabajo.
        id_trabajo: Trabajo al que pertenece el gasto.
        categoria: Categoría libre.
        descripcion: Nombre del gasto fijo.
        valor: Monto del gasto.
        quincena: `1` o `2` en contratos quincenales.
        id_deuda: Deuda mensual que paga el gasto; vacío si no aplica.

    Returns:
        El gasto persistido.

    Raises:
        ValueError: Si el trabajo no existe o los datos del gasto no son válidos.
    """
    trabajo = bd.get(TrabajoExtra, id_trabajo)
    if trabajo is None or trabajo.id_usuario != id_usuario:
        raise ValueError("El trabajo no existe.")
    periodo = _normalizar_quincena(quincena) if trabajo.frecuencia == FRECUENCIA_QUINCENAL else None
    gasto = crear_gasto(
        bd,
        id_usuario,
        categoria,
        descripcion,
        valor,
        date.today(),
        es_fijo=True,
        quincena=periodo,
        id_deuda=id_deuda,
    )
    gasto.id_trabajo = id_trabajo
    gasto.check_visible = False
    bd.commit()
    bd.refresh(gasto)
    return gasto


# ---------------------------------------------------------------------------
# Pagos generados
# ---------------------------------------------------------------------------


def _pagos_del_mes(
    bd: Session, id_trabajo: str, anio: int, mes: int
) -> list[Gasto]:
    """Lista los pagos de un trabajo en un mes concreto.

    Args:
        bd: Sesión de base de datos.
        id_trabajo: Contrato dueño de los pagos.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Pagos del mes ordenados por quincena (sin los gastos fijos del trabajo).
    """
    inicio, fin = _rango_del_mes(anio, mes)
    consulta = (
        select(Gasto)
        .where(
            Gasto.id_trabajo == id_trabajo,
            Gasto.categoria == CATEGORIA_TRABAJO,
            Gasto.fecha >= inicio,
            Gasto.fecha < fin,
        )
        .order_by(Gasto.quincena)
    )
    return list(bd.scalars(consulta))


def _meses_a_generar(
    trabajo: TrabajoExtra, anio: int, mes: int
) -> list[tuple[int, int]]:
    """Determina los meses del contrato que deben tener pagos.

    La generación arranca en el mes visible (o en el primer pago si es futuro) y
    no crea historia anterior. En un contrato indefinido la ventana es móvil de doce
    meses; un término fijo se detiene en `fecha_fin`.

    Args:
        trabajo: Contrato persistido.
        anio: Año del mes visible.
        mes: Mes visible (1–12).

    Returns:
        Lista de tuplas `(anio, mes)` ordenadas.
    """
    ancla = trabajo.fecha_pago or trabajo.fecha
    inicio = _posicion(ancla.year, ancla.month)
    visible = _posicion(anio, mes)
    primero = max(inicio, visible)
    if trabajo.tipo_contrato == CONTRATO_TERMINO_FIJO and trabajo.fecha_fin:
        fin = _posicion(trabajo.fecha_fin.year, trabajo.fecha_fin.month)
    else:
        fin = max(primero + MESES_VENTANA - 1, visible + MESES_VENTANA - 1)
    if fin < primero:
        return []
    return [_desde_posicion(posicion) for posicion in range(primero, fin + 1)]


def _crear_pagos_del_mes(
    bd: Session, trabajo: TrabajoExtra, anio: int, mes: int
) -> list[Gasto]:
    """Crea los pagos de un mes con la frecuencia del contrato.

    El día se ajusta al último del mes cuando el pago cae en un día inexistente
    (por ejemplo, 30 de febrero). En frecuencia mensual, el día se toma de
    `fecha_pago`; en quincenal, se usan los días 15 y 30.

    Args:
        bd: Sesión de base de datos.
        trabajo: Contrato dueño de los pagos.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Pagos creados (sin confirmar; el llamador hace `commit`).
    """
    ancla = trabajo.fecha_pago or trabajo.fecha
    if trabajo.frecuencia == FRECUENCIA_QUINCENAL:
        # Con las dos fechas escritas se usan sus días; un contrato anterior sin
        # segunda fecha conserva los días 15 y 30.
        dias = DIAS_QUINCENA
        if trabajo.fecha_pago_quincena_2 is not None and trabajo.fecha_pago is not None:
            dias = ((1, trabajo.fecha_pago.day), (2, trabajo.fecha_pago_quincena_2.day))
        partes = [
            (quincena, _fecha_con_dia(anio, mes, dia))
            for quincena, dia in dias
        ]
    else:
        partes = [(None, _fecha_con_dia(anio, mes, ancla.day))]

    creados: list[Gasto] = []
    for quincena, fecha_pago in partes:
        # Un término fijo no paga después de su último día.
        if trabajo.fecha_fin is not None and fecha_pago > trabajo.fecha_fin:
            fecha_pago = trabajo.fecha_fin
        pago = Gasto(
            id_usuario=trabajo.id_usuario,
            categoria=CATEGORIA_TRABAJO,
            descripcion=f"{PREFIJO_TRABAJO}{trabajo.descripcion}"[:150],
            valor=valor_del_pago(trabajo, quincena),
            es_fijo=True,
            fecha=fecha_pago,
            quincena=quincena,
            id_trabajo=trabajo.id_trabajo,
            pagado=False,
            check_visible=True,
        )
        bd.add(pago)
        creados.append(pago)
    return creados


def asegurar_pagos_trabajos(
    bd: Session, id_usuario: str, anio: int, mes: int
) -> int:
    """Genera los pagos que falten de todos los trabajos del usuario.

    Es idempotente por mes: un mes que ya tiene pagos no se vuelve a generar, de
    modo que una × (que inhabilita el pago sin borrarlo) no se deshace.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los trabajos.
        anio: Año del mes visible.
        mes: Mes visible (1–12).

    Returns:
        Cantidad de pagos creados.
    """
    creados = 0
    for trabajo in listar_trabajos(bd, id_usuario):
        for anio_mes, mes_mes in _meses_a_generar(trabajo, anio, mes):
            if _pagos_del_mes(bd, trabajo.id_trabajo, anio_mes, mes_mes):
                continue
            creados += len(_crear_pagos_del_mes(bd, trabajo, anio_mes, mes_mes))
    if creados:
        bd.commit()
    return creados


def _periodos_del_trabajo(
    bd: Session, trabajo: TrabajoExtra, pagos: list[Gasto]
) -> list[dict[str, object]]:
    """Arma las tablas de un contrato: pago, gastos fijos y disponible por periodo.

    Mensual: una sola tabla («Pago mensual»). Quincenal: una tabla por quincena. El
    disponible de cada periodo es lo cobrado menos sus gastos fijos.

    Args:
        bd: Sesión de base de datos.
        trabajo: Contrato a mostrar.
        pagos: Pagos del contrato en el mes visible.

    Returns:
        Lista de diccionarios con `etiqueta`, `quincena`, `valor`, `porcentaje`,
        `pago`, `gastos`, `gastos_total`, `cobrado` y `disponible`.
    """
    fijos = gastos_fijos_trabajo(bd, trabajo.id_trabajo)
    if trabajo.frecuencia == FRECUENCIA_QUINCENAL:
        definiciones: list[tuple[int | None, str]] = [
            (1, "Quincena 1 · día 15"),
            (2, "Quincena 2 · día 30"),
        ]
    else:
        definiciones = [(None, "Pago mensual")]

    periodos: list[dict[str, object]] = []
    for quincena, etiqueta in definiciones:
        valor = valor_del_pago(trabajo, quincena)
        pago = next((fila for fila in pagos if fila.quincena == quincena), None)
        gastos_periodo = [gasto for gasto in fijos if gasto.quincena == quincena]
        gastos_total = redondear_dinero(
            sum((valor_computable(gasto) for gasto in gastos_periodo), start=CERO)
        )
        # El ingreso del periodo es el valor del pago, cobrado o no. Un pago saltado
        # con la × vale cero porque ya no se espera (`valor_computable`).
        ingreso = redondear_dinero(valor_computable(pago)) if pago is not None else redondear_dinero(valor)
        cobrado = (
            valor_computable(pago) if pago is not None and pago.pagado else CERO
        )
        periodos.append(
            {
                "etiqueta": etiqueta,
                "quincena": quincena,
                "valor": valor,
                "porcentaje": porcentaje_del_total(valor, trabajo.valor)
                if quincena is not None
                else None,
                "pago": pago,
                "gastos": gastos_periodo,
                "gastos_total": gastos_total,
                "ingreso": ingreso,
                "cobrado": redondear_dinero(cobrado),
                "disponible": redondear_dinero(ingreso - gastos_total),
            }
        )
    return periodos


def pagos_del_mes(
    bd: Session, id_usuario: str, anio: int, mes: int
) -> list[dict[str, object]]:
    """Agrupa los pagos del mes por contrato para la vista.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los trabajos.
        anio: Año del mes visible.
        mes: Mes visible (1–12).

    Returns:
        Lista de diccionarios con el contrato, sus periodos (`periodos`), y los
        totales `cobrado`, `pendiente` y `disponible` del contrato en el mes.
    """
    bloques: list[dict[str, object]] = []
    for trabajo in listar_trabajos(bd, id_usuario):
        pagos = _pagos_del_mes(bd, trabajo.id_trabajo, anio, mes)
        if not pagos:
            continue
        periodos = _periodos_del_trabajo(bd, trabajo, pagos)
        cobrado = redondear_dinero(sum((periodo["cobrado"] for periodo in periodos), start=CERO))
        pendiente = redondear_dinero(
            sum(
                (valor_computable(pago) for pago in pagos if not pago.pagado),
                start=CERO,
            )
        )
        disponible = redondear_dinero(sum((periodo["disponible"] for periodo in periodos), start=CERO))
        ingreso_total = redondear_dinero(sum((periodo["ingreso"] for periodo in periodos), start=CERO))
        gastos_total = redondear_dinero(sum((periodo["gastos_total"] for periodo in periodos), start=CERO))
        bloques.append(
            {
                "trabajo": trabajo,
                "periodos": periodos,
                "cobrado": cobrado,
                "pendiente": pendiente,
                "disponible": disponible,
                "ingreso": ingreso_total,
                "gastos_total": gastos_total,
                "saldo_bolsillo": redondear_dinero(ingreso_total - gastos_total),
            }
        )
    return bloques


def extras_cobrados_mes(bd: Session, id_usuario: str, anio: int, mes: int) -> Decimal:
    """Suma el disponible de trabajos extras en un mes.

    Es lo cobrado menos los gastos fijos del trabajo. El diagnóstico de «Gastos y
    Presupuesto» suma este saldo al dinero libre del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los trabajos.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Disponible total, redondeado a pesos.
    """
    bloques = pagos_del_mes(bd, id_usuario, anio, mes)
    return redondear_dinero(sum((bloque["disponible"] for bloque in bloques), start=CERO))


def resumen_trabajos(
    bd: Session, id_usuario: str, anio: int | None = None, mes: int | None = None
) -> dict[str, Decimal | int]:
    """Calcula los totales de los pagos de trabajos extras.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los registros.
        anio: Año a resumir; si falta junto con `mes`, se resume todo.
        mes: Mes a resumir (1–12).

    Returns:
        Diccionario con total cobrado, total pendiente y conteos de pagos.
    """
    filtros = [
        Gasto.id_usuario == id_usuario,
        Gasto.id_trabajo.is_not(None),
        Gasto.categoria == CATEGORIA_TRABAJO,
    ]
    if anio is not None and mes is not None:
        inicio, fin = _rango_del_mes(anio, mes)
        filtros += [Gasto.fecha >= inicio, Gasto.fecha < fin]
    pagos = list(bd.scalars(select(Gasto).where(*filtros)))
    cobrados = [pago for pago in pagos if pago.pagado]
    pendientes = [pago for pago in pagos if not pago.pagado]
    return {
        "cobrado": redondear_dinero(
            sum((valor_computable(pago) for pago in cobrados), start=CERO)
        ),
        "pendiente": redondear_dinero(
            sum((valor_computable(pago) for pago in pendientes), start=CERO)
        ),
        "cobrados": len(cobrados),
        "pendientes": len(pendientes),
        "contratos": len(listar_trabajos(bd, id_usuario)),
    }


# ---------------------------------------------------------------------------
# Reparación de datos heredados (ADR-60)
# ---------------------------------------------------------------------------


def reparar_pagos_duplicados(bd: Session, *, simular: bool = False) -> dict[str, int]:
    """Restaura los pagos de trabajo reclasificados y elimina sus duplicados.

    Una versión anterior de la migración de categorías convirtió los pagos de
    «Trabajos Extras» (categoría técnica «Trabajo extra») a «Otros Gastos Fijos».
    Como la idempotencia de `asegurar_pagos_trabajos()` los busca por esa
    categoría, cada arranque generó una copia nueva. Esta función:

    1. Devuelve a «Trabajo extra» las filas con `id_trabajo` y descripción con el
       prefijo `Trabajo · ` que quedaron en otra categoría.
    2. Conserva un solo pago por contrato, año, mes y quincena, y elimina el
       resto. Se prefiere el pago cobrado y, entre los pendientes, el que no esté
       inhabilitado con la ×.

    Es idempotente: ejecutarla de nuevo no cambia nada.

    Args:
        bd: Sesión de base de datos.
        simular: Si es `True`, calcula el resultado pero no guarda los cambios.

    Returns:
        Diccionario con la cantidad de filas `restaurados` y `eliminados`.
    """
    restaurados = 0
    reclasificados = bd.scalars(
        select(Gasto).where(
            Gasto.id_trabajo.is_not(None),
            Gasto.categoria != CATEGORIA_TRABAJO,
        )
    ).all()
    for gasto in reclasificados:
        # Los gastos fijos reales del trabajo también tienen `id_trabajo`, pero
        # su descripción la escribe la usuaria y no lleva el prefijo del pago.
        if not (gasto.descripcion or "").startswith(PREFIJO_TRABAJO):
            continue
        gasto.categoria = CATEGORIA_TRABAJO
        restaurados += 1
    # El agrupamiento de abajo consulta la base: se fuerza el volcado de las
    # categorías recién restauradas para que entren en el mismo lote.
    if restaurados:
        bd.flush()

    pagos = bd.scalars(
        select(Gasto).where(
            Gasto.id_trabajo.is_not(None),
            Gasto.categoria == CATEGORIA_TRABAJO,
        )
    ).all()
    grupos: dict[tuple[str | None, int, int, int | None], list[Gasto]] = {}
    for pago in pagos:
        clave = (pago.id_trabajo, pago.fecha.year, pago.fecha.month, pago.quincena)
        grupos.setdefault(clave, []).append(pago)

    eliminados = 0
    for filas in grupos.values():
        if len(filas) <= 1:
            continue
        filas.sort(
            key=lambda gasto: (
                not gasto.pagado,
                gasto.inhabilitado_hasta is not None,
                gasto.id_gasto,
            )
        )
        for duplicado in filas[1:]:
            bd.delete(duplicado)
            eliminados += 1

    if simular:
        bd.rollback()
    elif restaurados or eliminados:
        bd.commit()
    return {"restaurados": restaurados, "eliminados": eliminados}
