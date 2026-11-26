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


@pytest.mark.parametrize("ruta", ["/finanzas", "/gastos"])
def test_gastos_fijos_usan_select_nativo_con_punto(
    cliente_admin: TestClient, bd, ruta: str
) -> None:
    """Los formularios de gastos fijos usan el mismo <select> con punto."""
    html = cliente_admin.get(ruta).text

    assert 'name="categoria"' in html
    assert "data-categoria-entrada" in html
    for categoria in catalogo.CATEGORIAS:
        assert f'value="{categoria.nombre}"' in html
        assert f">• {categoria.nombre}</option>" in html
        # El selector ya no pinta el cuadrito de color: usa un punto neutro.
        assert categoria.color not in html


@pytest.mark.parametrize("ruta", ["/presupuesto", "/trabajos-extras"])
def test_deducciones_y_trabajos_usan_select_nativo_con_punto(
    cliente_admin: TestClient, bd, ruta: str
) -> None:
    """Deducciones y Trabajos Extras usan un <select> con punto y valor limpio."""
    if ruta == "/trabajos-extras":
        trabajos.crear_trabajo(bd, _id_admin(bd), "Diseño", "600.000", date.today())
        trabajos.asegurar_pagos_trabajos(bd, _id_admin(bd), date.today().year, date.today().month)
    html = cliente_admin.get(ruta).text

    assert 'name="categoria"' in html
    assert "data-categoria-entrada" in html
    for categoria in catalogo.CATEGORIAS:
        assert f'value="{categoria.nombre}"' in html
        assert f">• {categoria.nombre}</option>" in html
        assert f'value="• {categoria.nombre}"' not in html


def test_el_formulario_de_deducciones_tiene_categoria_y_vinculo(
    cliente_admin: TestClient,
) -> None:
    """Deducciones Fijas captura categoría cerrada y puede vincular una deuda."""
    html = cliente_admin.get("/presupuesto").text

    assert "data-categoria-entrada" in html
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

    assert "data-categoria-entrada" in html
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


def test_la_leyenda_de_la_dona_solo_muestra_categorias_con_valor(
    cliente_admin: TestClient, bd
) -> None:
    """Las categorías en cero no se pintan en la leyenda de la dona."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    from app.servicios import capacidad, perfiles

    perfil = perfiles.obtener_perfil(bd, cuenta.id_usuario)
    hoy = date.today()
    resultado = capacidad.capacidad_endeudamiento(
        bd, cuenta.id_usuario, perfil, hoy.year, hoy.month
    )

    html = cliente_admin.get("/presupuesto").text

    for categoria in resultado.categorias:
        etiqueta = f'data-leyenda-etiqueta="{categoria["nombre"]}"'
        if categoria["valor"] > 0:
            assert etiqueta in html
        else:
            assert etiqueta not in html
    assert 'data-etiqueta="Otros Gastos Fijos"' in html
    # No hay una segunda leyenda duplicada ni la insignia «automática · deudas».
    assert "data-leyenda-categoria=" not in html
    assert "automática · deudas" not in html
    assert html.count('data-leyenda-etiqueta="Otros Gastos Fijos"') == 1


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
