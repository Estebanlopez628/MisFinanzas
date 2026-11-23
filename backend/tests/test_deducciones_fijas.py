"""Pruebas de SRS v1.4: deducciones fijas del salario y recálculo por quincena.

Cubren:
- REQ-08: alta, edición, eliminación y validación de deducciones fijas, y su
  resta del saldo libre de la quincena indicada.
- REQ-04: los recargos se suman al ingreso de la quincena de deducciones.
- REQ-05: el descuento por incapacidad reduce el sueldo base antes del reparto.
- Recálculo en vivo: el endpoint JSON devuelve los saldos por quincena.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.numeros import redondear_dinero
from app.core.texto import formatear_cop
from app.servicios import deducciones_fijas, perfiles, quincenas, usuarios
from app.servicios.incapacidad import liquidar_mes_incapacidad
from app.servicios.nomina import calcular_deducciones_ley


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


def _perfil_40_60(bd, id_usuario: str, sueldo: str = "3.484.000") -> None:
    """Configura un perfil quincenal con 40 % / 60 % y deducciones en la quincena 2.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil.
        sueldo: Sueldo básico mensual.
    """
    perfiles.guardar_perfil(bd, id_usuario, sueldo, "QUINCENAL", "40", "60", 2)


# ---------------------------------------------------------------------------
# REQ-08: servicio de deducciones fijas
# ---------------------------------------------------------------------------


def test_crear_listar_actualizar_y_eliminar(bd) -> None:
    """El ciclo completo de una deducción fija funciona sobre la base de datos."""
    id_usuario = _id_admin(bd)
    creada = deducciones_fijas.crear_deduccion(
        bd, id_usuario, "Libranza banco X", "120.000", 1
    )
    assert creada.valor == Decimal("120000.00")
    assert len(deducciones_fijas.listar_deducciones(bd, id_usuario)) == 1

    actualizada = deducciones_fijas.actualizar_deduccion(
        bd, id_usuario, creada.id_deduccion, "Libranza banco X", "150.000", 2
    )
    assert actualizada is not None
    assert actualizada.valor == Decimal("150000.00")
    assert actualizada.quincena == 2

    assert deducciones_fijas.eliminar_deduccion(bd, id_usuario, creada.id_deduccion)
    assert deducciones_fijas.listar_deducciones(bd, id_usuario) == []


def test_deduccion_rechaza_datos_invalidos(bd) -> None:
    """Descripción vacía, valor negativo y quincena fuera de rango se rechazan."""
    id_usuario = _id_admin(bd)
    casos = (
        ("", "100.000", 1),
        ("Fondo", "-5", 1),
        ("Fondo", "100.000", 3),
    )
    for descripcion, valor, quincena in casos:
        try:
            deducciones_fijas.crear_deduccion(bd, id_usuario, descripcion, valor, quincena)
        except ValueError:
            continue
        raise AssertionError(f"Se aceptó una deducción inválida: {descripcion!r}")


def test_deduccion_ajena_no_se_edita_ni_elimina(bd) -> None:
    """Un usuario no puede modificar ni borrar la deducción de otro."""
    id_admin = _id_admin(bd)
    cuenta = usuarios.buscar_por_correo(bd, "usuario@finanzas.co")
    assert cuenta is not None
    creada = deducciones_fijas.crear_deduccion(bd, id_admin, "Fondo", "50.000", 1)

    assert (
        deducciones_fijas.actualizar_deduccion(
            bd, cuenta.id_usuario, creada.id_deduccion, "Fondo", "1", 1
        )
        is None
    )
    assert deducciones_fijas.eliminar_deduccion(bd, cuenta.id_usuario, creada.id_deduccion) is False


# ---------------------------------------------------------------------------
# REQ-08: resta del saldo libre por quincena
# ---------------------------------------------------------------------------


def test_deduccion_fija_reduce_solo_su_quincena(bd) -> None:
    """Una cuota de la quincena 2 no afecta el saldo de la quincena 1."""
    id_usuario = _id_admin(bd)
    perfil = perfiles.guardar_perfil(bd, id_usuario, "3.000.000", "QUINCENAL", "50", "50", 1)
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Libranza", "200.000", 2)

    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, 2026, 11)
    q1, q2 = resumen

    assert q1.deducciones_fijas == Decimal("0.00")
    assert q2.deducciones_fijas == Decimal("200000.00")
    assert q2.saldo_libre == q2.ingreso - q2.gastos - q2.deducciones - Decimal("200000.00")
    assert q1.saldo_libre == q1.ingreso - q1.gastos - q1.deducciones


# ---------------------------------------------------------------------------
# REQ-04 y REQ-05: recargos e incapacidad en el ingreso de cada quincena
# ---------------------------------------------------------------------------


def test_incapacidad_reduce_el_sueldo_antes_del_reparto(bd) -> None:
    """Ejemplo del SRS: 3.484.000 − 1.000.000 = 2.484.000, repartido 40 % / 60 %."""
    id_usuario = _id_admin(bd)
    _perfil_40_60(bd, id_usuario)
    perfil = perfiles.obtener_perfil(bd, id_usuario)

    q1, q2 = quincenas.resumen_quincenas(
        bd, id_usuario, perfil, 2026, 11, descuento_incapacidad=Decimal("1000000")
    )

    assert q1.ingreso == Decimal("993600.00")
    assert q2.ingreso == Decimal("1739495.00")  # 60 % + auxilio de 249.095


def test_recargos_se_suman_a_la_quincena_de_deducciones(bd) -> None:
    """Las horas extras entran en la quincena que el perfil marca para deducciones."""
    id_usuario = _id_admin(bd)
    _perfil_40_60(bd, id_usuario, "3.000.000")
    perfil = perfiles.obtener_perfil(bd, id_usuario)

    q1, q2 = quincenas.resumen_quincenas(
        bd, id_usuario, perfil, 2026, 11, recargos=Decimal("150000")
    )

    assert q1.ingreso == Decimal("1200000.00")
    assert q2.ingreso == Decimal("1800000.00") + Decimal("150000.00") + Decimal("249095.00")


# ---------------------------------------------------------------------------
# Recálculo en vivo: endpoint JSON
# ---------------------------------------------------------------------------


def test_json_devuelve_saldos_por_quincena_con_recargos(
    cliente_admin: TestClient, bd
) -> None:
    """El cálculo en vivo devuelve el saldo de cada quincena ya ajustado."""
    id_usuario = _id_admin(bd)
    _perfil_40_60(bd, id_usuario, "3.000.000")
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Libranza", "100.000", 1)

    respuesta = cliente_admin.post(
        "/finanzas/calcular",
        json={
            "anio": 2026,
            "mes": 11,
            "quincena": 0,
            "sueldo_basico": "3.000.000",
            "horas_EXTRA_NOCTURNA": "10",
        },
    )

    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    filas = {fila["numero"]: fila for fila in cuerpo["quincenas"]}
    assert set(filas) == {1, 2}
    # SRS v4.13: el JSON ya no expone las fijas por separado; el `ingreso` de
    # la tarjeta es el neto real del corte, con ley y fijas descontadas.
    assert "deducciones_fijas" not in filas[1]
    assert filas[1]["ingreso"].startswith("$")
    # Los recargos y las fijas hacen que los cortes difieran.
    assert filas[2]["ingreso"] != filas[1]["ingreso"]
    assert "saldo_libre" in filas[2]


# ---------------------------------------------------------------------------
# HTTP: gestión en «Gastos y Presupuesto»
# ---------------------------------------------------------------------------


def test_presupuesto_crea_y_elimina_deduccion_por_formulario(cliente_admin, bd) -> None:
    """El formulario de deducciones fijas crea el registro y el botón lo elimina."""
    respuesta = cliente_admin.post(
        "/presupuesto/deducciones",
        data={"descripcion": "Libranza banco X", "valor": "120.000", "quincena": "1"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    lista = deducciones_fijas.listar_deducciones(bd, _id_admin(bd))
    assert len(lista) == 1

    eliminacion = cliente_admin.post(
        f"/presupuesto/deducciones/{lista[0].id_deduccion}/eliminar",
        follow_redirects=False,
    )
    assert eliminacion.status_code == 303
    assert deducciones_fijas.listar_deducciones(bd, _id_admin(bd)) == []


def test_presupuesto_ya_no_muestra_registro_de_gastos_fijos(cliente_admin) -> None:
    """SRS v1.4, REQ-08: el botón redundante de registrar gastos fijos se quita."""
    texto = cliente_admin.get("/presupuesto").text
    assert "Registrar gastos fijos" not in texto
    assert "Deducciones fijas del salario" in texto


def test_liquidacion_lista_las_deducciones_fijas(cliente_admin, bd) -> None:
    """SRS v1.5: la caja muestra cada deducción fija y el total del periodo."""
    deducciones_fijas.crear_deduccion(bd, _id_admin(bd), "Libranza", "80.000", 2)
    texto = " ".join(cliente_admin.get("/finanzas").text.split())
    assert "Deducciones fijas del salario" in texto
    assert "Libranza" in texto
    assert "Total de deducciones de ley" in texto
    assert "data-total-deducciones" in texto
    # El total agregado anterior desaparece: ahora se listan los conceptos.
    assert "data-deducciones-fijas" not in texto


def test_caja_de_deducciones_suma_ley_incapacidad_y_fijas(
    cliente_admin: TestClient, bd
) -> None:
    """El total de la caja suma salud, pensión, incapacidad del mes y fijas."""
    deducciones_fijas.crear_deduccion(bd, _id_admin(bd), "Libranza", "80.000", 1)

    respuesta = cliente_admin.post(
        "/finanzas/calcular",
        json={
            "anio": 2026,
            "mes": 11,
            "quincena": 0,
            "sueldo_basico": "2.960.000",
            "incapacidad_inicio": "2026-11-15",
            "incapacidad_fin": "2026-11-30",
        },
    )

    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True

    # La base de cotización es el devengado menos la incapacidad del mes.
    descuento = liquidar_mes_incapacidad(
        date(2026, 11, 15),
        date(2026, 11, 30),
        Decimal("2960000"),
        anio=2026,
        mes=11,
    ).valor_descontado
    base = Decimal("2960000") - descuento
    esperado = redondear_dinero(
        calcular_deducciones_ley(base).total + descuento + Decimal("80000")
    )

    assert cuerpo["datos"]["deduccion_incapacidad"] == formatear_cop(descuento)
    assert cuerpo["deducciones_fijas_periodo"] == "$80.000"
    assert cuerpo["total_deducciones_ley"] == formatear_cop(esperado)
