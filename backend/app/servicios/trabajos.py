"""Ingresos independientes ("Trabajos Extras").

Responsabilidad
---------------
- Registrar contratos de trabajo por fuera del salario con sus datos básicos:
  descripción, cliente, valor por pago, tipo de contrato y frecuencia.
- Generar, de forma idempotente, un pago por mes o dos pagos por mes (quincenas)
  dentro de la ventana del contrato.
- Guardar esos pagos como filas de `gastos` con `id_trabajo` para reutilizar la
  misma fila con check de los gastos fijos. `gastos.listar_gastos` los excluye,
  de modo que **no** restan del sueldo ni de las quincenas.
- Calcular el neto cobrado del mes, que el diagnóstico de «Gastos y Presupuesto»
  suma al dinero disponible.
- Eliminar el contrato y sus pagos en cascada.

Reglas
------
- `valor` es el monto **de cada pago**: mensual = un pago; quincenal = dos pagos
  (día 15 y día 30, ajustado al último día del mes).
- Contrato `INDEFINIDO`: ventana móvil de 12 meses que se extiende al abrir el
  módulo. Contrato `TERMINO_FIJO`: termina en `fecha_fin`.
- Un pago generado nunca se borra desde la interfaz: la × lo inhabilita 15 días
  (igual que un pago saltado de meta) para que no vuelva a generarse.
- Los trabajos anteriores a la SRS v1.7 se migran como término fijo de un solo
  mes, para no inventar ingresos recurrentes.

La tabla `trabajos_extras` está documentada en `diccionario_datos.md` §12.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import Gasto, TrabajoExtra
from app.servicios.gastos import valor_computable

CERO = Decimal("0")
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
CATEGORIA_TRABAJO = "Trabajo extra"
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
# Validación
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
) -> TrabajoExtra:
    """Registra un trabajo extra como contrato recurrente.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del registro.
        descripcion: Trabajo o servicio realizado.
        valor: Monto pactado **por cada pago**; no puede ser negativo.
        fecha: Fecha de inicio del contrato.
        cliente: Persona o empresa que contrató.
        tipo_contrato: `INDEFINIDO` o `TERMINO_FIJO`.
        frecuencia: `MENSUAL` (un pago) o `QUINCENAL` (dos pagos).
        fecha_fin: Final del contrato; obligatorio en término fijo.
        fecha_pago: Fecha del primer pago; si falta se usa la fecha de inicio.

    Returns:
        El trabajo persistido.

    Raises:
        ValueError: Si la descripción está vacía, el valor es negativo o
            inválido, el catálogo no es válido o las fechas se contradicen.
    """
    descripcion_limpia = descripcion.strip()
    if not descripcion_limpia:
        raise ValueError("La descripción del trabajo es obligatoria.")

    monto = redondear_dinero(parsear_monto(str(valor)))
    if monto < CERO:
        raise ValueError("El valor del trabajo no puede ser negativo.")

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
    """Elimina un trabajo extra y todos sus pagos generados.

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
    for pago in bd.scalars(select(Gasto).where(Gasto.id_trabajo == id_trabajo)):
        bd.delete(pago)
    bd.delete(trabajo)
    bd.commit()
    return True


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
        Pagos del mes ordenados por quincena.
    """
    inicio, fin = _rango_del_mes(anio, mes)
    consulta = (
        select(Gasto)
        .where(
            Gasto.id_trabajo == id_trabajo,
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
    no crea historia anterior: los pagos del mes visible son los que el usuario
    ve. En un contrato indefinido la ventana es móvil de doce meses; un término
    fijo se detiene en `fecha_fin`.

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
        partes = [
            (quincena, _fecha_con_dia(anio, mes, dia))
            for quincena, dia in DIAS_QUINCENA
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
            valor=trabajo.valor,
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
        Lista de diccionarios con el contrato, sus pagos del mes y sus totales
        `cobrado` y `pendiente`.
    """
    bloques: list[dict[str, object]] = []
    for trabajo in listar_trabajos(bd, id_usuario):
        pagos = _pagos_del_mes(bd, trabajo.id_trabajo, anio, mes)
        if not pagos:
            continue
        cobrado = redondear_dinero(
            sum(
                (valor_computable(pago) for pago in pagos if pago.pagado),
                start=CERO,
            )
        )
        pendiente = redondear_dinero(
            sum(
                (valor_computable(pago) for pago in pagos if not pago.pagado),
                start=CERO,
            )
        )
        bloques.append(
            {
                "trabajo": trabajo,
                "pagos": pagos,
                "cobrado": cobrado,
                "pendiente": pendiente,
            }
        )
    return bloques


def extras_cobrados_mes(bd: Session, id_usuario: str, anio: int, mes: int) -> Decimal:
    """Suma el neto cobrado de trabajos extras en un mes.

    Es el monto que el diagnóstico de «Gastos y Presupuesto» suma al saldo libre.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los trabajos.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Total cobrado, redondeado a pesos.
    """
    inicio, fin = _rango_del_mes(anio, mes)
    pagos = bd.scalars(
        select(Gasto).where(
            Gasto.id_usuario == id_usuario,
            Gasto.id_trabajo.is_not(None),
            Gasto.pagado.is_(True),
            Gasto.fecha >= inicio,
            Gasto.fecha < fin,
        )
    )
    return redondear_dinero(
        sum((valor_computable(pago) for pago in pagos), start=CERO)
    )


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
    if anio is not None and mes is not None:
        inicio, fin = _rango_del_mes(anio, mes)
        consulta = select(Gasto).where(
            Gasto.id_usuario == id_usuario,
            Gasto.id_trabajo.is_not(None),
            Gasto.fecha >= inicio,
            Gasto.fecha < fin,
        )
    else:
        consulta = select(Gasto).where(
            Gasto.id_usuario == id_usuario,
            Gasto.id_trabajo.is_not(None),
        )
    pagos = list(bd.scalars(consulta))
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
