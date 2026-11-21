"""Pruebas del selector cerrado y la dona por categorías (SRS v1.9, Paso 2).

Verifican que los formularios de Mis Finanzas, Gastos, Trabajos Extras y
Deducciones Fijas usen el catálogo de ocho opciones, que la vinculación con
deudas llegue al backend y que la dona se pinte con los colores del catálogo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import categorias as catalogo
from app.servicios import deudas, gastos, trabajos, usuarios

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"


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


@pytest.mark.parametrize("ruta", ["/finanzas", "/gastos", "/trabajos-extras"])
def test_los_formularios_de_gastos_ofrecen_el_catalogo_cerrado(
    cliente_admin: TestClient, bd, ruta: str
) -> None:
    """Los tres formularios muestran las ocho categorías con sus colores exactos."""
    if ruta == "/trabajos-extras":
        # El formulario vive dentro de cada periodo de pago del contrato.
        trabajo = trabajos.crear_trabajo(
            bd, _id_admin(bd), "Diseño", "600.000", date.today()
        )
        trabajos.asegurar_pagos_trabajos(bd, _id_admin(bd), date.today().year, date.today().month)
        assert trabajo is not None
    html = cliente_admin.get(ruta).text

    assert "data-selector-categoria" in html
    assert 'name="categoria"' in html
    assert "readonly" in html
    for categoria in catalogo.CATEGORIAS:
        assert f'data-categoria-opcion="{categoria.nombre}"' in html
        assert categoria.color in html
    assert html.count("data-categoria-opcion=") >= 8


def test_el_formulario_de_deducciones_tiene_categoria_y_vinculo(
    cliente_admin: TestClient,
) -> None:
    """Deducciones Fijas captura categoría cerrada y puede vincular una deuda."""
    html = cliente_admin.get("/presupuesto").text

    assert "data-selector-categoria" in html
    assert 'data-guardar-formulario="crear-deduccion-fija"' in html
    assert "data-vinculo-condicional" in html
    assert 'name="id_deuda"' in html


def test_deducciones_tiene_fila_superior_de_tres_campos_y_quincena_abajo(
    cliente_admin: TestClient,
) -> None:
    """El formulario sigue el orden Concepto | Categoría | Valor y luego Quincena."""
    html = cliente_admin.get("/presupuesto").text

    assert 'class="fila-campos fila-campos--deducciones"' in html
    assert "Concepto" in html
    assert "Categoría" in html
    assert "Valor Descontado (COP)" in html
    assert "Valor por pago (COP)" not in html
    assert "Quincena donde aplican los pagos" in html
    # La etiqueta antigua solo queda en el formulario de metas.
    assert html.count("Quincena donde aplicaremos los pagos") == 1
    assert html.index("Valor Descontado (COP)") < html.index("Quincena donde aplican los pagos")

    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    assert ".fila-campos--deducciones {" in css
    assert "repeat(3, minmax(0, 1fr))" in css
    assert ".deduccion-quincena {" in css


def test_la_edicion_de_un_gasto_incluye_categoria_y_vinculo(
    cliente_admin: TestClient, bd
) -> None:
    """El lápiz de Mis Finanzas permite corregir categoría y deuda vinculada."""
    gasto = gastos.crear_gasto(
        bd,
        _id_admin(bd),
        "Vivienda",
        "Arriendo",
        "900.000",
        date.today(),
        es_fijo=True,
    )

    html = cliente_admin.get("/finanzas").text

    assert "data-selector-categoria" in html
    assert f'data-guardar-formulario="editar-gasto-{gasto.id_gasto}"' in html
    assert f'value="{gasto.categoria}"' in html
    assert "data-vincular-deuda" in html


def test_el_alta_de_gastos_vincula_la_deuda_desde_el_formulario(
    cliente_admin: TestClient, bd
) -> None:
    """El campo `id_deuda` enviado por el selector llega al gasto persistido."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1200000", "400000", 3)

    respuesta = cliente_admin.post(
        "/gastos",
        data={
            "categoria": "Vivienda y Servicios",
            "descripcion": "Cuota del banco",
            "valor": "999999",
            "es_fijo": "1",
            "quincena": "1",
            "id_deuda": deuda.id_deuda,
            "origen": "finanzas",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    creado = next(g for g in gastos.listar_gastos(bd, id_usuario) if g.descripcion == "Cuota del banco")
    assert creado.id_deuda == deuda.id_deuda
    assert creado.valor == Decimal("400000.00")
    assert creado.categoria == "Créditos y Obligaciones"


def test_la_dona_muestra_las_ocho_categorias_y_la_obligacion_automatica(
    cliente_admin: TestClient,
) -> None:
    """La leyenda de la dona trae las ocho categorías y marca la número 8."""
    html = cliente_admin.get("/presupuesto").text

    for categoria in catalogo.CATEGORIAS:
        assert f'data-leyenda-categoria="{categoria.nombre}"' in html
        assert categoria.color in html
    assert "automática · deudas" in html
    assert 'data-etiqueta="Otros Gastos Fijos"' in html


def test_el_js_y_el_service_worker_incluyen_el_selector_y_la_preservacion() -> None:
    """El script global y la caché PWA incluyen el nuevo componente."""
    javascript = (RAIZ_APP / "static" / "js" / "categorias.js").read_text(encoding="utf-8")
    base = (RAIZ_APP / "templates" / "base.html").read_text(encoding="utf-8")
    service_worker = (RAIZ_APP / "static" / "js" / "sw.js").read_text(encoding="utf-8")

    assert "data-categoria-opcion" in javascript
    assert "sessionStorage" in javascript
    assert "data-vincular-deuda" in javascript
    assert "js/categorias.js" in base
    assert "js/categorias.js" in service_worker
