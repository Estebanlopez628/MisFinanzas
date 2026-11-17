"""Rutas del planificador de ahorro y metas (SRS v1.3, bloque 3).

Responsabilidad
---------------
- Servir la pestaña «Gastos y Presupuesto» con el diagnóstico de liquidez, el
  formulario de proyección y el seguimiento de abonos (solo lectura desde
  SRS v1.6: el abono lo registra el check del gasto fijo).
- Crear metas y eliminarlas. Crear una meta genera sus gastos fijos.

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
from app.servicios import ahorro, auditoria, deducciones_fijas, pagos_metas, perfiles

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


def _meses_del_formulario(cantidad: str, unidad: str) -> str:
    """Convierte el periodo escrito en el formulario a una cantidad de meses.

    SRS v1.6: el usuario escribe la cantidad y elige meses o años.

    Args:
        cantidad: Número escrito en el campo; puede venir vacío.
        unidad: `MESES` o `ANIOS`.

    Returns:
        Cantidad de meses como texto; vacío si el campo llegó vacío.

    Raises:
        ValueError: Si la cantidad no es un número entero.
    """
    texto = (cantidad or "").strip()
    if not texto:
        return ""
    if not texto.isdigit():
        raise ValueError("El periodo debe ser un número entero de meses o años.")
    return str(int(texto) * 12) if unidad == "ANIOS" else str(int(texto))


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
    pagos_metas.asegurar_gastos_de_metas(bd, usuario.id_usuario, hoy.year, hoy.month)
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
            "historial": ahorro.historial_metas(bd, usuario.id_usuario),
            "deducciones": deducciones_fijas.listar_deducciones(bd, usuario.id_usuario),
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
    unidad_periodo: Annotated[str, Form()] = "MESES",
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
        quincena: `1`, `2` o `3` (ambas quincenas).

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
            meses=_meses_del_formulario(meses, unidad_periodo),
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
        hoy = date.today()
        pagos_metas.asegurar_gastos_de_metas(bd, usuario.id_usuario, hoy.year, hoy.month)
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
            bd, usuario.id_usuario, "META_ARCHIVADA", "proyecciones_ahorro", id_proyeccion
        )
    return RedirectResponse(url="/presupuesto", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/presupuesto/metas/{id_proyeccion}/extender",
    name="extender_proyeccion",
    response_model=None,
)
def extender_meta(
    request: Request,
    id_proyeccion: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    cantidad: Annotated[str, Form()] = "",
    unidad_periodo: Annotated[str, Form()] = "MESES",
) -> HTMLResponse | RedirectResponse:
    """Extiende una meta cumplida o en curso y regenera sus cuotas.

    Args:
        request: Petición HTTP.
        id_proyeccion: Meta a extender.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        cantidad: Número de meses o años a agregar.
        unidad_periodo: `MESES` o `ANIOS`.

    Returns:
        Redirección al planificador o la vista con el error.
    """
    try:
        if not cantidad.strip():
            raise ValueError("Escribe cuántos meses o años quieres extender.")
        meses = int(_meses_del_formulario(cantidad, unidad_periodo))
        proyeccion = ahorro.extender_proyeccion(bd, usuario.id_usuario, id_proyeccion, meses)
    except ValueError as error:
        return RedirectResponse(
            url=f"/presupuesto?error={quote(str(error))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if proyeccion is None:
        return RedirectResponse(
            url=f"/presupuesto?error={quote('La meta no existe.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    auditoria.registrar(
        bd, usuario.id_usuario, "META_EXTENDIDA", "proyecciones_ahorro", id_proyeccion
    )
    hoy = date.today()
    pagos_metas.asegurar_gastos_de_metas(bd, usuario.id_usuario, hoy.year, hoy.month)
    return RedirectResponse(url="/presupuesto?guardado=1", status_code=status.HTTP_303_SEE_OTHER)

# ---------------------------------------------------------------------------
# Deducciones fijas del salario (SRS v1.4, REQ-08)
# ---------------------------------------------------------------------------


@router.post("/presupuesto/deducciones", name="crear_deduccion_fija", response_model=None)
def crear_deduccion_fija(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    descripcion: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "1",
) -> HTMLResponse | RedirectResponse:
    """Registra una deducción fija del salario (libranza, fondo, seguro).

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        descripcion: Concepto del descuento.
        valor: Monto por pago en pesos.
        quincena: `1` o `2`, pago del que se descuenta.

    Returns:
        Redirección al planificador o la vista con el error (400).
    """
    try:
        deduccion = deducciones_fijas.crear_deduccion(
            bd, usuario.id_usuario, descripcion, valor, quincena
        )
    except (ValueError, ArithmeticError) as error:
        contexto = _contexto(usuario, bd, error=str(error))
        return plantillas.TemplateResponse(
            request,
            "presupuesto/index.html",
            contexto,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    auditoria.registrar(
        bd, usuario.id_usuario, "DEDUCCION_FIJA_CREADA", "deducciones_fijas", deduccion.descripcion
    )
    return RedirectResponse(
        url="/presupuesto?guardado=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/presupuesto/deducciones/{id_deduccion}/editar",
    name="editar_deduccion_fija",
    response_model=None,
)
def editar_deduccion_fija(
    request: Request,
    id_deduccion: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    descripcion: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "1",
) -> HTMLResponse | RedirectResponse:
    """Modifica una deducción fija existente del usuario.

    Args:
        request: Petición HTTP.
        id_deduccion: Deducción a modificar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        descripcion: Nuevo concepto.
        valor: Nuevo monto por pago.
        quincena: Nueva quincena de descuento.

    Returns:
        Redirección al planificador o la vista con el error.
    """
    try:
        actualizada = deducciones_fijas.actualizar_deduccion(
            bd, usuario.id_usuario, id_deduccion, descripcion, valor, quincena
        )
    except (ValueError, ArithmeticError) as error:
        contexto = _contexto(usuario, bd, error=str(error))
        return plantillas.TemplateResponse(
            request,
            "presupuesto/index.html",
            contexto,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if actualizada is None:
        return RedirectResponse(
            url=f"/presupuesto?error={quote('La deducción no existe.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    auditoria.registrar(
        bd, usuario.id_usuario, "DEDUCCION_FIJA_ACTUALIZADA", "deducciones_fijas", id_deduccion
    )
    return RedirectResponse(
        url="/presupuesto?guardado=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/presupuesto/deducciones/{id_deduccion}/eliminar",
    name="eliminar_deduccion_fija",
)
def eliminar_deduccion_fija(
    id_deduccion: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina una deducción fija del usuario.

    Args:
        id_deduccion: Deducción a eliminar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al planificador.
    """
    if deducciones_fijas.eliminar_deduccion(bd, usuario.id_usuario, id_deduccion):
        auditoria.registrar(
            bd, usuario.id_usuario, "DEDUCCION_FIJA_ELIMINADA", "deducciones_fijas", id_deduccion
        )
    return RedirectResponse(url="/presupuesto", status_code=status.HTTP_303_SEE_OTHER)
