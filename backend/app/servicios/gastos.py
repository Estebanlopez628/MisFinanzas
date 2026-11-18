"""Gastos y presupuesto del usuario.

Responsabilidad
---------------
Registrar gastos fijos y variables, agruparlos por categoría y sumar el total de
un mes. La tabla `gastos` está definida en `diccionario_datos.md` §7 y se usa
para calcular el dinero disponible después de la nómina.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import Gasto

CERO = Decimal("0")


def valor_computable(gasto: Gasto, hoy: date | None = None) -> Decimal:
    """Devuelve el monto que cuenta en los totales del gasto.

    SRS v1.6: un pago marcado cuenta por lo realmente pagado (`monto_pagado`).
    Un pago saltado con × cuenta `0` mientras su plazo de inhabilitación no
    venza; después vuelve a contar como gasto normal.

    Args:
        gasto: Gasto a evaluar.
        hoy: Fecha de referencia; por defecto, hoy.

    Returns:
        Monto que se resta del saldo de la quincena.
    """
    if gasto.pagado:
        return gasto.monto_pagado if gasto.monto_pagado is not None else gasto.valor
    referencia = hoy or date.today()
    if gasto.inhabilitado_hasta is not None and gasto.inhabilitado_hasta > referencia:
        return CERO
    return gasto.valor


def crear_gasto(
    bd: Session,
    id_usuario: str,
    categoria: str,
    descripcion: str,
    valor: Decimal | str | int | float,
    fecha: date,
    es_fijo: bool = False,
    quincena: int | str | None = None,
) -> Gasto:
    """Registra un gasto del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        categoria: Categoría libre (vivienda, transporte, ocio…).
        descripcion: Detalle legible.
        valor: Monto del gasto; no puede ser negativo.
        fecha: Fecha en la que se causó.
        es_fijo: `True` para gastos recurrentes.
        quincena: `1` o `2` para gastos fijos de una quincena; `None` o `0`
            para gastos del mes completo.

    Returns:
        El gasto persistido.

    Raises:
        ValueError: Si la categoría o la descripción están vacías, el valor es
            negativo o inválido, o la quincena no es 1 ni 2.
    """
    categoria_limpia = categoria.strip()
    descripcion_limpia = descripcion.strip()
    if not categoria_limpia:
        raise ValueError("La categoría del gasto es obligatoria.")
    if not descripcion_limpia:
        raise ValueError("La descripción del gasto es obligatoria.")

    monto = redondear_dinero(parsear_monto(str(valor)))
    if monto < CERO:
        raise ValueError("El valor del gasto no puede ser negativo.")

    quincena_normalizada = _normalizar_quincena(quincena)

    gasto = Gasto(
        id_usuario=id_usuario,
        categoria=categoria_limpia[:60],
        descripcion=descripcion_limpia[:150],
        valor=monto,
        es_fijo=es_fijo,
        fecha=fecha,
        quincena=quincena_normalizada,
    )
    bd.add(gasto)
    bd.commit()
    bd.refresh(gasto)
    return gasto


def _normalizar_quincena(quincena: int | str | None) -> int | None:
    """Convierte la quincena de un formulario al valor persistido.

    Args:
        quincena: `1`, `2`, `0`, cadena vacía o `None`.

    Returns:
        `1`, `2` o `None` (mes completo).

    Raises:
        ValueError: Si el valor no es una quincena válida.
    """
    if quincena in (None, "", 0, "0"):
        return None
    try:
        numero = int(quincena)
    except (TypeError, ValueError) as error:
        raise ValueError("La quincena del gasto debe ser 1 o 2.") from error
    if numero not in (1, 2):
        raise ValueError("La quincena del gasto debe ser 1 o 2.")
    return numero


def listar_gastos(
    bd: Session,
    id_usuario: str,
    anio: int | None = None,
    mes: int | None = None,
    quincena: int | None = None,
) -> list[Gasto]:
    """Lista los gastos del usuario, opcionalmente filtrados por mes y quincena.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        anio: Año a filtrar; si es `None` se listan todos.
        mes: Mes a filtrar (1–12); requiere `anio`.
        quincena: `1` o `2` para limitar a esa quincena; `None` sin filtro.

    Returns:
        Lista ordenada por fecha descendente.
    """
    consulta = select(Gasto).where(
        Gasto.id_usuario == id_usuario,
        # SRS v1.7: los pagos de trabajos extras viven en `gastos` solo para
        # reutilizar la fila con check; no son gastos ni restan del sueldo.
        Gasto.id_trabajo.is_(None),
    )
    if anio is not None and mes is not None:
        inicio = date(anio, mes, 1)
        fin = date(anio + (mes // 12), (mes % 12) + 1, 1)
        consulta = consulta.where(Gasto.fecha >= inicio, Gasto.fecha < fin)
    if quincena in (1, 2):
        consulta = consulta.where(Gasto.quincena == quincena)
    consulta = consulta.order_by(Gasto.fecha.desc())
    return list(bd.scalars(consulta))


def total_gastos_mes(bd: Session, id_usuario: str, anio: int, mes: int) -> Decimal:
    """Suma los gastos de un mes calendario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).

    Returns:
        Total redondeado a centavos.
    """
    gastos = listar_gastos(bd, id_usuario, anio, mes)
    return redondear_dinero(sum((valor_computable(gasto) for gasto in gastos), start=CERO))


def total_gastos_quincena(
    bd: Session, id_usuario: str, anio: int, mes: int, quincena: int
) -> Decimal:
    """Suma los gastos fijos asignados a una quincena.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).
        quincena: `1` o `2`.

    Returns:
        Total redondeado a centavos.
    """
    gastos = listar_gastos(bd, id_usuario, anio, mes, quincena)
    return redondear_dinero(sum((valor_computable(gasto) for gasto in gastos), start=CERO))


def total_gastos_periodo(
    bd: Session, id_usuario: str, anio: int, mes: int, quincena: int = 0
) -> Decimal:
    """Suma los gastos que pertenecen al periodo visible.

    Reproduce la imputación del panel de quincenas: los gastos sin quincena
    asignada se cuentan en la quincena 1 para no perder el total del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).
        quincena: `0` para el mes completo, `1` o `2` para una quincena.

    Returns:
        Total redondeado a centavos.
    """
    if quincena not in (1, 2):
        return total_gastos_mes(bd, id_usuario, anio, mes)

    del_mes = listar_gastos(bd, id_usuario, anio, mes)
    if quincena == 1:
        seleccionados = [gasto for gasto in del_mes if gasto.quincena in (None, 1)]
    else:
        seleccionados = [gasto for gasto in del_mes if gasto.quincena == 2]
    return redondear_dinero(sum((valor_computable(gasto) for gasto in seleccionados), start=CERO))


def resumen_por_categoria(bd: Session, id_usuario: str) -> list[dict[str, object]]:
    """Agrupa los gastos por categoría y calcula su participación.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.

    Returns:
        Lista de diccionarios con categoría, total y porcentaje, ordenada de
        mayor a menor.
    """
    gastos = listar_gastos(bd, id_usuario)
    acumulado: dict[str, Decimal] = {}
    for gasto in gastos:
        acumulado[gasto.categoria] = acumulado.get(gasto.categoria, CERO) + gasto.valor

    total = sum(acumulado.values(), start=CERO)
    filas = [
        {
            "categoria": categoria,
            "total": valor,
            "porcentaje": (valor / total * 100) if total > CERO else CERO,
        }
        for categoria, valor in acumulado.items()
    ]
    return sorted(filas, key=lambda fila: fila["total"], reverse=True)


def eliminar_gasto(bd: Session, id_usuario: str, id_gasto: str) -> bool:
    """Elimina un gasto del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto (evita borrar datos ajenos).
        id_gasto: Identificador del gasto.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return False
    bd.delete(gasto)
    bd.commit()
    return True


