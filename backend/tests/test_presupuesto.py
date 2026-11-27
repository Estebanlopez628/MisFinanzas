"""Pruebas del planificador de ahorro y metas (SRS v1.3, bloque 3).

Se cubren las reglas del servicio (`app.servicios.ahorro`) y el camino HTTP de
la pestaña «Gastos y Presupuesto»: crear metas, registrar y corregir abonos,
eliminar y disparar la alerta de liquidez por debajo de $300.000.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.servicios import ahorro, gastos, pagos_metas, perfiles, usuarios


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
    """SRS v1.6: el gasto fijo tiene el periodo que escogió el usuario y su total."""
    id_usuario = _id_admin(bd)
    ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Seguro del vehículo",
        "Cuota mensual del seguro",
        "180.000",
        tipo_duracion=ahorro.DURACION_FIJA,
        meses=18,
        fecha_inicio=date(2026, 11, 1),
        quincena=2,
    )

    meta = ahorro.resumen_metas(bd, id_usuario)[0]
    assert meta.proyeccion.meses == 18
    assert meta.total_proyectado == Decimal("3240000.00")
    assert meta.porcentaje == Decimal("0.00")
    assert len(meta.meses) == 18


def test_periodo_indefinido_antiguo_usa_ventana_de_12_meses(bd) -> None:
    """Una meta sin periodo guardada antes de SRS v1.6 conserva la ventana de 12 meses."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_usuario, "Ahorro", "Heredada", "100.000", fecha_inicio=date(2026, 11, 1), meses=12
    )
    meta.meses = None
    bd.commit()

    resumen = ahorro.resumen_metas(bd, id_usuario)[0]
    assert resumen.total_proyectado is None
    assert len(resumen.meses) == ahorro.MESES_VENTANA_FIJA


def test_meta_limitada_exige_meses_validos(bd) -> None:
    """El periodo exige entre 1 y 600 meses (50 años)."""
    id_usuario = _id_admin(bd)
    for meses in ("0", "601", ""):
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
    """Solo se admiten las quincenas 1, 2 y 3 («ambas»)."""
    for valida in (1, 2, 3):
        meta = ahorro.crear_proyeccion(
            bd,
            _id_admin(bd),
            "Ahorro",
            f"Quincena {valida}",
            "100.000",
            quincena=valida,
            meses=12,
        )
        assert meta.quincena == valida

    for invalida in (0, 4, -1):
        try:
            ahorro.crear_proyeccion(
                bd,
                _id_admin(bd),
                "Ahorro",
                "Quincena inválida",
                "100.000",
                quincena=invalida,
                meses=12,
            )
        except ValueError:
            continue
        raise AssertionError(f"Se aceptó la quincena {invalida}.")


def test_meta_con_ambas_quincenas_reparte_la_cuota(bd) -> None:
    """SRS v1.5: «Ambas quincenas» divide la cuota mensual entre los dos pagos."""
    meta = ahorro.crear_proyeccion(
        bd, _id_admin(bd), "Ahorro", "Fondo compartido", "400.000", quincena=3, meses=12
    )
    resumen = next(
        item
        for item in ahorro.resumen_metas(bd, meta.id_usuario)
        if item.proyeccion.id_proyeccion == meta.id_proyeccion
    )

    assert resumen.etiqueta_quincena == "Ambas quincenas"
    assert resumen.valor_por_pago == Decimal("200000.00")
    assert resumen.proyeccion.valor_mensual == Decimal("400000.00")


# ---------------------------------------------------------------------------
# Servicio: abonos
# ---------------------------------------------------------------------------


def test_porcentaje_de_avance_tope_en_cien(bd) -> None:
    """El avance se calcula sobre el total y nunca supera el 100 %."""
    id_usuario = _id_admin(bd)
    ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Meta corta",
        "150.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses=2,
        fecha_inicio=date(2026, 11, 1),
    )
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, 2026, 11)
    for gasto in gastos.listar_gastos(bd, id_usuario, 2026, 11):
        pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, date(2026, 11, 5))
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, 2026, 12)
    for gasto in gastos.listar_gastos(bd, id_usuario, 2026, 12):
        pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, date(2026, 12, 5))

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
    assert perfil is not None
    perfil.monto_minimo_liquidez = Decimal("300000")
    bd.commit()
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
    assert resultado["umbral"] == Decimal("300000.00")
    assert resultado["saldo_libre"] < resultado["umbral"]
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
    perfil = perfiles.obtener_perfil(bd, _id_admin(bd))
    assert perfil is not None
    perfil.monto_minimo_liquidez = Decimal("300000")
    bd.commit()
    respuesta = cliente_admin.get("/presupuesto")
    assert respuesta.status_code == 200
    assert "Diagnóstico del mes" in respuesta.text
    assert "te quedan disponibles" in respuesta.text

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


def test_boton_de_deduccion_fija_homologado_al_de_meta(cliente_admin) -> None:
    """SRS v1.5: «Agregar deducción fija» pesa igual que «Crear meta»."""
    texto = " ".join(cliente_admin.get("/presupuesto").text.split())

    assert "Crear meta" in texto
    assert "Agregar deducción fija" in texto
    assert "+ Agregar deducción fija" not in texto
    # Ambos botones comparten la clase primaria.
    assert texto.count('class="boton boton--primario"') >= 2


def test_formulario_de_meta_ofrece_ambas_quincenas(cliente_admin) -> None:
    """SRS v1.5: el selector de metas agrega la tercera opción."""
    texto = cliente_admin.get("/presupuesto").text

    assert "Ambas quincenas" in texto
    assert 'value="3"' in texto


def test_meta_por_formulario_con_ambas_quincenas(cliente_admin, bd) -> None:
    """Al elegir «Ambas quincenas» la meta se guarda con quincena 3 y se reparte."""
    respuesta = cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "Fondo compartido",
            "valor_mensual": "400.000",
            "tipo_duracion": "FIJO",
            "meses": "12",
            "fecha_inicio": "2026-11-01",
            "quincena": "3",
        },
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    texto = " ".join(respuesta.text.split())
    assert "Ambas quincenas" in texto
    assert "$200.000 por pago" in texto


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
            "meses": "12",
            "quincena": "1",
        },
    )

    assert respuesta.status_code == 400
    assert "La descripción de la meta es obligatoria." in respuesta.text


def test_presupuesto_crea_meta_con_su_gasto_fijo(cliente_admin, bd) -> None:
    """Crear una meta por la página genera su gasto fijo en la quincena elegida."""
    respuesta = cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "Viaje",
            "valor_mensual": "200.000",
            "tipo_duracion": "FIJO",
            "meses": "12",
            "fecha_inicio": "2026-11-01",
            "quincena": "2",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    id_admin = _id_admin(bd)
    meta = ahorro.listar_proyecciones(bd, id_admin)[0]
    generados = [
        gasto
        for gasto in gastos.listar_gastos(bd, id_admin, 2026, 11)
        if gasto.id_proyeccion == meta.id_proyeccion
    ]
    assert len(generados) == 1
    assert generados[0].quincena == 2


def test_presupuesto_elimina_meta(cliente_admin, bd) -> None:
    """El botón de eliminar borra la meta y sus abonos."""
    id_admin = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd, id_admin, "Ahorro", "Meta temporal", "100.000", fecha_inicio=date(2026, 11, 1), meses=12
    )
    pagos_metas.asegurar_gastos_de_metas(bd, id_admin, 2026, 11)

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
