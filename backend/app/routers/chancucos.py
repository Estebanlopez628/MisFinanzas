"""Panel de Chancucos: referencias de pago con copiado y botón *Pagar*.

Responsabilidad
---------------
- Listar, crear, marcar como favorito y eliminar referencias.
- Exponer el número de referencia para que la mejora progresiva lo copie al
  portapapeles y abrir la pasarela oficial con el botón *Pagar*.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, exigir_administrador, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, chancucos

router = APIRouter(tags=["Chancucos"])


@router.get("/chancucos", response_class=HTMLResponse, name="ver_chancucos")
def ver_chancucos(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
    error: str = "",
) -> HTMLResponse:
    """Muestra el panel de referencias de pago.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.
        error: Mensaje de error opcional.

    Returns:
        HTML del panel.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Configurar Atajos de Pago",
            "chancucos": chancucos.listar_chancucos(bd, usuario.id_usuario),
            "guardado": bool(guardado),
            "error": error or None,
            "seccion": "atajos",
        }
    )
    return plantillas.TemplateResponse(request, "chancucos/index.html", contexto)


@router.post("/chancucos", name="crear_chancuco")
def crear_chancuco(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    descripcion: Annotated[str, Form()] = "",
    numero_referencia: Annotated[str, Form()] = "",
    url_pago: Annotated[str, Form()] = "",
    favorito: Annotated[str, Form()] = "",
    unico_pago: Annotated[str, Form()] = "1",
    dia_pago_1: Annotated[str, Form()] = "",
    dia_pago_2: Annotated[str, Form()] = "",
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Registra un atajo de pago.

    La SRS v1.3 redujo el formulario a tres datos: descripción, número de
    referencia y enlace de pago. Los antiguos ``entidad`` y ``tipo_servicio``
    se fusionaron en ``descripcion``. SRS v1.7 agrega uno o dos días de pago
    mensuales: con ``unico_pago = 1`` solo se guarda el primero.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        descripcion: Texto que identifica el atajo.
        numero_referencia: Número a copiar.
        url_pago: Pasarela oficial; opcional.
        favorito: ``1`` para marcarlo como favorito.
        unico_pago: ``1`` si el servicio se paga una sola vez al mes.
        dia_pago_1: Día del mes del primer pago (1–31).
        dia_pago_2: Día del mes del segundo pago (1–31); solo si no es único.
        origen: ``finanzas`` cuando el formulario está embebido en Mis Finanzas.

    Returns:
        Redirección al panel con el resultado.
    """
    exigir_administrador(usuario)
    destino = (
        "/finanzas?guardado_chancuco=1#chancucos"
        if origen == "finanzas"
        else "/chancucos?guardado=1"
    )
    base_error = (
        "/finanzas?error_chancuco=" if origen == "finanzas" else "/chancucos?error="
    )
    sufijo_error = "#chancucos" if origen == "finanzas" else ""
    try:
        chancuco = chancucos.crear_chancuco(
            bd,
            usuario.id_usuario,
            descripcion,
            numero_referencia,
            url_pago or None,
            favorito == "1",
            dia_pago_1=dia_pago_1,
            dia_pago_2=None if unico_pago == "1" else dia_pago_2,
        )
        auditoria.registrar(
            bd, usuario.id_usuario, "CHANCUCO_CREADO", "chancucos", chancuco.descripcion
        )
    except (ValueError, ArithmeticError) as error:
        from urllib.parse import quote

        return RedirectResponse(
            url=f"{base_error}{quote(str(error))}{sufijo_error}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(url=destino, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/chancucos/{id_chancuco}/favorito", name="alternar_favorito_chancuco")
def alternar_favorito(
    id_chancuco: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Marca o desmarca una referencia como favorita.

    Args:
        id_chancuco: Referencia a modificar.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        origen: ``finanzas`` cuando la acción viene del panel embebido.

    Returns:
        Redirección al panel correspondiente.
    """
    exigir_administrador(usuario)
    chancucos.alternar_favorito(bd, usuario.id_usuario, id_chancuco)
    destino = "/finanzas#chancucos" if origen == "finanzas" else "/chancucos"
    return RedirectResponse(url=destino, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/chancucos/{id_chancuco}/eliminar", name="eliminar_chancuco")
def eliminar_chancuco(
    id_chancuco: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Elimina una referencia de pago.

    Args:
        id_chancuco: Referencia a eliminar.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        origen: ``finanzas`` cuando la acción viene del panel embebido.

    Returns:
        Redirección al panel correspondiente.
    """
    exigir_administrador(usuario)
    if chancucos.eliminar_chancuco(bd, usuario.id_usuario, id_chancuco):
        auditoria.registrar(
            bd, usuario.id_usuario, "CHANCUCO_ELIMINADO", "chancucos", id_chancuco
        )
    destino = "/finanzas#chancucos" if origen == "finanzas" else "/chancucos"
    return RedirectResponse(url=destino, status_code=status.HTTP_303_SEE_OTHER)
