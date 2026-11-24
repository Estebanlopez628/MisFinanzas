"""Metas de ahorro convertidas en gastos fijos con check de pago (SRS v1.6).

Responsabilidad
---------------
- Generar, para cada meta, el gasto fijo de cada quincena en que se descuenta
  (dos gastos cuando la meta es «Ambas quincenas») durante el periodo que
  escogió el usuario, en meses o años.
- Marcar un gasto como pagado (✔). El pago queda registrado de forma permanente
  y su suma por mes forma el abono de la meta en «Gastos y Presupuesto».
- Desmarcar un ✔ (SRS v1.7, bloque C). Revierte el pago y su abono para corregir
  una marca hecha por error.
- Limpiar los checks de una quincena. Solo oculta el ✔; el pago se conserva.
- Quitar un pago con × en un gasto de meta: queda inhabilitado 15 días en su
  quincena, no cuenta en el saldo y su abono se retira. La meta nunca se elimina.
- Registrar un abono manual en un pago saltado, por si quedó dinero disponible.
- Propagar el valor editado de una quincena a los meses siguientes.

Reglas:
- Un pago inhabilitado no admite ✔. Vencido el plazo vuelve a ser un gasto normal.
- El valor de una quincena vale desde el mes editado en adelante hasta que se
  vuelva a editar; los meses pasados no cambian.
- Un abono heredado del modelo anterior se conserva como monto pagado; su cuota
  planeada es el valor del gasto.
- Los gastos sin quincena (mes completo) se limpian con los checks de la
  quincena 1, igual que en el panel.
- Los gastos de metas no se generan retroactivamente.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import AbonoProyeccion, Gasto
from app.servicios import ahorro, gastos

CERO = Decimal("0")
# Plazo de un pago saltado con × (una quincena completa).
DIAS_INHABILITADO = 15
# SRS v4.35: omisión temporal de un gasto fijo normal (no meta).
DIAS_OMITIDO = 10
PREFIJO_META = "Meta · "
ACCION_INHABILITADO = "inhabilitado"
ACCION_ELIMINADO = "eliminado"


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


def _gastos_de_meta_en_mes(
    bd: Session, id_proyeccion: str, anio: int, mes: int
) -> list[Gasto]:
    """Lista los gastos generados por una meta en un mes.

    Args:
        bd: Sesión de base de datos.
        id_proyeccion: Meta dueña de los gastos.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Gastos del mes ordenados por quincena.
    """
    inicio, fin = _rango_del_mes(anio, mes)
    consulta = (
        select(Gasto)
        .where(
            Gasto.id_proyeccion == id_proyeccion,
            Gasto.fecha >= inicio,
            Gasto.fecha < fin,
        )
        .order_by(Gasto.quincena)
    )
    return list(bd.scalars(consulta))


def _quincenas_de_la_meta(proyeccion) -> list[tuple[int, Decimal]]:
    """Calcula en qué quincenas se descuenta la meta y cuánto en cada una.

    SRS v1.7: con «Ambas quincenas» el monto de cada pago depende del modo
    (`DIVIDIR` reparte la cuota; `DUPLICAR` cobra la cuota completa); con
    quincena 1 o 2, el pago elegido asume la cuota completa.

    Args:
        proyeccion: Meta persistida.

    Returns:
        Lista de tuplas `(quincena, monto)`.
    """
    monto = ahorro.valor_por_pago(
        proyeccion.valor_mensual, proyeccion.quincena, proyeccion.modo_ambas
    )
    if proyeccion.quincena == ahorro.QUINCENA_AMBAS:
        return [(1, monto), (2, monto)]
    return [(proyeccion.quincena, monto)]


def _meses_a_generar(proyeccion, anio: int, mes: int) -> list[tuple[int, int]]:
    """Determina los meses de la meta que deben tener gastos desde el mes visible.

    Cubre todo el periodo que escogió el usuario, desde su inicio hasta el final
    (hasta 600 meses). Los meses anteriores al visible no se generan.

    Args:
        proyeccion: Meta persistida.
        anio: Año del mes visible.
        mes: Mes visible (1–12).

    Returns:
        Lista de tuplas `(anio, mes)` ordenadas.
    """
    origen = _posicion(anio, mes)
    inicio_meta = _posicion(proyeccion.fecha_inicio.year, proyeccion.fecha_inicio.month)
    fin = inicio_meta + (proyeccion.meses or ahorro.MESES_VENTANA_FIJA) - 1
    primero = max(inicio_meta, origen)
    return [_desde_posicion(posicion) for posicion in range(primero, fin + 1)]


def _valor_vigente(
    bd: Session,
    proyeccion,
    quincena: int,
    anio: int,
    mes: int,
    valor_inicial: Decimal,
) -> Decimal:
    """Obtiene el valor que rige una quincena de la meta en un mes nuevo.

    Toma el valor del último gasto anterior de esa quincena. Así, una edición
    hecha en un mes se mantiene en los meses siguientes.

    Args:
        bd: Sesión de base de datos.
        proyeccion: Meta persistida.
        quincena: `1` o `2`.
        anio: Año del mes a generar.
        mes: Mes a generar (1–12).
        valor_inicial: Cuota calculada si no hay gastos previos.

    Returns:
        Valor del gasto para ese mes.
    """
    previo = bd.scalar(
        select(Gasto)
        .where(
            Gasto.id_proyeccion == proyeccion.id_proyeccion,
            Gasto.quincena == quincena,
            Gasto.fecha < date(anio, mes, 1),
        )
        .order_by(Gasto.fecha.desc())
        .limit(1)
    )
    return previo.valor if previo is not None else valor_inicial


def asegurar_gastos_de_metas(
    bd: Session, id_usuario: str, anio: int, mes: int
) -> None:
    """Crea los gastos de las metas que falten desde el mes visible.

    Idempotente: un gasto por meta, quincena y mes. Si una meta tenía un abono
    registrado antes de SRS v1.6 y el mes no tiene gastos, el gasto nace pagado
    con ese monto.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las metas.
        anio: Año del mes visible.
        mes: Mes visible (1–12).
    """
    for proyeccion in ahorro.listar_proyecciones(bd, id_usuario):
        for anio_meta, mes_meta in _meses_a_generar(proyeccion, anio, mes):
            existentes = _gastos_de_meta_en_mes(
                bd, proyeccion.id_proyeccion, anio_meta, mes_meta
            )
            quincenas_creadas = {gasto.quincena for gasto in existentes}
            partes = _quincenas_de_la_meta(proyeccion)
            pendientes = [
                (quincena, monto)
                for quincena, monto in partes
                if quincena not in quincenas_creadas
            ]
            if not pendientes:
                continue

            abono_previo = None
            if not existentes:
                abono_previo = bd.scalar(
                    select(AbonoProyeccion).where(
                        AbonoProyeccion.id_proyeccion == proyeccion.id_proyeccion,
                        AbonoProyeccion.anio == anio_meta,
                        AbonoProyeccion.mes == mes_meta,
                    )
                )

            for quincena, monto in pendientes:
                pagado = abono_previo is not None
                bd.add(
                    Gasto(
                        id_usuario=id_usuario,
                        categoria=proyeccion.categoria[:60],
                        descripcion=f"{PREFIJO_META}{proyeccion.descripcion}"[:150],
                        valor=_valor_vigente(
                            bd, proyeccion, quincena, anio_meta, mes_meta, monto
                        ),
                        es_fijo=True,
                        fecha=date(anio_meta, mes_meta, 1),
                        quincena=quincena,
                        id_proyeccion=proyeccion.id_proyeccion,
                        pagado=pagado,
                        pagado_en=abono_previo.fecha_registro.date() if pagado else None,
                        monto_pagado=(
                            redondear_dinero(abono_previo.valor / len(partes))
                            if pagado
                            else None
                        ),
                        check_visible=True,
                    )
                )
            bd.commit()
            if abono_previo is not None:
                sincronizar_abono(bd, proyeccion.id_proyeccion, anio_meta, mes_meta)


def sincronizar_abono(
    bd: Session, id_proyeccion: str, anio: int, mes: int
) -> None:
    """Recalcula el abono de un mes como la suma de sus pagos marcados.

    Un pago marcado conserva su abono aunque el check se limpie. Si el mes ya no
    tiene pagos, el abono desaparece.

    Args:
        bd: Sesión de base de datos.
        id_proyeccion: Meta a recalcular.
        anio: Año del mes.
        mes: Mes (1–12).
    """
    gastos_mes = _gastos_de_meta_en_mes(bd, id_proyeccion, anio, mes)
    pagos = [gasto for gasto in gastos_mes if gasto.pagado]
    existente = bd.scalar(
        select(AbonoProyeccion).where(
            AbonoProyeccion.id_proyeccion == id_proyeccion,
            AbonoProyeccion.anio == anio,
            AbonoProyeccion.mes == mes,
        )
    )

    if pagos:
        total = redondear_dinero(
            sum((gastos.valor_computable(gasto) for gasto in pagos), start=CERO)
        )
        if existente is None:
            bd.add(
                AbonoProyeccion(
                    id_proyeccion=id_proyeccion,
                    anio=anio,
                    mes=mes,
                    valor=total,
                )
            )
        else:
            existente.valor = total
    elif existente is not None:
        bd.delete(existente)
    bd.commit()


def sincronizar_gasto(bd: Session, gasto: Gasto) -> None:
    """Actualiza el abono del mes de un gasto de meta, si lo tiene.

    Args:
        bd: Sesión de base de datos.
        gasto: Gasto recién modificado.
    """
    if gasto.id_proyeccion is None:
        return
    sincronizar_abono(bd, gasto.id_proyeccion, gasto.fecha.year, gasto.fecha.month)


def propagar_valor(bd: Session, gasto: Gasto) -> None:
    """Lleva el valor editado de una quincena a los meses siguientes.

    Solo cambian los gastos posteriores de la misma meta y quincena que aún no
    están pagados. Si el gasto editado ya está pagado, su monto pagado toma el
    nuevo valor. Después se recalculan los abonos afectados.

    Args:
        bd: Sesión de base de datos.
        gasto: Gasto con el valor ya actualizado.
    """
    if gasto.pagado:
        gasto.monto_pagado = gasto.valor
    if gasto.id_proyeccion is None:
        bd.commit()
        return

    posteriores = list(
        bd.scalars(
            select(Gasto).where(
                Gasto.id_proyeccion == gasto.id_proyeccion,
                Gasto.quincena == gasto.quincena,
                Gasto.fecha > gasto.fecha,
                Gasto.pagado.is_(False),
            )
        )
    )
    for posterior in posteriores:
        posterior.valor = gasto.valor
    bd.commit()

    meses = {(gasto.fecha.year, gasto.fecha.month)}
    meses |= {(posterior.fecha.year, posterior.fecha.month) for posterior in posteriores}
    for anio, mes in sorted(meses):
        sincronizar_abono(bd, gasto.id_proyeccion, anio, mes)


def marcar_pagado(
    bd: Session, id_usuario: str, id_gasto: str, hoy: date
) -> Gasto | None:
    """Marca un gasto fijo como pagado (✔) y registra su abono si es de meta.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto a marcar.
        hoy: Fecha del pago.

    Returns:
        El gasto actualizado, o `None` si no existe o es de otro usuario.

    Raises:
        ValueError: Si el pago está inhabilitado y su plazo no ha vencido.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None
    if gasto.inhabilitado_hasta is not None and gasto.inhabilitado_hasta > hoy:
        raise ValueError("Este pago está inhabilitado y no se puede marcar.")

    if not gasto.pagado:
        gasto.pagado = True
        gasto.pagado_en = hoy
        gasto.monto_pagado = gasto.valor
    gasto.inhabilitado_hasta = None
    gasto.check_visible = True
    bd.commit()
    sincronizar_gasto(bd, gasto)
    bd.refresh(gasto)
    return gasto


