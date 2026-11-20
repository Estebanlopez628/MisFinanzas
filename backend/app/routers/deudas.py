"""Rutas del módulo "Resumen de Deudas".

Responsabilidad
---------------
- Registrar pasivos con seis datos: acreedor, descripción, saldo, cuota, cuotas
  pendientes y periodicidad.
- Aplicar automáticamente las cuotas vencidas al abrir el módulo.
- Mostrar el plan de amortización de cada deuda y los totales de cartera.

Es un módulo de acceso general: cada usuario ve únicamente sus propias deudas
(SRS v1.2). La aritmética vive en `app.servicios.deudas`; este router solo valida
entradas, invoca el servicio y presenta resultados.
"""

from __future__ import annotations

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
    aplicadas: int = 0,
    valores: dict[str, str] | None = None,
) -> dict[str, object]:
    """Prepara el contexto de la vista de deudas.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error opcional.
        guardado: Bandera de éxito al registrar una deuda.
        aplicadas: Cuotas descontadas automáticamente en esta visita.
        valores: Datos ya escritos en el formulario, para no perderlos al
            corregir un error.

    Returns:
        Diccionario para la plantilla.
    """
    contexto = contexto_base(usuario)
    lista = deudas.listar_deudas(bd, usuario.id_usuario)
    pagos = deudas.listar_pagos(bd, usuario.id_usuario)
    planes = {
        deuda.id_deuda: deudas.proyeccion_deuda(
            deuda,
            pagos[deuda.id_deuda][-1].fecha_aplicacion
            if pagos.get(deuda.id_deuda)
            else None,
        )
        for deuda in lista
    }
    contexto.update(
        {
            "titulo_pagina": "Resumen de Deudas",
            "deudas": lista,
            "pagos": pagos,
            "planes": planes,
            "resumen": deudas.resumen_deudas(bd, usuario.id_usuario),
            "periodicidades": deudas.PERIODICIDADES,
            "error": error,
            "guardado": guardado,
            "aplicadas": aplicadas,
            "valores": valores or {},
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
    """Muestra las deudas, aplica las cuotas vencidas y lista los planes.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito del registro.

    Returns:
        HTML del módulo.
    """
    aplicadas = deudas.aplicar_cuotas_vencidas(bd, usuario.id_usuario)
    return plantillas.TemplateResponse(
        request,
        "deudas/index.html",
        _contexto(
            usuario,
            bd,
            guardado=bool(guardado),
            aplicadas=aplicadas,
        ),
    )


@router.post("/deudas", name="crear_deuda", response_model=None)
def crear_deuda(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    acreedor: Annotated[str, Form()] = "",
    descripcion: Annotated[str, Form()] = "",
    saldo_total: Annotated[str, Form()] = "",
    cuota: Annotated[str, Form()] = "",
    cuotas_pendientes: Annotated[str, Form()] = "",
    periodicidad: Annotated[str, Form()] = deudas.PERIODICIDAD_MENSUAL,
) -> HTMLResponse | RedirectResponse:
    """Registra una deuda con su plan de pagos.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        acreedor: Acreedor.
        descripcion: Detalle.
        saldo_total: Capital pendiente inicial.
        cuota: Valor de cada pago.
        cuotas_pendientes: Número de pagos que faltan.
        periodicidad: `QUINCENAL` o `MENSUAL`.

    Returns:
        Redirección o vista con error.
    """
    try:
        deuda = deudas.crear_deuda(
            bd,
            usuario.id_usuario,
            acreedor,
            saldo_total,
            cuota,
            cuotas_pendientes,
            periodicidad,
            descripcion or None,
        )
        auditoria.registrar(bd, usuario.id_usuario, "DEUDA_CREADA", "deudas", deuda.acreedor)
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "deudas/index.html",
            _contexto(
                usuario,
                bd,
                error=str(error),
                valores={
                    "acreedor": acreedor,
                    "descripcion": descripcion,
                    "saldo_total": saldo_total,
                    "cuota": cuota,
                    "cuotas_pendientes": cuotas_pendientes,
                    "periodicidad": periodicidad,
                },
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/deudas?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/deudas/{id_deuda}/eliminar", name="eliminar_deuda")
def eliminar_deuda(
    id_deuda: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina una deuda y sus pagos registrados.

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
