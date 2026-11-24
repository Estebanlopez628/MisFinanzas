"""Pruebas de las metas convertidas en gastos fijos con check (SRS v1.6).

Cubren el ciclo completo: crear la meta genera su gasto, el ✔ registra el abono,
«Limpiar checks» conserva el pago, editar un pago marcado actualiza el abono, la ×
inhabilita el pago sin borrar la meta y el saldo solo descuenta lo que sigue
activo.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.modelos import AbonoProyeccion, Gasto
from app.servicios import ahorro, gastos, pagos_metas, quincenas, usuarios

HOY = date.today()


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def _gastos_de_la_meta(bd, id_usuario: str, id_proyeccion: str, anio: int, mes: int):
    """Lista los gastos generados por una meta en un mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        id_proyeccion: Meta consultada.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Gastos de la meta en ese mes, ordenados por quincena.
    """
    return [
        gasto
        for gasto in gastos.listar_gastos(bd, id_usuario, anio, mes)
        if gasto.id_proyeccion == id_proyeccion
    ]


def _abono(bd, id_proyeccion: str, anio: int, mes: int):
    """Devuelve el abono de un mes o `None` si no hay pagos.

    Args:
        bd: Sesión de base de datos.
        id_proyeccion: Meta consultada.
        anio: Año del mes.
        mes: Mes (1–12).

    Returns:
        Monto del abono o `None`.
    """
    meta = next(
        (m for m in ahorro.resumen_metas(bd, _id_admin(bd)) if m.proyeccion.id_proyeccion == id_proyeccion),
        None,
    )
    assert meta is not None
    return next(
        (mes_meta.abono for mes_meta in meta.meses if (mes_meta.anio, mes_meta.mes) == (anio, mes)),
        None,
    )


def _crear_meta(bd, id_usuario: str, valor: str = "100.000", quincena: int = 1, **extra):
    """Crea una meta de noviembre de 2026 y genera sus gastos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta.
        valor: Cuota mensual.
        quincena: `1`, `2` o `3` (ambas).
        **extra: Argumentos adicionales de `crear_proyeccion`.

    Returns:
        La meta persistida.
    """
    extra.setdefault("meses", "24")
    meta = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Viaje",
        valor,
        fecha_inicio=date(2026, 11, 1),
        quincena=quincena,
        **extra,
    )
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, 2026, 11)
    return meta


def test_crear_meta_genera_su_gasto_en_la_quincena_elegida(bd) -> None:
    """La cuota nace como gasto fijo de la quincena elegida, con el prefijo de meta."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000", quincena=2)

    generados = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)
    assert len(generados) == 1
    assert generados[0].quincena == 2
    assert generados[0].valor == Decimal("100000.00")
    assert generados[0].descripcion.startswith("Meta · ")
    assert generados[0].pagado is False


def test_ambas_quincenas_genera_dos_mitades(bd) -> None:
    """«Ambas quincenas» crea un gasto por quincena con la mitad de la cuota."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000", quincena=3)

    generados = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)
    assert sorted(gasto.quincena for gasto in generados) == [1, 2]
    assert all(gasto.valor == Decimal("50000.00") for gasto in generados)


def test_generar_es_idempotente(bd) -> None:
    """Volver a generar no duplica los gastos de la meta."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario)
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, 2026, 11)

    assert len(_gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)) == 1


def test_marcar_pago_registra_el_abono_del_mes(bd) -> None:
    """El ✔ del gasto deja el abono registrado en Gastos y Presupuesto."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]

    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    assert _abono(bd, meta.id_proyeccion, 2026, 11) == Decimal("100000.00")


def test_limpiar_checks_conserva_el_abono(bd) -> None:
    """Limpiar oculta el ✔ pero el pago y su abono siguen registrados."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    limpiados = pagos_metas.limpiar_checks(bd, id_usuario, 2026, 11, 1)

    assert limpiados == 1
    bd.refresh(gasto)
    assert gasto.pagado is True
    assert gasto.check_visible is False
    assert _abono(bd, meta.id_proyeccion, 2026, 11) == Decimal("100000.00")


