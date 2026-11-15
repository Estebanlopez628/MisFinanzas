"""Rutas del perfil financiero y del cambio de contraseña.

Responsabilidad
---------------
- Mostrar y guardar el onboarding salarial: alias, sueldo básico, modalidad
  (mensual/quincenal), porcentajes de cada quincena y quincena donde se aplican
  las deducciones de ley.
- Permitir calcular los porcentajes a partir del neto de la quincena sin
  descuentos cuando el usuario no los conoce.
- Permitir el cambio de contraseña verificando la actual.
- Servir de punto de partida para que la calculadora recuerde el sueldo y no se
  tenga que escribir en cada visita.

Este router usa `obtener_usuario_sin_onboarding` para no crear un bucle de
redirecciones cuando el perfil todavía no existe (SRS v1.2, bloque 1).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, obtener_usuario_sin_onboarding
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, perfiles, usuarios

router = APIRouter(tags=["Perfil"])


def _formatear_porcentaje(valor: Decimal | None, defecto: str = "50") -> str:
    """Formatea un porcentaje para un `input type="number"`.

    Args:
        valor: Porcentaje almacenado o `None`.
        defecto: Texto a usar cuando no hay valor.

    Returns:
        Cadena con punto decimal, que es el formato que acepta el navegador.
    """
    if valor is None:
        return defecto
    return f"{valor:.2f}"


def _contexto_perfil(
    usuario: UsuarioSesion,
    perfil: object | None,
    *,
    errores: list[str] | None = None,
    errores_clave: list[str] | None = None,
    guardado: bool = False,
    clave_cambiada: bool = False,
) -> dict[str, object]:
    """Arma el contexto de la vista de perfil.

    Args:
        usuario: Usuario autenticado.
        perfil: Perfil persistido o `None`.
        errores: Errores del formulario salarial.
        errores_clave: Errores del cambio de contraseña.
        guardado: Bandera de éxito del guardado.
        clave_cambiada: Bandera de éxito del cambio de contraseña.

    Returns:
        Diccionario listo para la plantilla.
    """
    valores = {
        "alias": usuario.alias,
        "sueldo_basico": "",
        "modalidad_pago": perfiles.MODALIDAD_MENSUAL,
        "porcentaje_quincena_1": "50",
        "porcentaje_quincena_2": "50",
        "quincena_deducciones": "1",
        "conoce_porcentajes": "SI",
        "neto_sin_deducciones": "",
        "quincena_sin_deducciones": "1",
    }

    if perfil is not None:
        primero, segundo = perfiles.porcentajes_quincena(perfil)
        valores.update(
            {
                "alias": usuario.alias,
                "sueldo_basico": f"{perfil.sueldo_basico:.2f}".replace(".", ","),
                "modalidad_pago": perfil.modalidad_pago,
                "porcentaje_quincena_1": _formatear_porcentaje(primero),
                "porcentaje_quincena_2": _formatear_porcentaje(segundo),
                "quincena_deducciones": str(perfil.quincena_deducciones or 1),
            }
        )

    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Mi perfil",
            "perfil": perfil,
            "valores": valores,
            "errores": errores or [],
            "errores_clave": errores_clave or [],
            "guardado": guardado,
            "clave_cambiada": clave_cambiada,
            # Sin perfil, la vista se presenta como bienvenida de onboarding.
            "es_onboarding": perfil is None,
        }
    )
    return contexto


@router.get("/perfil", response_class=HTMLResponse, name="ver_perfil")
def ver_perfil(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_sin_onboarding),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
    clave: int = 0,
    bienvenida: int = 0,
) -> HTMLResponse:
    """Muestra la configuración salarial y el cambio de contraseña.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado, aunque no tenga perfil.
        bd: Sesión de base de datos.
        guardado: Bandera de la URL que confirma el guardado.
        clave: Bandera de la URL que confirma el cambio de contraseña.
        bienvenida: Bandera de la URL que fuerza el saludo inicial.

    Returns:
        HTML del perfil (con encabezado de bienvenida si es el onboarding).
    """
    perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
    contexto = _contexto_perfil(
        usuario, perfil, guardado=bool(guardado), clave_cambiada=bool(clave)
    )
    if bienvenida and perfil is None:
        contexto["es_onboarding"] = True
    return plantillas.TemplateResponse(request, "perfil/index.html", contexto)


@router.post("/perfil", response_class=HTMLResponse, name="guardar_perfil", response_model=None)
def guardar_perfil(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_sin_onboarding),
    bd: Session = Depends(obtener_bd),
    alias: Annotated[str, Form()] = "",
    sueldo_basico: Annotated[str, Form()] = "",
    modalidad_pago: Annotated[str, Form()] = perfiles.MODALIDAD_MENSUAL,
    porcentaje_quincena_1: Annotated[str, Form()] = "",
    porcentaje_quincena_2: Annotated[str, Form()] = "",
    quincena_deducciones: Annotated[str, Form()] = "1",
    conoce_porcentajes: Annotated[str, Form()] = "SI",
    neto_sin_deducciones: Annotated[str, Form()] = "",
    quincena_sin_deducciones: Annotated[str, Form()] = "1",
) -> HTMLResponse | RedirectResponse:
    """Guarda el perfil salarial del usuario.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        alias: Apodo para los saludos.
        sueldo_basico: Sueldo mensual base.
        modalidad_pago: `MENSUAL` o `QUINCENAL`.
        porcentaje_quincena_1: Porcentaje devengado en la quincena 1.
        porcentaje_quincena_2: Porcentaje devengado en la quincena 2.
        quincena_deducciones: Quincena que soporta salud y pensión.
        conoce_porcentajes: `SI` o `NO`; en `NO` se calcula desde el neto.
        neto_sin_deducciones: Valor recibido en la quincena sin descuentos.
        quincena_sin_deducciones: Quincena a la que corresponde ese valor.

    Returns:
        Redirección al tablero si se guarda; la vista con errores en caso
        contrario.
    """
    errores: list[str] = []
    try:
        usuarios.actualizar_alias(bd, usuario.id_usuario, alias)
    except ValueError as error:
        errores.append(str(error))

    modalidad = modalidad_pago.strip().upper()

    try:
        if modalidad == perfiles.MODALIDAD_QUINCENAL:
            if conoce_porcentajes.strip().upper() == "NO":
                primero, segundo, deducciones = perfiles.calcular_quincenas_desde_neto(
                    sueldo_basico, neto_sin_deducciones, quincena_sin_deducciones
                )
            else:
                primero = porcentaje_quincena_1 or None
                segundo = porcentaje_quincena_2 or None
                deducciones = quincena_deducciones or perfiles.QUINCENA_PRIMERA

            perfiles.guardar_perfil(
                bd,
                usuario.id_usuario,
                sueldo_basico,
                modalidad,
                primero,
                segundo,
                deducciones,
            )
        else:
            perfiles.guardar_perfil(
                bd, usuario.id_usuario, sueldo_basico, modalidad
            )
    except (ValueError, ArithmeticError) as error:
        errores.append(str(error))

    if errores:
        perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
        contexto = _contexto_perfil(usuario, perfil, errores=errores)
        contexto["valores"].update(
            {
                "alias": alias,
                "sueldo_basico": sueldo_basico,
                "modalidad_pago": modalidad,
                "porcentaje_quincena_1": porcentaje_quincena_1,
                "porcentaje_quincena_2": porcentaje_quincena_2,
                "quincena_deducciones": quincena_deducciones,
                "conoce_porcentajes": conoce_porcentajes,
                "neto_sin_deducciones": neto_sin_deducciones,
                "quincena_sin_deducciones": quincena_sin_deducciones,
            }
        )
        contexto["es_onboarding"] = perfil is None
        return plantillas.TemplateResponse(
            request, "perfil/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    auditoria.registrar(
        bd, usuario.id_usuario, "PERFIL_GUARDADO", "perfiles_financieros", "Onboarding salarial"
    )
    # El onboarding termina en el tablero principal, según el flujo aprobado.
    return RedirectResponse(url="/?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/perfil/contrasena", response_class=HTMLResponse, name="cambiar_contrasena", response_model=None)
def cambiar_contrasena(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_sin_onboarding),
    bd: Session = Depends(obtener_bd),
    contrasena_actual: Annotated[str, Form()] = "",
    contrasena_nueva: Annotated[str, Form()] = "",
    confirmar_contrasena: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Cambia la contraseña de la cuenta autenticada.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        contrasena_actual: Contraseña vigente.
        contrasena_nueva: Nueva contraseña.
        confirmar_contrasena: Repetición de la nueva contraseña.

    Returns:
        Redirección al perfil si se cambia; la vista con errores en caso
        contrario.
    """
    errores: list[str] = []
    if contrasena_nueva != confirmar_contrasena:
        errores.append("Las contraseñas nuevas no coinciden.")
    if len(contrasena_nueva) < 8:
        errores.append("La contraseña nueva debe tener al menos 8 caracteres.")

    if not errores:
        try:
            usuarios.cambiar_contrasena(
                bd, usuario.id_usuario, contrasena_actual, contrasena_nueva
            )
        except ValueError as error:
            errores.append(str(error))

    if errores:
        perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
        contexto = _contexto_perfil(usuario, perfil, errores_clave=errores)
        return plantillas.TemplateResponse(
            request, "perfil/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    auditoria.registrar(bd, usuario.id_usuario, "CLAVE_CAMBIADA", "usuarios", "Cambio propio")
    return RedirectResponse(url="/perfil?clave=1", status_code=status.HTTP_303_SEE_OTHER)
