"""Rutas de autenticación: login, registro y cierre de sesión.

Responsabilidad
---------------
- Validar credenciales contra la base de datos.
- Emitir la cookie de sesión firmada (`HttpOnly`, `SameSite=Lax`).
- Permitir el auto-registro únicamente como `USER_FINANZAS`, según el SRS RF-01.
- Cerrar la sesión eliminando la cookie.

No se registra la contraseña ni se devuelve en ningún mensaje de error.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.core.limitador import limitador_login
from app.core.seguridad import DURACION_SESION_MINUTOS, crear_token
from app.dependencias import NOMBRE_COOKIE, UsuarioSesion, usuario_opcional
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, usuarios

router = APIRouter(tags=["Autenticación"])

# Se expone la lista del repositorio para que la vista y las pruebas usen la
# misma fuente; en producción se retirará de la pantalla de login.
CUENTAS_DEMO = usuarios.CUENTAS_DEMO


def _clave_intento(request: Request, correo: str) -> str:
    """Construye la clave del limitador de intentos.

    Combina la IP de origen con el correo normalizado para no bloquear a todos
    los usuarios de una red cuando una sola cuenta recibe intentos fallidos.

    Args:
        request: Petición HTTP de origen.
        correo: Correo ingresado en el formulario.

    Returns:
        Clave estable para la ventana deslizante.
    """
    ip = request.client.host if request.client else "desconocida"
    return f"{ip}|{correo.strip().lower()}"


def _establecer_cookie(respuesta: RedirectResponse, token: str) -> None:
    """Adjunta la cookie de sesión a una respuesta de redirección.

    Args:
        respuesta: Respuesta que se enviará al navegador.
        token: Token emitido por `crear_token`.
    """
    from app.core.config import obtener_configuracion

    respuesta.set_cookie(
        key=NOMBRE_COOKIE,
        value=token,
        max_age=DURACION_SESION_MINUTOS * 60,
        httponly=True,
        samesite="lax",
        secure=obtener_configuracion().cookie_segura,
        path="/",
    )


@router.get("/login", response_class=HTMLResponse, name="ver_login", response_model=None)
def ver_login(
    request: Request,
    usuario: UsuarioSesion | None = Depends(usuario_opcional),
    registrado: int = 0,
) -> HTMLResponse | RedirectResponse:
    """Muestra el formulario de inicio de sesión.

    Args:
        request: Petición HTTP.
        usuario: Sesión existente; si la hay se redirige al tablero.
        registrado: Bandera de la URL que confirma un registro exitoso.

    Returns:
        La vista de login o una redirección al tablero.
    """
    if usuario is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    contexto = contexto_base(None)
    contexto.update(
        {
            "titulo_pagina": "Iniciar sesión",
            "error": None,
            "registrado": bool(registrado),
            "cuentas_demo": CUENTAS_DEMO,
        }
    )
    return plantillas.TemplateResponse(request, "login.html", contexto)


@router.post("/login", name="procesar_login", response_model=None)
def procesar_login(
    request: Request,
    correo: Annotated[str, Form()],
    contrasena: Annotated[str, Form()],
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Valida las credenciales y abre la sesión.

    Args:
        request: Petición HTTP.
        correo: Correo ingresado en el formulario.
        contrasena: Contraseña en texto plano.
        bd: Sesión de base de datos.

    Returns:
        Redirección al tablero si las credenciales son válidas; la vista de login
        con un mensaje genérico en caso contrario (nunca revela si el correo existe).
    """
    clave = _clave_intento(request, correo)
    if not limitador_login.permitir(clave):
        segundos = limitador_login.segundos_restantes(clave)
        contexto = contexto_base(None)
        contexto.update(
            {
                "titulo_pagina": "Iniciar sesión",
                "error": (
                    "Demasiados intentos fallidos. "
                    f"Espera {segundos} segundo(s) antes de volver a intentar."
                ),
                "registrado": False,
                "cuentas_demo": CUENTAS_DEMO,
                "correo_ingresado": correo,
            }
        )
        return plantillas.TemplateResponse(
            request, "login.html", contexto, status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )

    cuenta = usuarios.autenticar(bd, correo, contrasena)
    if cuenta is None:
        limitador_login.registrar_fallo(clave)
        # La auditoría guarda el correo intentado para detectar patrones de
        # fuerza bruta; nunca guarda la contraseña.
        auditoria.registrar(
            bd, None, "LOGIN_FALLIDO", "usuarios", f"Intento para {correo.strip()[:120]}"
        )
        contexto = contexto_base(None)
        contexto.update(
            {
                "titulo_pagina": "Iniciar sesión",
                "error": "Correo o contraseña incorrectos.",
                "registrado": False,
                "cuentas_demo": CUENTAS_DEMO,
                "correo_ingresado": correo,
            }
        )
        return plantillas.TemplateResponse(
            request, "login.html", contexto, status_code=status.HTTP_401_UNAUTHORIZED
        )

    limitador_login.limpiar(clave)
    auditoria.registrar(bd, cuenta.id_usuario, "LOGIN_OK", "usuarios", "Sesión iniciada")
    token = crear_token(cuenta.id_usuario, cuenta.rol, cuenta.alias)
    respuesta = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    _establecer_cookie(respuesta, token)
    return respuesta


