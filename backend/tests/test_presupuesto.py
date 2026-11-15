"""Pruebas del planificador de ahorro y metas (SRS v1.3, bloque 3).

Se cubren las reglas del servicio (`app.servicios.ahorro`) y el camino HTTP de
la pestaña «Gastos y Presupuesto»: crear metas, registrar y corregir abonos,
eliminar y disparar la alerta de liquidez por debajo de $300.000.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.servicios import ahorro, gastos, perfiles, usuarios


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


# ---------------------------------------------------------------------------
# Servicio: creación de metas
# ---------------------------------------------------------------------------


def test_crear_meta_limitada_calcula_total(bd) -> None:
    """Una meta limitada guarda sus meses y expone el total proyectado."""
    id_usuario = _id_admin(bd)
    ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Fondo de emergencia",
        "500.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses="6",
        fecha_inicio=date(2026, 11, 1),
        quincena=1,
    )

    resumenes = ahorro.resumen_metas(bd, id_usuario)
    assert len(resumenes) == 1
    meta = resumenes[0]
    assert meta.proyeccion.valor_mensual == Decimal("500000.00")
    assert meta.proyeccion.meses == 6
    assert meta.total_proyectado == Decimal("3000000.00")
    assert meta.acumulado == Decimal("0.00")
    assert meta.porcentaje == Decimal("0.00")
    assert len(meta.meses) == 6


def test_meta_fija_no_tiene_total_cerrado(bd) -> None:
    """Un gasto fijo indefinido compara contra 12 meses y no cierra total."""
    id_usuario = _id_admin(bd)
    ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Seguro del vehículo",
        "Cuota mensual del seguro",
        "180.000",
        tipo_duracion=ahorro.DURACION_FIJA,
        fecha_inicio=date(2026, 11, 1),
        quincena=2,
    )

    meta = ahorro.resumen_metas(bd, id_usuario)[0]
    assert meta.proyeccion.meses is None
    assert meta.total_proyectado is None
    assert meta.porcentaje == Decimal("0.00")
    assert len(meta.meses) == ahorro.MESES_VENTANA_FIJA


def test_meta_limitada_exige_meses_validos(bd) -> None:
    """La duración limitada exige entre 1 y 120 meses."""
    id_usuario = _id_admin(bd)
    for meses in ("0", "121", ""):
        try:
            ahorro.crear_proyeccion(
                bd,
                id_usuario,
                "Ahorro",
                "Meta inválida",
                "100.000",
                tipo_duracion=ahorro.DURACION_LIMITADA,
                meses=meses,
            )
        except ValueError:
            continue
        raise AssertionError(f"Se aceptó una duración inválida: {meses!r}")


def test_meta_rechaza_categoria_vacia_y_monto_negativo(bd) -> None:
    """La categoría es obligatoria y la cuota no puede ser negativa."""
    id_usuario = _id_admin(bd)
    casos = (
        ("", "Sin categoría", "100.000"),
        ("Ahorro", "", "100.000"),
        ("Ahorro", "Negativa", "-1"),
    )
    for categoria, descripcion, valor in casos:
        try:
            ahorro.crear_proyeccion(bd, id_usuario, categoria, descripcion, valor)
        except ValueError:
            continue
        raise AssertionError(f"Se aceptó una meta inválida: {descripcion!r}")


def test_meta_rechaza_quincena_fuera_de_rango(bd) -> None:
    """Solo se admite la quincena 1 o la 2."""
    try:
        ahorro.crear_proyeccion(
            bd, _id_admin(bd), "Ahorro", "Quincena inválida", "100.000", quincena=3
        )
    except ValueError:
        return
    raise AssertionError("Se aceptó la quincena 3.")


# ---------------------------------------------------------------------------
# Servicio: abonos
# ---------------------------------------------------------------------------


def test_abono_unico_por_mes_actualiza_el_monto(bd) -> None:
    """Registrar dos veces el mismo mes corrige en lugar de duplicar."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_usuario, "Ahorro", "Viaje", "200.000", fecha_inicio=date(2026, 11, 1)
    )

    ahorro.registrar_abono(bd, id_usuario, meta.id_proyeccion, 2026, 11, "200.000")
    ahorro.registrar_abono(bd, id_usuario, meta.id_proyeccion, 2026, 11, "250.000")

    resumen = ahorro.resumen_metas(bd, id_usuario)[0]
    assert resumen.acumulado == Decimal("250000.00")
    assert sum(1 for mes in resumen.meses if mes.registrado) == 1


def test_abono_no_ajeno_devuelve_none(bd) -> None:
    """Ningún usuario puede abonar a la meta de otro."""
    id_admin = _id_admin(bd)
    cuenta = usuarios.buscar_por_correo(bd, "usuario@finanzas.co")
    assert cuenta is not None

    meta = ahorro.crear_proyeccion(
        bd, id_admin, "Ahorro", "Meta ajena", "100.000", fecha_inicio=date(2026, 11, 1)
    )
    assert (
        ahorro.registrar_abono(
            bd, cuenta.id_usuario, meta.id_proyeccion, 2026, 11, "100.000"
        )
        is None
    )
    assert (
        ahorro.eliminar_proyeccion(bd, cuenta.id_usuario, meta.id_proyeccion) is False
    )


