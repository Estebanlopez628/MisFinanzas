"""Pruebas del panel de quincenas y del layout interno de "Mis Finanzas".

Cubren el cálculo del saldo libre por quincena (ingreso proyectado, gastos
fijos y deducciones de ley imputadas a la quincena del perfil) y la integración
de Gastos y Chancucos dentro de la vista principal (SRS v1.2, bloque 3).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import gastos, perfiles, quincenas, usuarios


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de la cuenta `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_resumen_imputa_deducciones_a_la_quincena_del_perfil(bd) -> None:
    """Salud y pensión del mes se descuentan solo en la quincena elegida."""
    id_usuario = _id_admin(bd)
    gastos.crear_gasto(
        bd, id_usuario, "Hogar", "Arriendo", "100.000", date(2026, 11, 1), quincena=1
    )
    gastos.crear_gasto(
        bd, id_usuario, "Transporte", "Gasolina", "200.000", date(2026, 11, 16), quincena=2
    )
    # Gasto anterior al SRS v1.2: sin quincena, se muestra en la primera.
    gastos.crear_gasto(
        bd, id_usuario, "Servicios", "Internet", "50.000", date(2026, 11, 5)
    )

    perfil = perfiles.obtener_perfil(bd, id_usuario)
    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, 2026, 11)

    assert len(resumen) == 2
    primera, segunda = resumen

    # SRS v4.8: 1.480.000 por quincena; el auxilio de 249.095 va al corte de
    # deducciones (aquí, la quincena 1).
    assert primera.ingreso == Decimal("1729095.00")
    assert segunda.ingreso == Decimal("1480000.00")

    # Deducciones de ley (8 % de 2.960.000 = 236.800) en la quincena 1.
    deducciones_mes = Decimal("236800.00")
    assert primera.deducciones == deducciones_mes
    assert segunda.deducciones == Decimal("0.00")

    # La primera quincena absorbe el gasto sin quincena asignada.
    assert primera.gastos == Decimal("150000.00")
    assert segunda.gastos == Decimal("200000.00")
    assert primera.saldo_libre == Decimal("1342295.00")
    assert segunda.saldo_libre == Decimal("1280000.00")
    assert primera.mes_completo is True
    assert segunda.mes_completo is False


def test_resumen_mensual_devuelve_una_sola_tarjeta(bd) -> None:
    """En modalidad MENSUAL hay una tarjeta con el sueldo completo."""
    id_usuario = _id_admin(bd)
    perfiles.guardar_perfil(bd, id_usuario, "2.960.000", perfiles.MODALIDAD_MENSUAL)
    gastos.crear_gasto(
        bd, id_usuario, "Hogar", "Arriendo", "800.000", date(2026, 11, 1)
    )

    perfil = perfiles.obtener_perfil(bd, id_usuario)
    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, 2026, 11)

    assert len(resumen) == 1
    tarjeta = resumen[0]
    assert tarjeta.numero == 0
    assert tarjeta.etiqueta == "Mes completo"
    assert tarjeta.ingreso == Decimal("3209095.00")
    assert tarjeta.gastos == Decimal("800000.00")
    assert tarjeta.deducciones == Decimal("236800.00")
    assert tarjeta.saldo_libre == Decimal("2172295.00")


def test_gasto_por_quincena_filtra_totales(bd) -> None:
    """El servicio separa los gastos de cada quincena."""
    id_usuario = _id_admin(bd)
    gastos.crear_gasto(
        bd, id_usuario, "Hogar", "Arriendo", "100.000", date(2026, 11, 1), quincena=1
    )
    gastos.crear_gasto(
        bd, id_usuario, "Transporte", "Gasolina", "200.000", date(2026, 11, 16), quincena=2
    )

    assert gastos.total_gastos_quincena(bd, id_usuario, 2026, 11, 1) == Decimal("100000.00")
    assert gastos.total_gastos_quincena(bd, id_usuario, 2026, 11, 2) == Decimal("200000.00")
    assert gastos.total_gastos_mes(bd, id_usuario, 2026, 11) == Decimal("300000.00")


def test_gasto_rechaza_quincena_invalida(bd) -> None:
    """Solo se admiten las quincenas 1 y 2."""
    try:
        gastos.crear_gasto(
            bd,
            _id_admin(bd),
            "Hogar",
            "Error",
            "1000",
            date(2026, 11, 1),
            quincena=3,
        )
    except ValueError as error:
        assert "quincena" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_vista_finanzas_muestra_dos_quincenas(cliente_admin: TestClient) -> None:
    """El layout de dos columnas pinta una tarjeta por quincena."""
    respuesta = cliente_admin.get("/finanzas")

    assert respuesta.status_code == 200
    # SRS v1.4, REQ-01: sin encabezado intermedio, la columna empieza en la tarjeta.
    assert 'aria-label="Quincenas, gastos fijos y atajos de pago"' in respuesta.text
    assert 'data-quincena="1"' in respuesta.text
    assert 'data-quincena="2"' in respuesta.text
    assert "Saldo libre restante" in respuesta.text
    # La plantilla "Semana típica" se retiró del layout.
    assert "Semana típica" not in respuesta.text


def test_gasto_creado_desde_finanzas_vuelve_al_panel(
    cliente_admin: TestClient,
) -> None:
    """El alta embebida redirige al ancla de quincenas."""
    respuesta = cliente_admin.post(
        "/gastos",
        data={
            "categoria": "Transporte",
            "descripcion": "Gasolina",
            "valor": "120.000",
            "fecha": "2026-11-10",
            "es_fijo": "1",
            "quincena": "2",
            "origen": "finanzas",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/finanzas?guardado_gasto=1#quincenas"
    html = cliente_admin.get("/finanzas").text
    assert "Gasolina" in html
    assert "guardado_gasto" not in html


def test_chancucos_embebidos_solo_para_administrador(
    cliente_admin: TestClient, cliente_usuario: TestClient
) -> None:
    """El panel embebido aparece para ADMIN_OLB y se oculta al usuario público."""
    respuesta = cliente_admin.post(
        "/chancucos",
        data={
            "descripcion": "EPM energía",
            "numero_referencia": "123456",
            "url_pago": "https://epm.com.co/pagos",
            "origen": "finanzas",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/finanzas?guardado_chancuco=1#chancucos"

    # SRS v1.4, REQ-07: la vista de liquidación solo consulta los atajos; la
    # administración vive en la pestaña "Configurar Atajos de Pago".
    html_admin = cliente_admin.get("/finanzas").text
    assert "🔗 Atajos de pago" in html_admin
    assert "123456" in html_admin
    assert 'data-copiar="123456"' in html_admin
    assert "https://epm.com.co/pagos" in html_admin
    assert "🔗 Configurar atajos de pago" not in html_admin
    assert "Guardar atajo de pago" not in html_admin

    html_gestion = cliente_admin.get("/chancucos").text
    assert "123456" in html_gestion

    html_usuario = cliente_usuario.get("/finanzas").text
    assert "123456" not in html_usuario


def test_liquidacion_json_imputa_deducciones_a_la_quincena_del_perfil(
    cliente_admin: TestClient,
) -> None:
    """La quincena 1 concentra salud y pensión del mes completo; la 2 no."""
    respuesta = cliente_admin.post(
        "/finanzas/calcular",
        json={"anio": 2026, "mes": 11, "quincena": 1},
    )

    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    # 4 % de 2.960.000 (sueldo mensual del perfil) = 118.400 por concepto.
    assert cuerpo["datos"]["deduccion_salud"] == "$118.400"
    assert cuerpo["datos"]["deduccion_pension"] == "$118.400"

    respuesta = cliente_admin.post(
        "/finanzas/calcular",
        json={"anio": 2026, "mes": 11, "quincena": 2},
    )

    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    assert cuerpo["datos"]["deduccion_salud"] == "$0"
    assert cuerpo["datos"]["deduccion_pension"] == "$0"


def test_gastos_del_periodo_separan_las_quincenas(
    bd, cliente_admin: TestClient
) -> None:
    """El panel derecho solo descuenta los gastos de la quincena consultada."""
    gastos.crear_gasto(
        bd,
        _id_admin(bd),
        "Transporte",
        "Gasolina",
        "120.000",
        date(2026, 11, 16),
        quincena=2,
    )

    # El texto del HTML puede partirse en varias líneas; se normalizan los espacios.
    html_quincena_2 = " ".join(
        cliente_admin.get("/finanzas?anio=2026&mes=11&quincena=2").text.split()
    )
    assert "Gastos del periodo: $120.000" in html_quincena_2

    html_quincena_1 = " ".join(
        cliente_admin.get("/finanzas?anio=2026&mes=11&quincena=1").text.split()
    )
    assert "Gastos del periodo: $0" in html_quincena_1
