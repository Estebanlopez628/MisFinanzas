"""Administración de cuentas (solo `ADMIN_OLB`).

Responsabilidad
---------------
Listar usuarios, cambiar su rol y activar/desactivar cuentas. El servidor
verifica el rol en cada petición; la interfaz solo oculta lo que el usuario no
puede usar.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, exigir_administrador, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, usuarios

router = APIRouter(tags=["Administración"])


def _contexto_admin(
    usuario: UsuarioSesion, lista: list[object], *, error: str | None = None
) -> dict[str, object]:
    """Prepara el contexto de la vista de usuarios.

    Args:
        usuario: Administrador autenticado.
        lista: Usuarios a mostrar.
        error: Mensaje de error opcional.

    Returns:
        Diccionario para la plantilla.
    """
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Usuarios",
            "usuarios": lista,
            "roles": (usuarios.ROL_ADMIN, usuarios.ROL_USUARIO),
            "error": error,
        }
    )
    return contexto


@router.get("/admin/usuarios", response_class=HTMLResponse, name="ver_usuarios")
def ver_usuarios(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Lista todas las cuentas registradas.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML con la tabla de usuarios.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    return plantillas.TemplateResponse(
        request,
        "admin/usuarios.html",
        _contexto_admin(usuario, usuarios.listar_usuarios(bd)),
    )


@router.post("/admin/usuarios/{id_usuario}/rol", name="cambiar_rol_usuario", response_model=None)
def cambiar_rol_usuario(
    request: Request,
    id_usuario: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    rol: Annotated[str, Form()] = usuarios.ROL_USUARIO,
) -> HTMLResponse | RedirectResponse:
    """Asigna un rol a otra cuenta.

    Args:
        request: Petición HTTP.
        id_usuario: Cuenta a modificar.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        rol: Nuevo rol.

    Returns:
        Redirección al listado; si falla, el listado con el error.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    error = None
    if id_usuario == usuario.id_usuario:
        error = "No puedes cambiar tu propio rol."
    else:
        try:
            usuarios.cambiar_rol(bd, id_usuario, rol)
            auditoria.registrar(
                bd,
                usuario.id_usuario,
                "ROL_CAMBIADO",
                "usuarios",
                f"Cuenta {id_usuario} → {rol}",
            )
        except ValueError as fallo:
            error = str(fallo)

    if error:
        return plantillas.TemplateResponse(
            request,
            "admin/usuarios.html",
            _contexto_admin(usuario, usuarios.listar_usuarios(bd), error=error),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/admin/usuarios", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/usuarios/{id_usuario}/estado", name="cambiar_estado_usuario", response_model=None)
def cambiar_estado_usuario(
    request: Request,
    id_usuario: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    activo: Annotated[str, Form()] = "1",
) -> HTMLResponse | RedirectResponse:
    """Activa o desactiva una cuenta (baja lógica).

    Args:
        request: Petición HTTP.
        id_usuario: Cuenta a modificar.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        activo: ``1`` para activar, ``0`` para desactivar.

    Returns:
        Redirección al listado; si falla, el listado con el error.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    error = None
    if id_usuario == usuario.id_usuario:
        error = "No puedes desactivar tu propia cuenta."
    else:
        try:
            usuarios.cambiar_estado(bd, id_usuario, activo == "1")
            auditoria.registrar(
                bd,
                usuario.id_usuario,
                "ESTADO_CAMBIADO",
                "usuarios",
                f"Cuenta {id_usuario} → {'activa' if activo == '1' else 'inactiva'}",
            )
        except ValueError as fallo:
            error = str(fallo)

    if error:
        return plantillas.TemplateResponse(
            request,
            "admin/usuarios.html",
            _contexto_admin(usuario, usuarios.listar_usuarios(bd), error=error),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/admin/usuarios", status_code=status.HTTP_303_SEE_OTHER)
