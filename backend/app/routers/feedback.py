"""API de reportes de soporte «Ayuda y comentarios» (SRS v2.0, Fase A).

Responsabilidad
---------------
- Recibir los reportes que el usuario estándar envía desde el modal.
- Servir el contador de pendientes, el listado y el cambio de estado al panel
  administrativo.

El envío usa JSON porque el modal es una mejora progresiva con `fetch`. Las
rutas administrativas exigen el rol `ADMIN_OLB` en el servidor, no solo en la
interfaz. OLB_BYTE y la facturación quedan fuera del catálogo de módulos.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import esquemas
from app.core.base_datos import obtener_bd
from app.routers.vistas import contexto_base, plantillas
from app.dependencias import (
    UsuarioSesion,
    exigir_administrador,
    obtener_usuario_actual,
)
from app.servicios import feedback

router = APIRouter(tags=["Soporte"])


class CambioEstado(BaseModel):
    """Cuerpo JSON para actualizar el estado de un reporte.

    Attributes:
        estado: Uno de los valores de `feedback.ESTADOS`.
    """

    estado: str


@router.post("/feedback", status_code=status.HTTP_201_CREATED, name="enviar_feedback")
def enviar_feedback(
    datos: esquemas.FeedbackNuevo,
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, object]:
    """Registra un reporte de soporte enviado por un usuario autenticado.

    El dispositivo se detecta en el servidor a partir del ``User-Agent``; el
    valor que llegue en el cuerpo se ignora a propósito para que no pueda
    falsearse desde el navegador.

    Args:
        datos: Reporte validado por el esquema Pydantic.
        request: Petición HTTP, usada para leer el ``User-Agent``.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Confirmación con el identificador y el estado inicial.

    Raises:
        HTTPException: 400 si el reporte no supera la validación de negocio.
    """
    dispositivo = feedback.detectar_dispositivo(request.headers.get("user-agent", ""))
    try:
        esquemas.validar_formulario(
            esquemas.FeedbackNuevo,
            tipo_reporte=datos.tipo_reporte,
            modulo=datos.modulo,
            descripcion=datos.descripcion,
            dispositivo=dispositivo,
        )
        reporte = feedback.crear_reporte(
            bd,
            usuario,
            datos.tipo_reporte,
            datos.descripcion,
            datos.modulo,
            dispositivo,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    return {
        "ok": True,
        "id": reporte.id_feedback,
        "estado": reporte.estado,
    }


@router.get("/feedback/pendientes", name="contar_feedback_pendiente")
def contar_feedback_pendiente(
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, int]:
    """Devuelve el número de reportes pendientes para el badge del administrador.

    Args:
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        Diccionario con la clave ``pendientes``.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    return {"pendientes": feedback.contar_pendientes(bd)}


@router.get("/feedback", name="listar_feedback")
def listar_feedback(
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, object]:
    """Lista todos los reportes recibidos para el panel administrativo.

    Args:
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        Diccionario con ``reportes`` y el total de ``pendientes``.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    reportes = feedback.listar_reportes(bd)
    return {
        "reportes": [feedback.serialize(reporte) for reporte in reportes],
        "pendientes": feedback.contar_pendientes(bd),
    }


@router.post("/feedback/{id_feedback}/estado", name="actualizar_estado_feedback")
def actualizar_estado_feedback(
    id_feedback: str,
    cambio: CambioEstado,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, object]:
    """Cambia el estado de un reporte y devuelve el contador actualizado.

    Args:
        id_feedback: Identificador del reporte.
        cambio: Nuevo estado enviado por el panel.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        Confirmación con el estado y el nuevo total de pendientes.

    Raises:
        HTTPException: 403 si no es administrador; 404 si el reporte o el estado
            no existen.
    """
    exigir_administrador(usuario)
    reporte = feedback.cambiar_estado(bd, id_feedback, cambio.estado)
    if reporte is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El reporte o el estado indicado no existe.",
        )
    return {
        "ok": True,
        "estado": reporte.estado,
        "pendientes": feedback.contar_pendientes(bd),
    }


@router.get("/admin/comentarios", response_class=HTMLResponse, name="ver_comentarios")
def ver_comentarios(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Muestra el panel de reportes recibidos (SRS v2.0, sección 5.5).

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML con el listado y el contador de pendientes.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    reportes = feedback.listar_reportes(bd)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Comentarios y Reportes",
            "reportes": [feedback.serialize(reporte) for reporte in reportes],
            "pendientes": feedback.contar_pendientes(bd),
            "estados": feedback.ESTADOS,
            "etiquetas_tipo": dict(feedback.TIPOS_REPORTE),
        }
    )
    return plantillas.TemplateResponse(request, "admin/comentarios.html", contexto)
