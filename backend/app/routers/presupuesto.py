"""Rutas del planificador de ahorro y metas (SRS v1.3, bloque 3).

Responsabilidad
---------------
- Servir la pestaña «Gastos y Presupuesto» con el diagnóstico de liquidez, el
  formulario de proyección y el seguimiento de abonos.
- Crear metas, registrar o corregir el abono de un mes y eliminarlas.

La aritmética vive en `app.servicios.ahorro`; aquí solo se traduce HTTP.
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
from app.servicios import ahorro, auditoria, perfiles

router = APIRouter(tags=["Presupuesto"])


def _fecha_del_formulario(texto: str) -> date:
    """Convierte la fecha de inicio del formulario o devuelve la de hoy.

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


def _contexto(
    usuario: UsuarioSesion,
    bd: Session,
    *,
    guardado: bool = False,
    error: str | None = None,
) -> dict[str, object]:
    """Prepara el contexto de la plantilla de presupuesto.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.
        error: Mensaje de error opcional.

    Returns:
        Diccionario listo para Jinja2.
    """
    hoy = date.today()
    perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Gastos y Presupuesto",
            "seccion": "gastos",
            "diagnostico": ahorro.diagnostico(
                bd, usuario.id_usuario, perfil, hoy.year, hoy.month
            ),
            "metas": ahorro.resumen_metas(bd, usuario.id_usuario),
            "categorias": ahorro.CATEGORIAS_SUGERIDAS,
            "fecha_hoy": hoy.isoformat(),
            "guardado": guardado,
            "error": error or None,
        }
    )
    return contexto


@router.get("/presupuesto", response_class=HTMLResponse, name="ver_presupuesto")
def ver_presupuesto(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
    error: str = "",
) -> HTMLResponse:
    """Muestra el planificador de ahorro.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.
        error: Mensaje de error opcional.

    Returns:
        HTML del planificador.
    """
    contexto = _contexto(usuario, bd, guardado=bool(guardado), error=error or None)
    return plantillas.TemplateResponse(request, "presupuesto/index.html", contexto)


@router.post("/presupuesto/metas", name="crear_proyeccion", response_model=None)
def crear_proyeccion(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    categoria: Annotated[str, Form()] = "",
    descripcion: Annotated[str, Form()] = "",
    valor_mensual: Annotated[str, Form()] = "",
    tipo_duracion: Annotated[str, Form()] = ahorro.DURACION_FIJA,
    meses: Annotated[str, Form()] = "",
    fecha_inicio: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "1",
) -> HTMLResponse | RedirectResponse:
    """Registra una meta de ahorro o un gasto programado.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        categoria: Categoría sugerida o libre.
        descripcion: Detalle del objetivo.
        valor_mensual: Cuota mensual en pesos.
        tipo_duracion: `FIJO` o `LIMITADO`.
        meses: Cantidad de cuotas si es limitada.
        fecha_inicio: Primer mes de la proyección.
        quincena: `1` o `2`.

    Returns:
        Redirección al planificador o la vista con el error.
    """
    try:
        proyeccion = ahorro.crear_proyeccion(
            bd,
            usuario.id_usuario,
            categoria,
            descripcion,
            valor_mensual,
            tipo_duracion=tipo_duracion,
            meses=meses,
            fecha_inicio=_fecha_del_formulario(fecha_inicio),
            quincena=quincena,
        )
        auditoria.registrar(
            bd,
            usuario.id_usuario,
            "META_CREADA",
            "proyecciones_ahorro",
            proyeccion.descripcion,
        )
    except (ValueError, ArithmeticError) as error:
        contexto = _contexto(usuario, bd, error=str(error))
        return plantillas.TemplateResponse(
            request,
            "presupuesto/index.html",
            contexto,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(
        url="/presupuesto?guardado=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/presupuesto/metas/{id_proyeccion}/abono",
    name="registrar_abono_proyeccion",
    response_model=None,
)
def registrar_abono(
    id_proyeccion: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    anio: Annotated[str, Form()] = "",
    mes: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Registra o corrige el abono de un mes de la meta.

    Args:
        id_proyeccion: Meta a la que se abona.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        anio: Año del abono.
        mes: Mes del abono (1–12).
        valor: Monto abonado.

    Returns:
        Redirección al planificador con el resultado.
    """
    try:
        abono = ahorro.registrar_abono(
            bd,
            usuario.id_usuario,
            id_proyeccion,
            int(anio),
            int(mes),
            valor,
        )
    except (ValueError, ArithmeticError) as error:
        return RedirectResponse(
            url=f"/presupuesto?error={quote(str(error))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if abono is None:
        return RedirectResponse(
            url=f"/presupuesto?error={quote('La meta no existe.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    auditoria.registrar(
        bd,
        usuario.id_usuario,
        "ABONO_META",
        "abonos_proyeccion",
        f"{id_proyeccion} {anio}-{mes}",
    )
    return RedirectResponse(
        url="/presupuesto?guardado=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/presupuesto/metas/{id_proyeccion}/eliminar", name="eliminar_proyeccion")
def eliminar_proyeccion(
    id_proyeccion: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina una meta y sus abonos.

    Args:
        id_proyeccion: Identificador de la meta.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al planificador.
    """
    if ahorro.eliminar_proyeccion(bd, usuario.id_usuario, id_proyeccion):
        auditoria.registrar(
            bd, usuario.id_usuario, "META_ELIMINADA", "proyecciones_ahorro", id_proyeccion
        )
    return RedirectResponse(url="/presupuesto", status_code=status.HTTP_303_SEE_OTHER)
