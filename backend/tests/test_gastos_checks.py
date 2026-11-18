"""Pruebas de los checks de gastos fijos y sus acciones (SRS v1.7, bloque C).

Cubren el desmarcado individual —que revierte el pago y su abono—, el render
del ✔ solo cuando el check está visible, la limpieza masiva sin residuos y la
presencia del lápiz de edición y del botón «Cancelar».
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.modelos import AbonoProyeccion, Gasto
from app.servicios import ahorro, deducciones_fijas, gastos, pagos_metas, usuarios

HOY = date.today()


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


def _meta_con_gasto(bd, id_usuario: str):
    """Crea una meta con su gasto del mes en curso y lo devuelve.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta.

    Returns:
        Tupla `(proyeccion, gasto)` del mes en curso.
    """
    proyeccion = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Fondo de emergencia",
        "100.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses=12,
        fecha_inicio=HOY,
        quincena=1,
    )
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, HOY.year, HOY.month)
    gasto = bd.scalar(select(Gasto).where(Gasto.id_proyeccion == proyeccion.id_proyeccion))
    assert gasto is not None
    return proyeccion, gasto


def _abono(bd, id_proyeccion: str) -> Decimal | None:
    """Devuelve el abono del mes en curso de una meta.

    Args:
        bd: Sesión de base de datos.
        id_proyeccion: Meta consultada.

    Returns:
        Monto abonado o `None` si no hay abono.
    """
    abono = bd.scalar(
        select(AbonoProyeccion).where(
            AbonoProyeccion.id_proyeccion == id_proyeccion,
            AbonoProyeccion.anio == HOY.year,
            AbonoProyeccion.mes == HOY.month,
        )
    )
    return abono.valor if abono is not None else None


# ---------------------------------------------------------------------------
# Servicio: desmarcar
# ---------------------------------------------------------------------------


def test_desmarcar_revierte_el_pago_y_retira_el_abono(bd) -> None:
    """Quitar el ✔ devuelve el gasto a pendiente y elimina su abono."""
    id_usuario = _id_admin(bd)
    proyeccion, gasto = _meta_con_gasto(bd, id_usuario)
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)
    assert _abono(bd, proyeccion.id_proyeccion) == Decimal("100000.00")

    actualizado = pagos_metas.desmarcar_pagado(bd, id_usuario, gasto.id_gasto)

    assert actualizado is not None
    assert actualizado.pagado is False
    assert actualizado.pagado_en is None
    assert actualizado.monto_pagado is None
    assert actualizado.check_visible is True
    assert _abono(bd, proyeccion.id_proyeccion) is None


def test_desmarcar_vuelve_a_restar_en_la_quincena(bd) -> None:
    """El gasto desmarcado cuenta de nuevo en el saldo de su quincena."""
    id_usuario = _id_admin(bd)
    _, gasto = _meta_con_gasto(bd, id_usuario)
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)
    # Con el pago marcado, el gasto cuenta por su monto pagado (100.000).
    pagos_metas.desmarcar_pagado(bd, id_usuario, gasto.id_gasto)
    bd.refresh(gasto)

    assert gastos.valor_computable(gasto) == Decimal("100000.00")


def test_desmarcar_gasto_ajeno_no_hace_nada(bd) -> None:
    """El servicio ignora un gasto de otro usuario."""
    id_admin = _id_admin(bd)
    _, gasto = _meta_con_gasto(bd, id_admin)
    pagos_metas.marcar_pagado(bd, id_admin, gasto.id_gasto, HOY)

    resultado = pagos_metas.desmarcar_pagado(bd, "usuario-ajeno", gasto.id_gasto)

    assert resultado is None
    bd.refresh(gasto)
    assert gasto.pagado is True


# ---------------------------------------------------------------------------
# Camino HTTP
# ---------------------------------------------------------------------------


def test_http_desmarcar_devuelve_al_panel(cliente_admin, bd) -> None:
    """La ruta del ✔ invertido responde 303 y regresa a las quincenas."""
    id_usuario = _id_admin(bd)
    _, gasto = _meta_con_gasto(bd, id_usuario)
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    respuesta = cliente_admin.post(
        f"/gastos/{gasto.id_gasto}/no-pagado",
        data={"origen": "finanzas"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/finanzas#quincenas"
    bd.refresh(gasto)
    assert gasto.pagado is False


def test_http_desmarcar_ajeno_no_cambia_el_pago(cliente_usuario, bd) -> None:
    """Un usuario público no puede desmarcar el pago de la cuenta administradora."""
    id_admin = _id_admin(bd)
    _, gasto = _meta_con_gasto(bd, id_admin)
    pagos_metas.marcar_pagado(bd, id_admin, gasto.id_gasto, HOY)

    respuesta = cliente_usuario.post(
        f"/gastos/{gasto.id_gasto}/no-pagado",
        data={"origen": "finanzas"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    bd.refresh(gasto)
    assert gasto.pagado is True


def test_panel_pinta_el_check_marcado_y_permite_desmarcar(cliente_admin, bd) -> None:
    """Con el pago visible, el ✔ es un botón que apunta a `no-pagado`."""
    id_usuario = _id_admin(bd)
    _, gasto = _meta_con_gasto(bd, id_usuario)
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    html = cliente_admin.get("/finanzas").text

    assert "boton-circular--marcado" in html
    assert f"/gastos/{gasto.id_gasto}/no-pagado" in html
    assert "pulsa para desmarcar" in html


def test_limpiar_checks_no_deja_el_check_en_el_panel(cliente_admin, bd) -> None:
    """Tras limpiar, el ✔ desaparece del panel aunque el pago se conserve."""
    id_usuario = _id_admin(bd)
    proyeccion, gasto = _meta_con_gasto(bd, id_usuario)
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)
    pagos_metas.limpiar_checks(bd, id_usuario, HOY.year, HOY.month, 1)

    html = cliente_admin.get("/finanzas").text

    assert "boton-circular--marcado" not in html
    assert "boton-circular--check" in html
    # El pago sigue registrado y su abono se conserva.
    assert _abono(bd, proyeccion.id_proyeccion) == Decimal("100000.00")


def test_panel_ofrece_lapiz_cancelar_y_limpieza_visible(cliente_admin, bd) -> None:
    """La fila usa lápiz, «Cancelar» y un botón de limpieza con más contraste."""
    id_usuario = _id_admin(bd)
    _, gasto = _meta_con_gasto(bd, id_usuario)
    pagos_metas.marcar_pagado(bd, id_usuario, gasto.id_gasto, HOY)

    html = cliente_admin.get("/finanzas").text

    assert "boton-circular--editar" in html
    assert "data-cancelar-edicion" in html
    assert "boton--cancelar" in html
    assert "boton--advertencia" in html
    assert "data-confirmar=" in html


def test_presupuesto_hereda_lapiz_y_cancelar(cliente_admin, bd) -> None:
    """Las deducciones fijas usan el mismo componente de edición (DRY)."""
    id_usuario = _id_admin(bd)
    deducciones_fijas.crear_deduccion(bd, id_usuario, "Préstamo", "150.000", 1)

    html = cliente_admin.get("/presupuesto").text

    assert "boton-circular--editar" in html
    assert "data-cancelar-edicion" in html
    assert "boton--cancelar" in html
