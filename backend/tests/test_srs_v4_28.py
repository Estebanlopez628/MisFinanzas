"""Pruebas de la SRS v4.28: textos y paridad de la comparativa."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.modelos import AbonoProyeccion, Gasto, ProyeccionAhorro
from app.servicios import ahorro, consejero, pagos_metas, usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_textos_y_branding(cliente_admin: TestClient) -> None:
    """Rol técnico, cifrado y marca antigua desaparecen de la UI."""
    base = (RUTA / "templates/base.html").read_text(encoding="utf-8")
    perfil = (RUTA / "templates/perfil/index.html").read_text(encoding="utf-8")
    finanzas = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    ayuda = cliente_admin.get("/ayuda").text

    assert "usuario.rol" not in base
    assert "PBKDF2" not in perfil and "SHA256" not in perfil
    assert "Ver todos los gastos fijos" not in finanzas
    assert "Mis Finanzas" in ayuda
    assert "MisFinanzas" not in ayuda


def test_consejo_ahorro_entrega_el_componente(bd) -> None:
    """Sin deudas, el consejo devuelve el bloque de cierre con barras vacías."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    resultado = consejero.consejo_financiero(bd, cuenta.id_usuario, "Ana", Decimal("900000"))

    assert resultado.activo is True
    assert resultado.cierre["barras_deuda"] == []
    assert resultado.cierre["resumen_barras"]["max_base"] == 1


def test_abonos_meta_se_acumulan(cliente_admin: TestClient, bd) -> None:
    """Varios abonos en el mismo mes suman al acumulado y al check."""
    from datetime import date

    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    meta = ahorro.crear_proyeccion(
        bd, cuenta.id_usuario, "Créditos y Obligaciones", "Viaje", "300000",
        tipo_duracion="LIMITADO", meses=3,
    )
    from datetime import date

    pagos_metas.asegurar_gastos_de_metas(
        bd, cuenta.id_usuario, date.today().year, date.today().month
    )
    gasto = bd.scalars(
        select(Gasto).where(
            Gasto.id_proyeccion == meta.id_proyeccion, Gasto.id_usuario == cuenta.id_usuario
        )
    ).first()
    assert gasto is not None

    respuesta = cliente_admin.post(
        f"/api/gastos/{gasto.id_gasto}/abono-meta", data={"valor": "40000"}
    )
    assert respuesta.status_code == 200
    respuesta2 = cliente_admin.post(
        f"/api/gastos/{gasto.id_gasto}/abono-meta", data={"valor": "80000"}
    )
    assert respuesta2.status_code == 200

    abono = bd.scalars(
        select(AbonoProyeccion).where(AbonoProyeccion.id_proyeccion == meta.id_proyeccion)
    ).one()
    assert abono.valor == Decimal("120000.00")
    bd.refresh(gasto)
    assert gasto.monto_pagado == Decimal("120000.00")
    assert gasto.pagado is True


def test_layout_y_capas_de_modales() -> None:
    """La grilla de deudas en web y la jerarquía de capas están definidas."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    web = css.split("@media (min-width: 768px) {")[-1]
    assert ".rejilla-paneles--deudas" in web
    assert "flex-direction: column" in web
    assert "margin-inline: auto" in web
    assert ".app-modal {" in css
    bloque = css.split(".app-modal {", 1)[1].split("}", 1)[0]
    assert "z-index: 9999" in bloque
    assert "z-index: 9000" in css


def test_confirmacion_olb_esta_en_el_boton() -> None:
    """La anulación confirma al pulsar, no al enviar el formulario."""
    html = (RUTA / "templates/olb_byte/index.html").read_text(encoding="utf-8")
    inicio = html.index("Confirmar anulación")
    bloque = html[max(0, inicio - 500) : inicio + 60]
    assert "data-confirmar" in bloque
    assert "Confirmar anulación" in bloque


def test_vista_sin_deudas_no_muestra_grafica_vieja(cliente_admin: TestClient, bd) -> None:
    """El perfil sin deudas ve el componente nuevo, no la comparativa antigua."""
    respuesta = cliente_admin.get("/presupuesto")

    assert respuesta.status_code == 200
    assert "impacto-deudas" in respuesta.text
    assert "impacto-deudas__vacio" in respuesta.text
    assert "Base frente a optimizado" not in respuesta.text
    assert "comparativa__grafica" not in respuesta.text