def test_limpiar_solo_afecta_su_quincena(bd) -> None:
    """Limpiar la quincena 1 no toca los checks de la quincena 2."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000", quincena=3)
    for gasto in _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11):
        pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    pagos_metas.limpiar_checks(bd, id_usuario, 2026, 11, 1)

    visibles = {
        gasto.quincena: gasto.check_visible
        for gasto in _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)
    }
    assert visibles == {1: False, 2: True}


def test_solo_una_mitad_pagada_abona_solo_esa_mitad(bd) -> None:
    """Con «Ambas» y un solo ✔, el abono del mes es la mitad de la cuota."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000", quincena=3)
    primera = next(
        gasto
        for gasto in _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)
        if gasto.quincena == 1
    )

    pagos_metas.marcar_pagado(bd, id_usuario, primera.id_gasto, HOY)

    assert _abono(bd, meta.id_proyeccion, 2026, 11) == Decimal("50000.00")


def test_editar_gasto_pagado_actualiza_el_abono(bd) -> None:
    """Corregir el valor de un gasto ya pagado cambia el abono del mes."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    gastos.actualizar_gasto(bd, id_usuario, gasto.id_gasto, "Viaje", "120.000", quincena=1)
    pagos_metas.propagar_valor(bd, gasto)

    assert _abono(bd, meta.id_proyeccion, 2026, 11) == Decimal("120000.00")
    assert ahorro.listar_proyecciones(bd, id_usuario)[0].valor_mensual == Decimal("100000.00")


def test_x_en_pago_marcado_quita_abono_y_conserva_la_meta(bd) -> None:
    """La × de un pago marcado retira su abono sin eliminar la meta."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    accion = pagos_metas.quitar_gasto(bd, id_usuario, gasto.id_gasto, HOY)

    assert accion == pagos_metas.ACCION_INHABILITADO
    assert _abono(bd, meta.id_proyeccion, 2026, 11) is None
    assert len(ahorro.listar_proyecciones(bd, id_usuario)) == 1
    bd.refresh(gasto)
    assert gasto.inhabilitado_hasta == HOY + timedelta(days=15)


def test_pago_inhabilitado_no_admite_check(bd) -> None:
    """Un pago saltado no se puede marcar mientras está inhabilitado."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    pagos_metas.quitar_gasto(bd, id_usuario, gasto.id_gasto, HOY)

    try:
        pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)
    except ValueError:
        return
    raise AssertionError("Se marcó un pago inhabilitado.")


def test_pago_inhabilitado_no_resta_en_su_quincena(bd) -> None:
    """El valor saltado vuelve al saldo de esa quincena mientras esté inhabilitado."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000", quincena=1)
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]

    antes = quincenas.resumen_quincenas(bd, id_usuario, None, 2026, 11)[0]
    pagos_metas.quitar_gasto(bd, id_usuario, gasto.id_gasto, HOY)
    despues = quincenas.resumen_quincenas(bd, id_usuario, None, 2026, 11)[0]

    assert antes.gastos >= Decimal("100000.00")
    assert despues.gastos == antes.gastos - Decimal("100000.00")