@router.post("/salir", name="cerrar_sesion")
def cerrar_sesion() -> RedirectResponse:
    """Cierra la sesión eliminando la cookie.

    Returns:
        Redirección al login.
    """
    respuesta = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    respuesta.delete_cookie(NOMBRE_COOKIE, path="/")
    return respuesta


@router.get("/registro", response_class=HTMLResponse, name="ver_registro", response_model=None)
def ver_registro(
    request: Request,
    usuario: UsuarioSesion | None = Depends(usuario_opcional),
) -> HTMLResponse | RedirectResponse:
    """Muestra el formulario de registro público.

    Args:
        request: Petición HTTP.
        usuario: Sesión existente; si la hay no tiene sentido registrar otra.

    Returns:
        La vista de registro o una redirección al tablero.
    """
    if usuario is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    contexto = contexto_base(None)
    contexto.update(
        {
            "titulo_pagina": "Crear cuenta",
            "errores": [],
            "valores": {"correo": "", "alias": ""},
        }
    )
    return plantillas.TemplateResponse(request, "registro.html", contexto)


@router.post("/registro", name="procesar_registro", response_model=None)
def procesar_registro(
    request: Request,
    correo: Annotated[str, Form()],
    alias: Annotated[str, Form()],
    contrasena: Annotated[str, Form()],
    confirmar_contrasena: Annotated[str, Form()],
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Crea una cuenta `USER_FINANZAS` previa validación.

    El auto-registro como administrador no existe: el rol se asigna siempre del
    lado del servidor.

    Args:
        request: Petición HTTP.
        correo: Correo del nuevo usuario.
        alias: Apodo para los saludos.
        contrasena: Contraseña elegida.
        confirmar_contrasena: Repetición de la contraseña.
        bd: Sesión de base de datos.

    Returns:
        Redirección al login si el registro es exitoso; la vista con errores en
        caso contrario.
    """
    errores: list[str] = []
    if contrasena != confirmar_contrasena:
        errores.append("Las contraseñas no coinciden.")

    if not errores:
        try:
            usuarios.crear_usuario(bd, correo, contrasena, alias)
        except ValueError as error:
            errores.append(str(error))

    if errores:
        contexto = contexto_base(None)
        contexto.update(
            {
                "titulo_pagina": "Crear cuenta",
                "errores": errores,
                "valores": {"correo": correo, "alias": alias},
            }
        )
        return plantillas.TemplateResponse(
            request, "registro.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    return RedirectResponse(
        url="/login?registrado=1", status_code=status.HTTP_303_SEE_OTHER
    )
