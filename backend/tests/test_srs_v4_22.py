"""Pruebas de la SRS v4.22: barras comparativas por deuda recomendada.

El componente visual se renderiza en Jinja2/CSS, pero sus cifras las calcula
Python en `consejero.py`. Estas pruebas blindan las fórmulas y la plataforma.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import chancucos, consejero, deudas, usuarios


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


def _consejo_con_deudas(bd):
    """Siembra tres deudas y devuelve el consejo con excedente amplio.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Consejo financiero ya calculado.
    """
    id_usuario = _id_admin(bd)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar", "197568", "16464", 12)
    deudas.crear_deuda(bd, id_usuario, "Alkomprar 2", "288395", "57679", 5)
    deudas.crear_deuda(bd, id_usuario, "Addi", "385100", "50000", 8)
    return consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("2000000"))


def test_cierre_expone_barras_por_deuda_recomendada(bd) -> None:
    """Cada deuda del plan lleva saldo, cuota, plazos y porcentaje."""
    resultado = _consejo_con_deudas(bd)
    barras = resultado.cierre["barras_deuda"]

    assert len(barras) == 3
    assert {barra["nombre"] for barra in barras} == {"Alkomprar", "Alkomprar 2", "Addi"}
    for barra in barras:
        assert barra["id_deuda"]
        assert barra["saldo"] > 0
        assert barra["cuota"] > 0
        assert barra["meses_base"] >= 1
        assert barra["meses_excedente"] >= 1
        assert barra["fecha_cierre_base"]
        assert 0 <= barra["porcentaje_ahorro"] <= 100


def test_formulas_de_ahorro_por_barra(bd) -> None:
    """Ahorro = MAX(0, base − excedente) y porcentaje redondeado."""
    barras = _consejo_con_deudas(bd).cierre["barras_deuda"]

    for barra in barras:
        base = barra["meses_base"]
        optimo = barra["meses_excedente"]
        assert optimo <= base
        assert barra["meses_ahorrados"] == max(0, base - optimo)
        assert barra["porcentaje_ahorro"] == round(((base - optimo) / base) * 100)


def test_resumen_global_usa_max_base_y_primera_deuda(bd) -> None:
    """El encabezado toma el mayor plazo base y el objetivo del plan."""
    resultado = _consejo_con_deudas(bd)
    resumen = resultado.cierre["resumen_barras"]
    barras = resultado.cierre["barras_deuda"]

    max_base = max(barra["meses_base"] for barra in barras)
    objetivo = barras[0]["meses_excedente"]
    assert resumen["max_base"] == max_base
    assert resumen["meses_objetivo"] == objetivo
    assert resumen["porcentaje_global"] == max(
        0, round(((max_base - objetivo) / max_base) * 100)
    )
    assert resumen["meses_base_texto"] == (
        f"{max_base} {'mes' if max_base == 1 else 'meses'}"
    )
    assert resumen["meses_objetivo_texto"] == (
        f"{objetivo} {'mes' if objetivo == 1 else 'meses'}"
    )


def test_mis_finanzas_muestra_logo_en_el_encabezado(cliente_admin: TestClient) -> None:
    """El módulo muestra el logo oficial a 30 px, igual que OLB_BYTE."""
    html = cliente_admin.get("/finanzas").text

    assert 'class="modulo__icono"' in html
    assert "img/icono-192.png" in html
    assert 'alt="Mis Finanzas" width="30" height="30"' in html


def test_chancucos_no_ofrece_favorito(cliente_admin: TestClient, bd) -> None:
    """«Configurar atajos de pago» no muestra la opción de favorito."""
    id_usuario = _id_admin(bd)
    chancucos.crear_chancuco(bd, id_usuario, "EPM energía", "123456", "")

    html = cliente_admin.get("/chancucos").text

    assert "Marcar como favorito" not in html
    assert 'name="favorito"' not in html
    assert "alternar_favorito" not in html
    assert ">Favorito</th>" not in html
    assert "★" not in html and "☆" not in html
    # La tabla pasa de seis columnas a cinco.
    assert "<th scope=\"col\">Descripción</th>" in html
    assert "<th scope=\"col\">Acciones</th>" in html


def test_sin_deudas_no_hay_barras(bd) -> None:
    """Sin plan de deudas el componente no recibe datos que dibujar."""
    id_usuario = _id_admin(bd)
    resultado = consejero.consejo_financiero(bd, id_usuario, "Ana", Decimal("900000"))

    assert resultado.cierre.get("barras_deuda", []) == []
    assert resultado.cierre.get("resumen_barras", {}).get("max_base", 1) == 1
