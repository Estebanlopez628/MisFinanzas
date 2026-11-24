"""Pruebas de la SRS v4.41: paridad de acciones en Trabajos Extras."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.servicios import gastos, pagos_metas, trabajos, usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_trabajos_usa_la_misma_fila_de_gastos() -> None:
    """La lista de gastos fijos del trabajo usa `fila_gasto`, no una filaSimple."""
    vista = (RUTA / "templates/trabajos/index.html").read_text(encoding="utf-8")
    assert "{{ fila_gasto(gasto, hoy, 'trabajos', trabajo.id_trabajo) }}" in vista
    assert "Limpiar checks de este trabajo" in vista
    assert 'name="id_trabajo"' in vista
    # Ya no queda la fila hecha a mano con solo eliminar.
    assert "class=\"lista-gastos__item\">" not in vista


def test_limpiar_checks_solo_afecta_al_trabajo(bd) -> None:
    """El filtro por contrato no toca los checks de Mis Finanzas."""
    hoy = date.today()
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    trabajo = trabajos.crear_trabajo(
        bd, cuenta.id_usuario, "Trabajo QA v441", "1000000", hoy
    )
    gasto_trabajo = trabajos.crear_gasto_trabajo(
        bd, cuenta.id_usuario, trabajo.id_trabajo, "Vivienda", "Gasto trabajo QA",
        "120000",
    )
    gasto_finanzas = gastos.crear_gasto(
        bd, cuenta.id_usuario, "Vivienda", "Gasto finanzas QA", "150000", hoy,
        es_fijo=True,
    )
    pagos_metas.marcar_pagado(bd, cuenta.id_usuario, gasto_trabajo.id_gasto, hoy)
    pagos_metas.marcar_pagado(bd, cuenta.id_usuario, gasto_finanzas.id_gasto, hoy)

    limpiados = pagos_metas.limpiar_checks(
        bd, cuenta.id_usuario, hoy.year, hoy.month, 0,
        id_trabajo=trabajo.id_trabajo,
    )
    assert limpiados == 1
    bd.refresh(gasto_trabajo)
    bd.refresh(gasto_finanzas)
    assert gasto_trabajo.check_visible is False
    assert gasto_finanzas.check_visible is True