def desmarcar_pagado(
    bd: Session, id_usuario: str, id_gasto: str
) -> Gasto | None:
    """Revierte el ✔ de un gasto fijo y retira su abono (SRS v1.7).

    Sirve para corregir un check marcado por error: el gasto vuelve a contar en
    el saldo de su quincena y, si es de una meta, el abono del mes se recalcula
    sin ese pago. El check queda visible para poder volver a marcarlo.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto cuyo ✔ se retira.

    Returns:
        El gasto actualizado, o `None` si no existe o es de otro usuario.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None

    gasto.pagado = False
    gasto.pagado_en = None
    gasto.monto_pagado = None
    # El check se muestra vacío: el usuario puede volver a pulsarlo si se
    # arrepiente, sin perder el estado de «pago conservado».
    gasto.check_visible = True
    bd.commit()
    sincronizar_gasto(bd, gasto)
    bd.refresh(gasto)
    return gasto


def registrar_abono_manual(
    bd: Session,
    id_usuario: str,
    id_gasto: str,
    monto_texto: str,
    hoy: date,
) -> Gasto | None:
    """Abona un monto en un pago saltado, por si quedó dinero disponible.

    El pago deja de estar inhabilitado, queda pagado con el monto indicado y
    ese monto cuenta en el saldo de la quincena y en el abono del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto saltado con ×.
        monto_texto: Monto escrito por el usuario.
        hoy: Fecha del abono.

    Returns:
        El gasto actualizado, o `None` si no existe o es de otro usuario.

    Raises:
        ValueError: Si el pago no está inhabilitado o el monto no es positivo.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None
    if gasto.inhabilitado_hasta is None or gasto.inhabilitado_hasta <= hoy:
        raise ValueError("El abono manual solo aplica a un pago saltado con ×.")

    monto = redondear_dinero(parsear_monto(str(monto_texto)))
    if monto <= CERO:
        raise ValueError("El abono debe ser mayor que cero.")

    gasto.pagado = True
    gasto.pagado_en = hoy
    gasto.monto_pagado = monto
    gasto.inhabilitado_hasta = None
    gasto.check_visible = True
    bd.commit()
    sincronizar_gasto(bd, gasto)
    bd.refresh(gasto)
    return gasto