def test_eliminar_meta_la_archiva_y_conserva_el_historial(bd) -> None:
    """Eliminar archiva la meta: sale de la lista, pero su pago y su historial quedan."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gastos_mes = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)
    id_pagado = gastos_mes[0].id_gasto
    pagos_metas.marcar_pagado(bd, id_usuario, id_pagado, HOY)
    id_futuro = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 12)[0].id_gasto

    assert ahorro.eliminar_proyeccion(bd, id_usuario, meta.id_proyeccion, hoy=date(2026, 11, 16)) is True

    bd.expire_all()
    assert ahorro.listar_proyecciones(bd, id_usuario) == []
    assert bd.get(Gasto, id_pagado) is not None
    assert bd.get(Gasto, id_futuro) is None
    historial = ahorro.historial_metas(bd, id_usuario)
    assert len(historial) == 1
    assert historial[0]["estado"] == ahorro.ESTADO_ELIMINADA
    assert historial[0]["total_recogido"] == Decimal("100000.00")


def test_historial_detalla_pagos_mes_por_mes(bd) -> None:
    """El historial lista cada mes hasta el archivado: pagado con monto y fecha."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000", meses=3)
    nov = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    pagos_metas.marcar_pagado(bd, id_usuario, nov.id_gasto, date(2026, 11, 15))
    ahorro.eliminar_proyeccion(bd, id_usuario, meta.id_proyeccion, hoy=date(2026, 11, 16))

    pagos = ahorro.historial_metas(bd, id_usuario)[0]["pagos"]

    # Dic 2026 es posterior al archivado: la meta ya no lo reclama, no aparece.
    assert [(p["etiqueta"], p["estado"]) for p in pagos] == [("nov 2026", "Pagado")]
    assert pagos[0]["valor"] == Decimal("100000.00")
    assert pagos[0]["fecha"] == date(2026, 11, 15)


def test_meta_cumplida_se_marca_y_se_puede_extender(bd) -> None:
    """Una meta de 3 meses que ya terminó queda cumplida y se extiende desde el mes actual."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_usuario, "Ahorro", "Corta", "100.000", meses=3, fecha_inicio=date(2026, 1, 1)
    )

    resumen = ahorro.resumen_metas(bd, id_usuario)[0]
    assert resumen.cumplida is True

    ahorro.extender_proyeccion(bd, id_usuario, meta.id_proyeccion, 2, hoy=date(2026, 11, 16))
    bd.refresh(meta)
    assert meta.meses == 12
    resumen = ahorro.resumen_metas(bd, id_usuario)[0]
    assert resumen.cumplida is False
    assert resumen.fin_etiqueta == "dic 2026"


def test_extender_meta_en_curso_suma_desde_su_fin(bd) -> None:
    """Extender una meta en curso agrega meses después de su último mes planificado."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_usuario, "Ahorro", "En curso", "100.000", meses=12, fecha_inicio=date(2026, 11, 1)
    )

    ahorro.extender_proyeccion(bd, id_usuario, meta.id_proyeccion, 6, hoy=date(2026, 11, 16))
    bd.refresh(meta)

    assert meta.meses == 18
    assert ahorro.resumen_metas(bd, id_usuario)[0].fin_etiqueta == "abr 2028"


def test_meta_archivada_no_se_extiende(bd) -> None:
    """Una meta eliminada no puede extenderse: queda solo en el historial."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_usuario, "Ahorro", "Archivada", "100.000", meses=12, fecha_inicio=date(2026, 11, 1)
    )
    ahorro.eliminar_proyeccion(bd, id_usuario, meta.id_proyeccion, hoy=date(2026, 11, 16))

    try:
        ahorro.extender_proyeccion(bd, id_usuario, meta.id_proyeccion, 3)
    except ValueError:
        return
    raise AssertionError("Se extendió una meta archivada.")


def test_vistas_muestran_el_check_y_el_estado_del_mes(cliente_admin, bd) -> None:
    """Mis Finanzas muestra el ✔ del pago y Gastos y Presupuesto el estado del mes."""
    id_admin = _id_admin(bd)
    meta = _crear_meta(bd, id_admin, "100.000")
    gasto = _gastos_de_la_meta(bd, id_admin, meta.id_proyeccion, 2026, 11)[0]

    finanzas = cliente_admin.get("/finanzas")
    assert finanzas.status_code == 200
    assert f"/gastos/{gasto.id_gasto}/pagado" in finanzas.text
    assert "Meta · Viaje" in finanzas.text
    # SRS v4.40: el botón está visible desde la primera carga, con o sin ✔.
    assert "Limpiar checks" in finanzas.text

    pagos_metas.marcar_pagado(bd, id_admin, gasto.id_gasto, HOY)
    finanzas = cliente_admin.get("/finanzas")
    assert "Limpiar checks" in finanzas.text

    presupuesto = cliente_admin.get("/presupuesto")
    assert presupuesto.status_code == 200
    assert "Abonado" in presupuesto.text


def test_plazo_vencido_vuelve_a_ser_un_pago_normal(bd) -> None:
    """Pasados 15 días, el pago saltado vuelve a contar y admite ✔."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    pagos_metas.quitar_gasto(bd, id_usuario, gasto.id_gasto, HOY)
    gasto.inhabilitado_hasta = HOY - timedelta(days=1)
    bd.commit()

    assert gastos.valor_computable(gasto, HOY) == Decimal("100000.00")
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)
    assert gasto.pagado is True