def actualizar_gasto(
    bd: Session,
    id_usuario: str,
    id_gasto: str,
    descripcion: str,
    valor: Decimal | str | int | float,
    categoria: str | None = None,
    quincena: int | str | None = None,
) -> Gasto | None:
    """Modifica la descripción, el valor o la categoría de un gasto existente.

    La SRS v1.3 permite corregir el monto de un gasto fijo en cualquier momento
    (por ejemplo, un recibo de servicios que cambia cada mes) sin tener que
    eliminarlo y volverlo a crear. La fecha original se conserva para no alterar
    el histórico del presupuesto.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto (impide modificar datos ajenos).
        id_gasto: Identificador del gasto.
        descripcion: Nuevo detalle legible.
        valor: Nuevo monto; no puede ser negativo.
        categoria: Categoría nueva; si es `None` se conserva la anterior.
        quincena: `1` o `2` para la quincena del gasto; `None`, `0` o cadena
            vacía lo devuelven al mes completo.

    Returns:
        El gasto actualizado, o `None` si no existe o pertenece a otro usuario.

    Raises:
        ValueError: Si la descripción está vacía, el valor es negativo o
            inválido, o la quincena no es 1 ni 2.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None

    descripcion_limpia = descripcion.strip()
    if not descripcion_limpia:
        raise ValueError("La descripción del gasto es obligatoria.")

    monto = redondear_dinero(parsear_monto(str(valor)))
    if monto < CERO:
        raise ValueError("El valor del gasto no puede ser negativo.")

    gasto.descripcion = descripcion_limpia[:150]
    gasto.valor = monto
    gasto.quincena = _normalizar_quincena(quincena)

    if categoria is not None:
        categoria_limpia = categoria.strip()
        if not categoria_limpia:
            raise ValueError("La categoría del gasto es obligatoria.")
        gasto.categoria = categoria_limpia[:60]

    bd.commit()
    bd.refresh(gasto)
    return gasto