def registrar_abono_meta(
    bd: Session,
    id_usuario: str,
    id_gasto: str,
    monto_texto: str,
    hoy: date,
) -> Gasto | None:
    """Acumula un abono libre a la meta vinculada a un gasto fijo (SRS v4.28).

    Permite varios abonos en el mismo mes: se suman al `AbonoProyeccion` de ese
    mes —se conserva su restricción de unicidad— y al `monto_pagado` del gasto,
    de modo que el check refleje lo realmente abonado sin migrar la base.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto fijo vinculado a una meta.
        monto_texto: Monto escrito por el usuario.
        hoy: Fecha del abono.

    Returns:
        El gasto actualizado, o `None` si no existe o no es del usuario.

    Raises:
        ValueError: Si el monto no es positivo.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario or not gasto.id_proyeccion:
        return None

    monto = redondear_dinero(parsear_monto(str(monto_texto)))
    if monto <= CERO:
        raise ValueError("El abono debe ser mayor que cero.")

    abono = bd.scalars(
        select(AbonoProyeccion).where(
            AbonoProyeccion.id_proyeccion == gasto.id_proyeccion,
            AbonoProyeccion.anio == hoy.year,
            AbonoProyeccion.mes == hoy.month,
        )
    ).first()
    if abono is None:
        abono = AbonoProyeccion(
            id_proyeccion=gasto.id_proyeccion,
            anio=hoy.year,
            mes=hoy.month,
            valor=CERO,
        )
        bd.add(abono)
    abono.valor = redondear_dinero(abono.valor + monto)

    gasto.pagado = True
    gasto.check_visible = True
    gasto.pagado_en = hoy
    gasto.monto_pagado = redondear_dinero(gasto.monto_pagado or CERO) + monto
    gasto.inhabilitado_hasta = None
    bd.commit()
    sincronizar_gasto(bd, gasto)
    bd.refresh(gasto)
    return gasto


def limpiar_checks(
    bd: Session,
    id_usuario: str,
    anio: int,
    mes: int,
    quincena: int,
    id_trabajo: str | None = None,
) -> int:
    """Oculta los checks de una quincena sin borrar los pagos registrados.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        anio: Año del periodo.
        mes: Mes del periodo (1–12).
        quincena: `1` o `2` para una quincena (la 1 incluye los gastos del mes
            completo); `0` para la modalidad mensual, que limpia todo el mes.
        id_trabajo: Si se indica, restringe la acción a los gastos de ese
            contrato de Trabajos Extras, sin tocar los de Mis Finanzas.

    Returns:
        Cantidad de checks ocultados.
    """
    if id_trabajo:
        # `gastos.listar_gastos` excluye los pagos de trabajos para que no resten
        # del sueldo; aquí se consultan directamente para limpiar solo este
        # contrato, sin tocar los checks de Mis Finanzas.
        inicio = date(anio, mes, 1)
        fin = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
        del_mes = list(
            bd.scalars(
                select(Gasto).where(
                    Gasto.id_usuario == id_usuario,
                    Gasto.id_trabajo == id_trabajo,
                    Gasto.fecha >= inicio,
                    Gasto.fecha < fin,
                )
            ).all()
        )
    else:
        del_mes = gastos.listar_gastos(bd, id_usuario, anio, mes)
    if quincena == 1:
        seleccion = [gasto for gasto in del_mes if gasto.quincena in (None, 1)]
    elif quincena == 2:
        seleccion = [gasto for gasto in del_mes if gasto.quincena == 2]
    else:
        seleccion = del_mes

    limpiados = 0
    for gasto in seleccion:
        if gasto.pagado and gasto.check_visible:
            gasto.check_visible = False
            limpiados += 1
    bd.commit()
    return limpiados


def inhabilitar_gasto(
    bd: Session, id_usuario: str, id_gasto: str, hoy: date
) -> Gasto | None:
    """Salta un pago de meta: lo inhabilita 15 días y retira su abono.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto de meta a inhabilitar.
        hoy: Fecha en la que se salta el pago.

    Returns:
        El gasto actualizado, o `None` si no existe o es de otro usuario.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None

    gasto.pagado = False
    gasto.pagado_en = None
    gasto.monto_pagado = None
    gasto.check_visible = False
    gasto.inhabilitado_hasta = hoy + timedelta(days=DIAS_INHABILITADO)
    bd.commit()
    sincronizar_gasto(bd, gasto)
    bd.refresh(gasto)
    return gasto


