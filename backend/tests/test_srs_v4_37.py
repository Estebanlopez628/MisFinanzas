"""Pruebas de la SRS v4.37: modal unificado, Habilitar, modal sólido e íconos."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import ahorro, gastos, pagos_metas, usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_x_unificada_con_meta_bloqueada() -> None:
    """La X abre el modal también en metas, con Eliminar bloqueado."""
    fila = (RUTA / "templates/finanzas/_gasto_fijo.html").read_text(encoding="utf-8")
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    base = (RUTA / "templates/base.html").read_text(encoding="utf-8")

    assert 'data-es-meta=' in fila
    assert "data-omitir-gasto" in fila
    assert (
        "No puedes eliminar una meta desde gastos fijos, debes hacerlo en el módulo de registro de metas."
        in js
    )
    assert 'id="modal-omitir-gasto"' in base


def test_habilitar_reactiva(cliente_admin: TestClient, bd) -> None:
    """El endpoint Habilitar limpia la omisión y devuelve el gasto al plan."""
    hoy = date.today()
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    gasto = gastos.crear_gasto(
        bd, cuenta.id_usuario, "Vivienda", "Arriendo", "800000", hoy, es_fijo=True
    )
    pagos_metas.omitir_pago(bd, cuenta.id_usuario, gasto.id_gasto, hoy)

    respuesta = cliente_admin.post(f"/api/gastos/{gasto.id_gasto}/habilitar")
    assert respuesta.status_code == 200
    assert respuesta.json()["ok"] is True
    bd.refresh(gasto)
    assert gasto.inhabilitado_hasta is None
    assert gasto.check_visible is True


def test_editar_gasto_solido_y_al_frente() -> None:
    """El modal Editar gasto tiene fondo sólido y z-index superior."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    indice = css.index("details.edicion-gasto--modal[open] > .edicion-gasto__formulario")
    bloque = css[indice : css.index("}", indice)]
    assert "background: var(--bg-card)" in bloque
    assert "z-index: 9002" in bloque
    centrado = css.split(".modal-centrado > * {", 1)[1].split("}", 1)[0]
    assert "background: var(--bg-card)" in centrado
    assert "z-index: 9002" in centrado


def test_iconos_en_titulo_no_en_subnav() -> None:
    """Las pestañas están limpias y cada vista muestra su ícono grande."""
    subnav = (RUTA / "templates/finanzas/_subnav.html").read_text(encoding="utf-8")
    assert "subnav-finanzas__icono" not in subnav
    for nombre in (
        "finanzas/index.html", "presupuesto/index.html",
        "chancucos/index.html", "historial/index.html",
    ):
        vista = (RUTA / "templates" / nombre).read_text(encoding="utf-8")
        assert "heroe__titulo-icono" in vista or "💰" in vista