def test_abono_rechaza_mes_invalido(bd) -> None:
    """El mes del abono debe estar entre 1 y 12."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_usuario, "Ahorro", "Mes inválido", "100.000", fecha_inicio=date(2026, 11, 1)
    )
    try:
        ahorro.registrar_abono(bd, id_usuario, meta.id_proyeccion, 2026, 13, "100.000")
    except ValueError:
        return
    raise AssertionError("Se aceptó el mes 13.")


def test_porcentaje_de_avance_tope_en_cien(bd) -> None:
    """El avance se calcula sobre el total y nunca supera el 100 %."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Meta corta",
        "100.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses=2,
        fecha_inicio=date(2026, 11, 1),
    )
    ahorro.registrar_abono(bd, id_usuario, meta.id_proyeccion, 2026, 11, "150.000")
    ahorro.registrar_abono(bd, id_usuario, meta.id_proyeccion, 2026, 12, "150.000")

    resumen = ahorro.resumen_metas(bd, id_usuario)[0]
    assert resumen.acumulado == Decimal("300000.00")
    assert resumen.porcentaje == Decimal("100.00")


# ---------------------------------------------------------------------------
# Servicio: diagnóstico de liquidez
# ---------------------------------------------------------------------------


def test_diagnostico_sin_gastos_no_alerta(bd) -> None:
    """Sin gastos fijos el saldo libre supera el umbral de alerta."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    resultado = ahorro.diagnostico(bd, id_usuario, perfil, 2026, 11)

    assert resultado["umbral"] == ahorro.UMBRAL_ALERTA
    assert resultado["alerta"] is False
    assert resultado["saldo_libre"] > ahorro.UMBRAL_ALERTA


def test_diagnostico_alerta_con_gastos_altos(bd) -> None:
    """Con gastos fijos que consumen el sueldo se dispara la alerta crítica."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    gastos.crear_gasto(
        bd,
        id_usuario,
        "Vivienda",
        "Arriendo",
        "2.800.000",
        date(2026, 11, 1),
        es_fijo=True,
        quincena=1,
    )

    resultado = ahorro.diagnostico(bd, id_usuario, perfil, 2026, 11)
    assert resultado["saldo_libre"] < ahorro.UMBRAL_ALERTA
    assert resultado["alerta"] is True


# ---------------------------------------------------------------------------
# HTTP: pestaña «Gastos y Presupuesto»
# ---------------------------------------------------------------------------


def test_presupuesto_exige_sesion(cliente) -> None:
    """La pestaña es privada: sin sesión redirige al login."""
    respuesta = cliente.get("/presupuesto", follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"].endswith("/login")


def test_presupuesto_muestra_banner_y_alerta(cliente_admin, bd) -> None:
    """La página presenta el diagnóstico y la advertencia de liquidez."""
    respuesta = cliente_admin.get("/presupuesto")
    assert respuesta.status_code == 200
    assert "Diagnóstico del mes" in respuesta.text
    assert "te sobran del sueldo" in respuesta.text

    # Con gastos fijos que se comen el sueldo, el banner crítico aparece.
    gastos.crear_gasto(
        bd,
        _id_admin(bd),
        "Vivienda",
        "Arriendo",
        "2.800.000",
        date(2026, 11, 1),
        es_fijo=True,
        quincena=1,
    )
    critica = cliente_admin.get("/presupuesto")
    assert "menos de $300.000" in critica.text
    assert "disminuir tus deudas" in critica.text


def test_presupuesto_crea_meta_por_formulario(cliente_admin, bd) -> None:
    """El formulario crea la meta y redirige con la bandera de guardado."""
    respuesta = cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "Fondo de emergencia",
            "valor_mensual": "300.000",
            "tipo_duracion": "LIMITADO",
            "meses": "4",
            "fecha_inicio": "2026-11-01",
            "quincena": "2",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/presupuesto?guardado=1"
    assert len(ahorro.listar_proyecciones(bd, _id_admin(bd))) == 1


def test_presupuesto_rechaza_meta_invalida(cliente_admin) -> None:
    """Una meta sin descripción vuelve al formulario con error 400."""
    respuesta = cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "",
            "valor_mensual": "100.000",
            "tipo_duracion": "FIJO",
            "quincena": "1",
        },
    )

    assert respuesta.status_code == 400
    assert "La descripción de la meta es obligatoria." in respuesta.text


def test_presupuesto_registra_y_corrige_abono(cliente_admin, bd) -> None:
    """El abono del mes se guarda y se puede corregir desde la página."""
    cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "Viaje",
            "valor_mensual": "200.000",
            "tipo_duracion": "FIJO",
            "fecha_inicio": "2026-11-01",
            "quincena": "1",
        },
        follow_redirects=False,
    )
    id_admin = _id_admin(bd)
    meta = ahorro.listar_proyecciones(bd, id_admin)[0]

    for valor in ("200.000", "250.000"):
        respuesta = cliente_admin.post(
            f"/presupuesto/metas/{meta.id_proyeccion}/abono",
            data={"anio": "2026", "mes": "11", "valor": valor},
            follow_redirects=False,
        )
        assert respuesta.status_code == 303

    resumen = ahorro.resumen_metas(bd, id_admin)[0]
    assert resumen.acumulado == Decimal("250000.00")


def test_presupuesto_elimina_meta(cliente_admin, bd) -> None:
    """El botón de eliminar borra la meta y sus abonos."""
    id_admin = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_admin, "Ahorro", "Meta temporal", "100.000", fecha_inicio=date(2026, 11, 1)
    )
    ahorro.registrar_abono(bd, id_admin, meta.id_proyeccion, 2026, 11, "100.000")

    respuesta = cliente_admin.post(
        f"/presupuesto/metas/{meta.id_proyeccion}/eliminar", follow_redirects=False
    )

    assert respuesta.status_code == 303
    assert ahorro.listar_proyecciones(bd, id_admin) == []


def test_presupuesto_bloqueado_para_usuario_publico(cliente_usuario) -> None:
    """`USER_FINANZAS` sí puede usar el planificador (módulo de Mis Finanzas)."""
    respuesta = cliente_usuario.get("/presupuesto")
    assert respuesta.status_code == 200
    assert "Proyectar una meta" in respuesta.text