def omitir_pago(
    bd: Session, id_usuario: str, id_gasto: str, hoy: date
) -> Gasto | None:
    """Omite temporalmente el cobro de un gasto fijo o de una meta durante 10 días.

    SRS v4.37: el modal de la X es el mismo para gastos normales y metas
    proyectadas. En ambos casos el registro se conserva y deja de contarse en
    los compromisos hasta `hoy + 10`, fecha en que se reactiva automáticamente.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto fijo o de meta a omitir.
        hoy: Fecha en la que se activa la omisión.

    Returns:
        El gasto actualizado, o `None` si no existe o es ajeno.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None

    gasto.pagado = False
    gasto.pagado_en = None
    gasto.monto_pagado = None
    gasto.check_visible = False
    gasto.inhabilitado_hasta = hoy + timedelta(days=DIAS_OMITIDO)
    bd.commit()
    sincronizar_gasto(bd, gasto)
    bd.refresh(gasto)
    return gasto


def habilitar_gasto(
    bd: Session, id_usuario: str, id_gasto: str
) -> Gasto | None:
    """Reactiva de inmediato un gasto fijo o meta previamente omitido.

    SRS v4.37: el botón «Habilitar» sustituye a «Abonar» en los ítems
    inhabilitados. Limpia la fecha de omisión y devuelve el gasto a los
    compromisos de la quincena sin esperar los diez días.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto a reactivar.

    Returns:
        El gasto reactivado, o `None` si no existe o es ajeno.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None

    gasto.inhabilitado_hasta = None
    gasto.pagado = False
    gasto.pagado_en = None
    gasto.monto_pagado = None
    gasto.check_visible = True
    bd.commit()
    sincronizar_gasto(bd, gasto)
    bd.refresh(gasto)
    return gasto


def quitar_gasto(
    bd: Session, id_usuario: str, id_gasto: str, hoy: date
) -> str | None:
    """Gestiona la × de un gasto fijo según sea de meta, de trabajo o manual.

    Un gasto de meta se inhabilita (la meta sigue viva). Un pago de trabajo extra
    también se inhabilita 15 días: así la × no lo borra y la generación
    idempotente no lo vuelve a crear. Un gasto manual se elimina como antes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del gasto.
        id_gasto: Gasto sobre el que se pulsó ×.
        hoy: Fecha de la acción.

    Returns:
        `ACCION_INHABILITADO`, `ACCION_ELIMINADO` o `None` si no existe.
    """
    gasto = bd.get(Gasto, id_gasto)
    if gasto is None or gasto.id_usuario != id_usuario:
        return None
    if gasto.id_proyeccion is not None or gasto.id_trabajo is not None:
        inhabilitar_gasto(bd, id_usuario, id_gasto, hoy)
        return ACCION_INHABILITADO
    gastos.eliminar_gasto(bd, id_usuario, id_gasto)
    return ACCION_ELIMINADO
