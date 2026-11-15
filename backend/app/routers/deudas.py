"""Rutas del módulo "Resumen de Deudas".

Responsabilidad
---------------
Registrar pasivos, aplicar abonos y mostrar los totales de cartera. Es un módulo
de acceso general: cada usuario ve únicamente sus propias deudas (SRS v1.2).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, deudas

router = APIRouter(tags=["Deudas"])


def _contexto(
    usuario: UsuarioSesion,
    bd: Session,
    *,
    error: str | None = None,
    guardado: bool = False,
) -> dict[str, object]:
    """Prepara el contexto de la vista de deudas.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error opcional.
        guardado: Bandera de éxito.

    Returns:
        Diccionario para la plantilla.
    """
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Resumen de Deudas",
            "deudas": deudas.listar_deudas(bd, usuario.id_usuario),
            "resumen": deudas.resumen_deudas(bd, usuario.id_usuario),
            "error": error,
            "guardado": guardado,
        }
    )
    return contexto


@router.get("/deudas", response_class=HTMLResponse, name="ver_deudas")
def ver_deudas(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra las deudas y sus totales.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.

    Returns:
        HTML del módulo.
    """
    return plantillas.TemplateResponse(
        request, "deudas/index.html", _contexto(usuario, bd, guardado=bool(guardado))
    )


@router.post("/deudas", name="crear_deuda", response_model=None)
def crear_deuda(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    acreedor: Annotated[str, Form()] = "",
    descripcion: Annotated[str, Form()] = "",
    saldo_total: Annotated[str, Form()] = "",
    cuota_mensual: Annotated[str, Form()] = "",
    tasa_interes: Annotated[str, Form()] = "",
    fecha_limite: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra una deuda.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        acreedor: Acreedor.
        descripcion: Detalle.
        saldo_total: Saldo inicial.
        cuota_mensual: Cuota pactada.
        tasa_interes: Tasa porcentual.
        fecha_limite: Fecha límite ISO.

    Returns:
        Redirección o vista con error.
    """
    limite = None
    if fecha_limite.strip():
        try:
            limite = date.fromisoformat(fecha_limite.strip())
        except ValueError:
            return plantillas.TemplateResponse(
                request,
                "deudas/index.html",
                _contexto(usuario, bd, error="La fecha límite no tiene un formato válido."),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    try:
        deuda = deudas.crear_deuda(
            bd,
            usuario.id_usuario,
            acreedor,
            saldo_total,
            descripcion or None,
            cuota_mensual or None,
            tasa_interes or None,
            limite,
        )
        auditoria.registrar(bd, usuario.id_usuario, "DEUDA_CREADA", "deudas", deuda.acreedor)
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "deudas/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/deudas?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/deudas/{id_deuda}/abonar", name="abonar_deuda", response_model=None)
def abonar_deuda(
    request: Request,
    id_deuda: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    monto: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Aplica un abono al saldo de una deuda.

    Args:
        request: Petición HTTP.
        id_deuda: Deuda abonada.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        monto: Dinero abonado.

    Returns:
        Redirección o vista con error.
    """
    try:
        deudas.abonar_deuda(bd, usuario.id_usuario, id_deuda, monto)
        auditoria.registrar(bd, usuario.id_usuario, "DEUDA_ABONADA", "deudas", id_deuda)
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "deudas/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/deudas", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/deudas/{id_deuda}/eliminar", name="eliminar_deuda")
def eliminar_deuda(
    id_deuda: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina una deuda.

    Args:
        id_deuda: Deuda a eliminar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al listado.
    """
    if deudas.eliminar_deuda(bd, usuario.id_usuario, id_deuda):
        auditoria.registrar(bd, usuario.id_usuario, "DEUDA_ELIMINADA", "deudas", id_deuda)
    return RedirectResponse(url="/deudas", status_code=status.HTTP_303_SEE_OTHER)
