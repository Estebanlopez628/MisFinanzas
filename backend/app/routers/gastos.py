"""Rutas del presupuesto de gastos.

Responsabilidad
---------------
Registrar gastos fijos y variables, listarlos, mostrar el total del mes y
eliminarlos. El módulo complementa la nómina: el saldo del bolsillo menos los
gastos es el dinero realmente disponible.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, gastos

router = APIRouter(tags=["Gastos"])


def _parsear_fecha(texto: str) -> date:
    """Convierte la fecha del formulario o devuelve la de hoy.

    Args:
        texto: Valor ``AAAA-MM-DD``; puede venir vacío.

    Returns:
        Fecha válida.

    Raises:
        ValueError: Si el texto no es una fecha ISO.
    """
    if not texto.strip():
        return date.today()
    return date.fromisoformat(texto.strip())


@router.get("/gastos", response_class=HTMLResponse, name="ver_gastos")
def ver_gastos(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra el presupuesto y el formulario de gastos.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.

    Returns:
        HTML del módulo.
    """
    hoy = date.today()
    lista = gastos.listar_gastos(bd, usuario.id_usuario)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Gastos",
            "gastos": lista,
            "resumen": gastos.resumen_por_categoria(bd, usuario.id_usuario),
            "total_mes": gastos.total_gastos_mes(bd, usuario.id_usuario, hoy.year, hoy.month),
            "fecha_hoy": hoy.isoformat(),
            "guardado": bool(guardado),
            "seccion": "gastos",
        }
    )
    return plantillas.TemplateResponse(request, "gastos/index.html", contexto)


@router.post("/gastos", name="crear_gasto", response_model=None)
def crear_gasto(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    categoria: Annotated[str, Form()] = "",
    descripcion: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
    fecha: Annotated[str, Form()] = "",
    es_fijo: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "",
    origen: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra un gasto.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        categoria: Categoría del gasto.
        descripcion: Detalle.
        valor: Monto.
        fecha: Fecha ISO; si falta se usa hoy.
        es_fijo: ``1`` si es recurrente.
        quincena: ``1`` o ``2`` para gastos fijos de una quincena.
        origen: ``finanzas`` cuando el formulario vive en "Mis Finanzas"; en ese
            caso se vuelve al panel de quincenas tras guardar.

    Returns:
        Redirección al listado o a Mis Finanzas, o la vista con el error.
    """
    try:
        gasto = gastos.crear_gasto(
            bd,
            usuario.id_usuario,
            categoria,
            descripcion,
            valor,
            _parsear_fecha(fecha),
            es_fijo=es_fijo == "1",
            quincena=quincena,
        )
        auditoria.registrar(
            bd, usuario.id_usuario, "GASTO_CREADO", "gastos", gasto.descripcion
        )
    except (ValueError, ArithmeticError) as error:
        if origen == "finanzas":
            return RedirectResponse(
                url=f"/finanzas?error_gasto={quote(str(error))}#quincenas",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        hoy = date.today()
        contexto = contexto_base(usuario)
        contexto.update(
            {
                "titulo_pagina": "Gastos",
                "gastos": gastos.listar_gastos(bd, usuario.id_usuario),
                "resumen": gastos.resumen_por_categoria(bd, usuario.id_usuario),
                "total_mes": gastos.total_gastos_mes(
                    bd, usuario.id_usuario, hoy.year, hoy.month
                ),
                "fecha_hoy": hoy.isoformat(),
                "guardado": False,
                "seccion": "gastos",
                "error": str(error),
            }
        )
        return plantillas.TemplateResponse(
            request, "gastos/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    if origen == "finanzas":
        return RedirectResponse(
            url="/finanzas?guardado_gasto=1#quincenas",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(url="/gastos?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/gastos/{id_gasto}/editar", name="editar_gasto", response_model=None)
def editar_gasto(
    request: Request,
    id_gasto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    descripcion: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
    categoria: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "",
    origen: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Actualiza el valor o la descripción de un gasto ya registrado.

    La SRS v1.3 exige poder corregir un gasto fijo sin eliminarlo, porque los
    recibos de servicios cambian mes a mes y el saldo de la quincena debe
    recalcularse con el monto nuevo.

    Args:
        request: Petición HTTP.
        id_gasto: Identificador del gasto a modificar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        descripcion: Nuevo detalle legible.
        valor: Nuevo monto en pesos.
        categoria: Categoría nueva; si llega vacía se conserva la actual.
        quincena: `1` o `2` para la quincena del gasto; vacío para el mes completo.
        origen: ``finanzas`` cuando el formulario vive en "Mis Finanzas"; en ese
            caso se vuelve al panel de quincenas tras guardar.

    Returns:
        Redirección al listado o a Mis Finanzas, o la vista con el error.
    """
    try:
        gasto = gastos.actualizar_gasto(
            bd,
            usuario.id_usuario,
            id_gasto,
            descripcion,
            valor,
            categoria=categoria or None,
            quincena=quincena,
        )
    except (ValueError, ArithmeticError) as error:
        if origen == "finanzas":
            return RedirectResponse(
                url=f"/finanzas?error_gasto={quote(str(error))}#quincenas",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        hoy = date.today()
        contexto = contexto_base(usuario)
        contexto.update(
            {
                "titulo_pagina": "Gastos",
                "gastos": gastos.listar_gastos(bd, usuario.id_usuario),
                "resumen": gastos.resumen_por_categoria(bd, usuario.id_usuario),
                "total_mes": gastos.total_gastos_mes(
                    bd, usuario.id_usuario, hoy.year, hoy.month
                ),
                "fecha_hoy": hoy.isoformat(),
                "guardado": False,
                "seccion": "gastos",
                "error": str(error),
            }
        )
        return plantillas.TemplateResponse(
            request, "gastos/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    if gasto is None:
        # El gasto no existe o pertenece a otro usuario: se responde igual que
        # un listado vacío para no revelar información ajena.
        if origen == "finanzas":
            return RedirectResponse(
                url="/finanzas?error_gasto=El%20gasto%20no%20existe.#quincenas",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(url="/gastos", status_code=status.HTTP_303_SEE_OTHER)

    auditoria.registrar(
        bd, usuario.id_usuario, "GASTO_ACTUALIZADO", "gastos", gasto.descripcion
    )

    if origen == "finanzas":
        return RedirectResponse(
            url="/finanzas?guardado_gasto=1#quincenas",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(url="/gastos?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/gastos/{id_gasto}/eliminar", name="eliminar_gasto")
def eliminar_gasto(
    id_gasto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Elimina un gasto del usuario.

    Args:
        id_gasto: Identificador del gasto.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        origen: ``finanzas`` cuando la acción se lanza desde el panel de
            quincenas; en ese caso se vuelve allí.

    Returns:
        Redirección al listado correspondiente.
    """
    if gastos.eliminar_gasto(bd, usuario.id_usuario, id_gasto):
        auditoria.registrar(bd, usuario.id_usuario, "GASTO_ELIMINADO", "gastos", id_gasto)
    if origen == "finanzas":
        return RedirectResponse(
            url="/finanzas#quincenas", status_code=status.HTTP_303_SEE_OTHER
        )
    return RedirectResponse(url="/gastos", status_code=status.HTTP_303_SEE_OTHER)
