"""Pruebas de la SRS v4.10 (doble descuento, resultado y desglose)."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.servicios import gastos, perfiles, usuarios


def _id_admin(bd) -> str:
    """Devuelve el identificador del administrador sembrado.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador del administrador de pruebas.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def _preparar(bd) -> None:
    """Configura el caso base 40/60 con auxilio y gastos del corte.

    Args:
        bd: Sesión de base de datos.
    """
    id_usuario = _id_admin(bd)
    perfiles.guardar_perfil(
        bd,
        id_usuario,
        "3.484.000",
        perfiles.MODALIDAD_QUINCENAL,
        "40",
        "60",
        2,
        dia_quincena_1=15,
        dia_quincena_2=30,
    )

def test_tarjetas_no_restan_dos_veces_la_ley(cliente_admin: TestClient, bd) -> None:
    """Las tarjetas muestran el sueldo neto de ley y no repiten la fila."""
    _preparar(bd)
    html = cliente_admin.get("/finanzas").text
    assert "data-deducciones-quincena" not in html
    assert "descontados en esta" not in html
    assert "2.060.775" in html


def test_resultado_tiene_salto_y_total_de_gastos(cliente_admin: TestClient, bd) -> None:
    """La nota del resultado se divide en dos líneas con el total del mes."""
    _preparar(bd)
    html = cliente_admin.get("/finanzas").text
    assert ">TOTAL DEVENGADO<" in html
    assert "Ingresos totales menos deducciones de ley e incapacidad.<br />" in html
    assert "Total de Gastos del mes:" in html
    assert 'data-campo="total_gastos_mes"' in html


def test_orden_contable_de_las_nueve_filas(cliente_admin: TestClient, bd) -> None:
    """Primero los positivos hasta Total ingresos; después los negativos."""
    _preparar(bd)
    html = cliente_admin.get("/finanzas").text
    inicio = html.index('<ul class="lista-parametros">')
    fin = html.index("</ul>", inicio)
    bloque = html[inicio:fin]
    campos = re.findall(r'data-campo="([^"]+)"', bloque)
    assert campos == [
        "valor_hora",
        "total_recargos",
        "total_devengado",
        "auxilio_transporte",
        "total_ingresos",
        "deduccion_salud",
        "deduccion_pension",
        "deduccion_incapacidad",
        "total_deducciones",
    ]
    for etiqueta in (
        "Valor hora ordinaria",
        "Horas extras y recargos",
        "Total devengado (sueldo + recargos)",
        "Auxilio de transporte",
        "Total ingresos",
        "Salud (4,00 %)",
        "Pensión (4,00 %)",
        "Descuento por incapacidad",
        "Total deducciones",
    ):
        assert etiqueta in bloque, etiqueta
    assert "lista-parametros__separador" in bloque
    assert "Disponible después de gastos" not in bloque


def test_dona_global_permanece_intacta(cliente_admin: TestClient, bd) -> None:
    """El ajuste visual no altera la base ni los arcos de la dona global."""
    html = cliente_admin.get("/presupuesto").text
    assert "dona__desglose" in html
    assert "Ingreso global del mes:" in html
    assert 'data-leyenda-etiqueta="Total libre"' in html


def test_pago_mensual_tampoco_duplica_la_ley(cliente_admin: TestClient, bd) -> None:
    """En pago único mensual la tarjeta tampoco resta dos veces la ley."""
    id_usuario = _id_admin(bd)
    perfiles.guardar_perfil(bd, id_usuario, "3.484.000", perfiles.MODALIDAD_MENSUAL)
    html = cliente_admin.get("/finanzas").text
    assert "data-deducciones-quincena" not in html
    assert "3.454.375" in html
    assert "3.733.095" not in html


def test_json_expone_el_total_de_gastos(cliente_usuario: TestClient) -> None:
    """El recálculo reactivo actualiza la nueva nota."""
    respuesta = cliente_usuario.post(
        "/finanzas/calcular", json={"sueldo_basico": "3.484.000"}
    )
    assert respuesta.status_code == 200
    assert "total_gastos_mes" in respuesta.json()["datos"]