def test_abono_manual_solo_en_pago_saltado(bd) -> None:
    """El abono manual se rechaza si el pago no fue saltado con ×."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]

    try:
        pagos_metas.registrar_abono_manual(bd, id_usuario, gasto.id_gasto, "40.000", HOY)
    except ValueError:
        return
    raise AssertionError("Se aceptó un abono manual sin pago saltado.")


def test_abono_manual_en_pago_saltado_suma_al_saldo_y_al_abono(bd) -> None:
    """Un abono manual en un pago saltado cuenta en el saldo y en el abono del mes."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    pagos_metas.quitar_gasto(bd, id_usuario, gasto.id_gasto, HOY)
    antes = quincenas.resumen_quincenas(bd, id_usuario, None, 2026, 11)[0].gastos

    pagos_metas.registrar_abono_manual(bd, id_usuario, gasto.id_gasto, "40.000", HOY)

    assert quincenas.resumen_quincenas(bd, id_usuario, None, 2026, 11)[0].gastos == antes + Decimal("40000.00")
    assert _abono(bd, meta.id_proyeccion, 2026, 11) == Decimal("40000.00")
    bd.refresh(gasto)
    assert gasto.inhabilitado_hasta is None


def test_editar_valor_se_propaga_a_los_meses_siguientes(bd) -> None:
    """Editar una quincena cambia ese valor desde el mes editado en adelante."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    nov = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]

    gastos.actualizar_gasto(bd, id_usuario, nov.id_gasto, "Viaje", "120.000", quincena=1)
    pagos_metas.propagar_valor(bd, nov)

    dic = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 12)[0]
    assert dic.valor == Decimal("120000.00")
    bd.refresh(nov)
    assert nov.valor == Decimal("120000.00")


def test_meses_nuevos_toman_el_valor_vigente(bd) -> None:
    """Un mes generado después de la edición usa el valor editado."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, "100.000")
    nov = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    gastos.actualizar_gasto(bd, id_usuario, nov.id_gasto, "Viaje", "120.000", quincena=1)
    pagos_metas.propagar_valor(bd, nov)

    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, 2027, 11)

    nuevo = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2027, 11)[0]
    assert nuevo.valor == Decimal("120000.00")


def test_meta_limitada_genera_toda_su_duracion(bd) -> None:
    """Una meta de 18 meses genera los 18 gastos, no solo los 12 primeros."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(
        bd,
        id_usuario,
        "100.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses="18",
    )

    generados = list(
        bd.scalars(select(Gasto).where(Gasto.id_proyeccion == meta.id_proyeccion))
    )
    assert len(generados) == 18


def test_abono_heredado_se_convierte_en_pago_con_su_monto(bd) -> None:
    """Un abono del modelo anterior nace como pago marcado con el monto abonado."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Viaje",
        "100.000",
        fecha_inicio=date(2026, 11, 1),
        quincena=1,
        meses=24,
    )
    bd.add(
        AbonoProyeccion(
            id_proyeccion=meta.id_proyeccion,
            anio=2026,
            mes=11,
            valor=Decimal("70000"),
        )
    )
    bd.commit()

    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, 2026, 11)

    gasto = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion, 2026, 11)[0]
    assert gasto.pagado is True
    assert gasto.monto_pagado == Decimal("70000.00")
    assert gasto.valor == Decimal("100000.00")
    assert _abono(bd, meta.id_proyeccion, 2026, 11) == Decimal("70000.00")


