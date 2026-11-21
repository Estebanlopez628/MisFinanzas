"""Pruebas del flujo condicional de vinculación (SRS v1.9, sección 3.2).

Cubren la pregunta SI/NO al elegir «Créditos y Obligaciones», el listado de
todas las deudas activas, el acceso rápido al módulo de deudas, el regreso con
la deuda recién creada y la preservación en `sessionStorage`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, trabajos, usuarios

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"
MENSAJE_NO = (
    "Debes registrar tu deuda en el módulo Registro y Detalles de deudas "
    "para poder guardar este registro"
)


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


def test_la_pregunta_condicional_aparece_en_los_tres_modulos(
    cliente_admin: TestClient, bd
) -> None:
    """Cada módulo muestra su texto exacto y la opción NO con el acceso rápido."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    trabajo = trabajos.crear_trabajo(bd, cuenta.id_usuario, "Diseño", "600.000", date.today())
    trabajos.asegurar_pagos_trabajos(bd, cuenta.id_usuario, date.today().year, date.today().month)
    assert trabajo is not None

    casos = (
        ("/presupuesto", "¿Esta deducción corresponde a una de tus deudas registradas?", "deducciones"),
        ("/finanzas", "¿Este crédito corresponde a una de tus deudas registradas?", "finanzas"),
        ("/trabajos-extras", "¿Este crédito corresponde a una de tus deudas registradas?", "trabajos"),
    )
    for ruta, texto, modulo in casos:
        html = cliente_admin.get(ruta).text
        assert "data-vinculo-condicional" in html
        assert texto in html
        assert 'value="SI"' in html
        assert 'value="NO"' in html
        assert MENSAJE_NO in html
        assert "Ve a registrar la deuda" in html
        assert f"data-origen=\"{modulo}\"" in html
        assert f"volver={modulo}" in html


def test_el_desplegable_lista_todas_las_deudas_activas(
    cliente_admin: TestClient, bd
) -> None:
    """Se ofrecen deudas mensuales y quincenales activas."""
    id_usuario = _id_admin(bd)
    mensual = deudas.crear_deuda(bd, id_usuario, "Banco Mensual", "1200000", "400000", 3)
    quincenal = deudas.crear_deuda(
        bd, id_usuario, "Tienda Quincenal", "800000", "100000", 8,
        periodicidad=deudas.PERIODICIDAD_QUINCENAL
    )

    html = cliente_admin.get("/presupuesto").text

    assert "Deudas registradas" in html
    assert mensual.id_deuda in html
    assert quincenal.id_deuda in html
    assert "Banco Mensual" in html
    assert "Tienda Quincenal" in html


def test_el_regreso_al_modulo_de_origen_lleva_la_deuda_reciente(
    cliente_admin: TestClient, bd
) -> None:
    """El botón de regreso apunta al módulo correcto y al id de la deuda creada."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)

    html = cliente_admin.get("/deudas?volver=deducciones").text

    assert "Volver al formulario de origen" in html
    assert f"deuda_id={deuda.id_deuda}" in html
    assert 'href="/presupuesto?guardado_deuda=1' in html


def test_el_backend_exige_deuda_cuando_la_categoria_es_credito(
    cliente_admin: TestClient, bd
) -> None:
    """La validación del servidor bloquea el guardado sin deuda vinculada."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)

    rechazada = cliente_admin.post(
        "/presupuesto/deducciones",
        data={
            "descripcion": "Libranza",
            "categoria": "Créditos y Obligaciones",
            "valor": "400.000",
            "quincena": "1",
            "id_deuda": "",
        },
    )
    assert rechazada.status_code == 400
    assert MENSAJE_NO in rechazada.text

    aceptada = cliente_admin.post(
        "/presupuesto/deducciones",
        data={
            "descripcion": "Libranza",
            "categoria": "Créditos y Obligaciones",
            "valor": "400.000",
            "quincena": "1",
            "id_deuda": deuda.id_deuda,
        },
        follow_redirects=False,
    )
    assert aceptada.status_code == 303


def test_el_javascript_preserva_el_origen_y_restaura_al_volver() -> None:
    """El script guarda el módulo, marca SI y carga la deuda al regresar."""
    javascript = (RAIZ_APP / "static" / "js" / "categorias.js").read_text(encoding="utf-8")

    assert "deuda-origen:" in javascript
    assert "data-origen-modulo" in javascript
    assert "guardado_deuda" in javascript
    assert "deuda_id" in javascript
    assert "opcionSi.checked = true" in javascript
    assert "data-ir-a-deudas" in javascript
    assert "sessionStorage" in javascript
