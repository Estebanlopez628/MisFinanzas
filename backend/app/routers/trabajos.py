"""Rutas del módulo "Trabajos Extras".

Responsabilidad
---------------
Registrar contratos de ingresos independientes con su tipo de contrato y
frecuencia, generar sus pagos del mes y permitir marcarlos como cobrados con el
mismo check de los gastos fijos. El neto cobrado se transfiere al diagnóstico de
«Gastos y Presupuesto»; nunca se suma al sueldo ni a las quincenas principales.
Es un módulo de acceso general: cada usuario ve únicamente sus propios trabajos
(SRS v1.2, ampliado en SRS v1.7 bloque E).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.core.texto import formatear_mes_anio
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, capacidad, perfiles, trabajos

router = APIRouter(tags=["Trabajos Extras"])


def _fecha_opcional(texto: str) -> date | None:
    """Convierte una fecha del formulario en `date`, o `None` si viene vacía.

    Args:
        texto: Valor ``AAAA-MM-DD`` o cadena vacía.

    Returns:
        Fecha válida o `None`.

    Raises:
        ValueError: Si el texto no es una fecha ISO.
    """
    limpio = texto.strip()
    return date.fromisoformat(limpio) if limpio else None


def _contexto(
    usuario: UsuarioSesion,
    bd: Session,
    *,
    error: str | None = None,
    guardado: bool = False,
) -> dict[str, object]:
    """Prepara el contexto de la vista de Trabajos Extras.

    Genera los pagos del mes visible que falten antes de listarlos, de modo que
    un contrato indefinido extienda su ventana de doce meses al abrirlo.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error.
        guardado: Bandera de éxito.

    Returns:
        Diccionario para la plantilla.
    """
    hoy = date.today()
    trabajos.asegurar_pagos_trabajos(bd, usuario.id_usuario, hoy.year, hoy.month)
    perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Trabajos Extras",
            "trabajos": trabajos.listar_trabajos(bd, usuario.id_usuario),
            "bloques": trabajos.pagos_del_mes(bd, usuario.id_usuario, hoy.year, hoy.month),
            "resumen": trabajos.resumen_trabajos(
                bd, usuario.id_usuario, hoy.year, hoy.month
            ),
            "extras_mes": trabajos.extras_cobrados_mes(
                bd, usuario.id_usuario, hoy.year, hoy.month
            ),
            "capacidad": capacidad.capacidad_endeudamiento(
                bd, usuario.id_usuario, perfil, hoy.year, hoy.month
            ),
            "mes_visible": formatear_mes_anio(hoy.year, hoy.month),
            "hoy": hoy,
            "error": error,
            "guardado": guardado,
            "fecha_hoy": hoy.isoformat(),
            "contratos": trabajos.CONTRATOS_VALIDOS,
            "frecuencias": trabajos.FRECUENCIAS_VALIDAS,
        }
    )
    return contexto


@router.get("/trabajos-extras", response_class=HTMLResponse, name="ver_trabajos_extras")
def ver_trabajos_extras(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
    error: str = "",
) -> HTMLResponse:
    """Muestra los trabajos extras y sus pagos del mes.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.
        error: Mensaje de error devuelto por una acción anterior.

    Returns:
        HTML del módulo.
    """
    return plantillas.TemplateResponse(
        request,
        "trabajos/index.html",
        _contexto(usuario, bd, guardado=bool(guardado), error=error or None),
    )


@router.post("/trabajos-extras", name="crear_trabajo", response_model=None)
def crear_trabajo(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    descripcion: Annotated[str, Form()] = "",
    cliente: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
    fecha: Annotated[str, Form()] = "",
    tipo_contrato: Annotated[str, Form()] = trabajos.CONTRATO_INDEFINIDO,
    frecuencia: Annotated[str, Form()] = trabajos.FRECUENCIA_MENSUAL,
    fecha_fin: Annotated[str, Form()] = "",
    fecha_pago: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra un trabajo extra y genera sus pagos del mes.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        descripcion: Trabajo realizado.
        cliente: Cliente que contrató.
        valor: Monto de cada pago.
        fecha: Fecha de inicio del contrato (ISO); si falta se usa hoy.
        tipo_contrato: `INDEFINIDO` o `TERMINO_FIJO`.
        frecuencia: `MENSUAL` o `QUINCENAL`.
        fecha_fin: Final del contrato; obligatorio en término fijo.
        fecha_pago: Fecha del primer pago; si falta se usa el inicio.

    Returns:
        Redirección o vista con error.
    """
    try:
        fecha_inicio = _fecha_opcional(fecha) or date.today()
        trabajo = trabajos.crear_trabajo(
            bd,
            usuario.id_usuario,
            descripcion,
            valor,
            fecha_inicio,
            cliente or None,
            tipo_contrato=tipo_contrato,
            frecuencia=frecuencia,
            fecha_fin=_fecha_opcional(fecha_fin),
            fecha_pago=_fecha_opcional(fecha_pago),
        )
        hoy = date.today()
        trabajos.asegurar_pagos_trabajos(bd, usuario.id_usuario, hoy.year, hoy.month)
        auditoria.registrar(
            bd, usuario.id_usuario, "TRABAJO_CREADO", "trabajos_extras", trabajo.descripcion
        )
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "trabajos/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/trabajos-extras?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/trabajos-extras/{id_trabajo}/estado", name="cambiar_estado_trabajo", response_model=None)
def cambiar_estado(
    request: Request,
    id_trabajo: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    estado: Annotated[str, Form()] = trabajos.ESTADO_COBRADO,
) -> HTMLResponse | RedirectResponse:
    """Marca un contrato como cobrado o pendiente (compatibilidad).

    El cobro real se registra pago a pago con el check de cada fila.

    Args:
        request: Petición HTTP.
        id_trabajo: Trabajo a modificar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        estado: Nuevo estado.

    Returns:
        Redirección o vista con error.
    """
    try:
        trabajos.cambiar_estado(bd, usuario.id_usuario, id_trabajo, estado)
    except ValueError as error:
        return plantillas.TemplateResponse(
            request,
            "trabajos/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/trabajos-extras", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/trabajos-extras/{id_trabajo}/eliminar", name="eliminar_trabajo")
def eliminar_trabajo(
    id_trabajo: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina un trabajo extra y todos sus pagos generados.

    Args:
        id_trabajo: Trabajo a eliminar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al listado.
    """
    if trabajos.eliminar_trabajo(bd, usuario.id_usuario, id_trabajo):
        auditoria.registrar(
            bd, usuario.id_usuario, "TRABAJO_ELIMINADO", "trabajos_extras", id_trabajo
        )
    return RedirectResponse(url="/trabajos-extras", status_code=status.HTTP_303_SEE_OTHER)