def test_formulario_convierte_anios_a_meses(cliente_admin, bd) -> None:
    """El periodo escrito en años se guarda como 12 meses por año."""
    respuesta = cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "Fondo a tres años",
            "valor_mensual": "100.000",
            "tipo_duracion": "FIJO",
            "meses": "3",
            "unidad_periodo": "ANIOS",
            "fecha_inicio": "2026-11-01",
            "quincena": "1",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    meta = ahorro.listar_proyecciones(bd, _id_admin(bd))[0]
    assert meta.meses == 36


def test_pagina_muestra_historial_y_extension(cliente_admin, bd) -> None:
    """La página ofrece extender y, tras eliminar, muestra la meta en el historial."""
    id_admin = _id_admin(bd)
    meta = _crear_meta(bd, id_admin, "100.000")

    pagina = cliente_admin.get("/presupuesto")
    assert f"/presupuesto/metas/{meta.id_proyeccion}/extender" in pagina.text

    respuesta = cliente_admin.post(
        f"/presupuesto/metas/{meta.id_proyeccion}/extender",
        data={"cantidad": "6", "unidad_periodo": "MESES"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    bd.expire_all()
    assert ahorro.listar_proyecciones(bd, id_admin)[0].meses == 30

    cliente_admin.post(f"/presupuesto/metas/{meta.id_proyeccion}/eliminar", follow_redirects=False)
    pagina = cliente_admin.get("/presupuesto")
    assert "Historial de metas" in pagina.text
    assert "Viaje" in pagina.text
    assert "Ver pagos de esta meta" in pagina.text


def test_pago_ajeno_no_se_marca(bd) -> None:
    """Un usuario no puede marcar el gasto de otro."""
    id_admin = _id_admin(bd)
    cuenta = usuarios.buscar_por_correo(bd, "usuario@finanzas.co")
    assert cuenta is not None
    meta = _crear_meta(bd, id_admin, "100.000")
    gasto = _gastos_de_la_meta(bd, id_admin, meta.id_proyeccion, 2026, 11)[0]

    assert pagos_metas.marcar_pagado(bd, cuenta.id_usuario, gasto.id_gasto, HOY) is None


def test_ruta_de_abono_manual_ya_no_existe(cliente_admin, bd) -> None:
    """El formulario manual de abonos se retiró: la ruta ya no responde."""
    id_admin = _id_admin(bd)
    meta = _crear_meta(bd, id_admin, "100.000")

    respuesta = cliente_admin.post(
        f"/presupuesto/metas/{meta.id_proyeccion}/abono",
        data={"anio": "2026", "mes": "11", "valor": "100.000"},
        follow_redirects=False,
    )

    assert respuesta.status_code in (404, 405)


def test_ruta_de_check_marca_el_pago(cliente_admin, bd) -> None:
    """El ✔ por HTTP registra el pago y redirige al panel de origen."""
    id_admin = _id_admin(bd)
    meta = _crear_meta(bd, id_admin, "100.000")
    gasto = _gastos_de_la_meta(bd, id_admin, meta.id_proyeccion, 2026, 11)[0]

    respuesta = cliente_admin.post(
        f"/gastos/{gasto.id_gasto}/pagado",
        data={"origen": "finanzas"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/finanzas")
    bd.expire_all()
    assert gastos.listar_gastos(bd, id_admin, 2026, 11)[0].pagado is True

