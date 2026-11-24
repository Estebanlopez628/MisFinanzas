"""Pruebas de la SRS v4.35: omisión de 10 días, modales, íconos y atajos."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.modelos import Gasto
from app.servicios import ahorro, gastos, pagos_metas, usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


def _admin(bd):
    """Devuelve el administrador sembrado.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Cuenta administradora.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta


def test_omitir_pago_diez_dias(cliente_admin: TestClient, bd) -> None:
    """El gasto normal y la meta se omiten 10 días (modal unificado)."""
    cuenta = _admin(bd)
    hoy = date.today()
    gasto = gastos.crear_gasto(
        bd, cuenta.id_usuario, "Vivienda", "Arriendo", "800000", hoy, es_fijo=True
    )
    respuesta = cliente_admin.post(f"/api/gastos/{gasto.id_gasto}/omitir")
    assert respuesta.status_code == 200
    assert respuesta.json()["ok"] is True
    bd.refresh(gasto)
    assert gasto.inhabilitado_hasta == hoy + timedelta(days=10)
    assert gasto.pagado is False

    meta = ahorro.crear_proyeccion(
        bd, cuenta.id_usuario, "Créditos y Obligaciones", "Viaje QA v435", "300000",
        tipo_duracion="LIMITADO", meses=3,
    )
    pagos_metas.asegurar_gastos_de_metas(
        bd, cuenta.id_usuario, hoy.year, hoy.month
    )
    gasto_meta = bd.query(Gasto).filter(Gasto.id_proyeccion == meta.id_proyeccion).first()
    # SRS v4.37: el modal unificado también permite omitir metas 10 días.
    assert pagos_metas.omitir_pago(
        bd, cuenta.id_usuario, gasto_meta.id_gasto, hoy
    ) is not None


def test_modal_omitir_y_editar_gasto() -> None:
    """El modal de la X existe y Editar gasto lleva Cancelar a ancho completo."""
    base = (RUTA / "templates/base.html").read_text(encoding="utf-8")
    fila = (RUTA / "templates/finanzas/_gasto_fijo.html").read_text(encoding="utf-8")

    assert 'id="modal-omitir-gasto"' in base
    assert "cuéntanos qué deseas hacer con este gasto fijo" in base
    assert "Omitir pago (10 dias)" in base and "Eliminar Gasto" in base
    assert "data-omitir-confirmar" in base and "data-eliminar-confirmar" in base
    assert "data-omitir-cancelar" in base
    assert "data-omitir-gasto" in fila
    assert "acciones-formulario--grilla" in fila
    assert "boton--ancho-completo" in fila
    assert "gasto.id_proyeccion" in fila


def test_modales_opacos_y_capas() -> None:
    """Los modales usan fondo sólido y la jerarquía de z-index se conserva."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    app_modal = css.split(".app-modal {", 1)[1].split("}", 1)[0]
    assert "background: rgba(15, 23, 42, 0.45)" in app_modal
    assert "backdrop-filter: blur(6px)" in app_modal
    assert css.count("backdrop-filter: blur(6px)") >= 3
    controles = css.split(".edicion-gasto__formulario .campo__control {", 1)[1].split("}", 1)[0]
    assert "box-sizing: border-box" in controles
    assert "max-width: 100%" in controles


def test_iconos_subnav() -> None:
    """SRS v4.37: las pestañas van limpias y el ícono vive en el título grande."""
    html = (RUTA / "templates/finanzas/_subnav.html").read_text(encoding="utf-8")
    assert "subnav-finanzas__icono" not in html
    for nombre in ("presupuesto/index.html", "chancucos/index.html", "historial/index.html"):
        vista = (RUTA / "templates" / nombre).read_text(encoding="utf-8")
        assert 'heroe__titulo-icono' in vista
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert ".heroe__titulo-icono" in css


def test_cabeceras_deudas_exactas() -> None:
    """Los encabezados usan los textos y saltos de línea pedidos."""
    html = (RUTA / "templates/deudas/index.html").read_text(encoding="utf-8")
    for texto in (
        ">Total <br /> Adeudado</th>",
        ">No. De <br /> cuotas <br /> pendientes</th>",
        ">Intervalo <br /> De pago</th>",
        ">Vinculación</th>",
        ">Estado</th>",
    ):
        assert texto in html


def test_atajos_dia_plano_y_vista_movil() -> None:
    """El día no lleva óvalo y la vista inicial móvil muestra tres datos."""
    html = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert "atajo-dia-texto" in html
    assert "Pagar los :" in html
    assert "dias_pago_plural" in html
    dias = (RUTA / "templates/chancucos/_dias.html").read_text(encoding="utf-8")
    assert "días {{ item.dia_pago_1 }}" in dias
    assert "Valor a pagar:" in html
    dia = css.split(".atajo-dia-texto {", 1)[1].split("}", 1)[0]
    assert "background: none" in dia and "border: 0" in dia
    movil = css.split("@media (max-width: 640px) {")[-1]
    assert ".atajo-movil-fecha" in css
