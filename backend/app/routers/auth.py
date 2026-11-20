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

import secrets

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.core.config import obtener_configuracion
from app.core.limitador import limitador_login
from app.core.seguridad import (
    DURACION_SESION_MINUTOS,
    TokenInvalido,
    crear_token,
    crear_token_recuperacion,
    decodificar_token_recuperacion,
)
from app.dependencias import NOMBRE_COOKIE, UsuarioSesion, usuario_opcional
from app.routers.vistas import contexto_base, plantillas
from app.servicios import acceso_google, auditoria, usuarios
from app.servicios import correo as servicio_correo

router = APIRouter(tags=["Autenticación"])

# Se expone la lista del repositorio para que la vista y las pruebas usen la
# misma fuente; en producción se retirará de la pantalla de login.


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
    restablecida: int = 0,
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
            "exito": "Tu contraseña se actualizó. Ya puedes iniciar sesión." if restablecida else None,
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


NOMBRE_COOKIE_ESTADO = "estado_google"


@router.get("/olvide-contrasena", response_class=HTMLResponse, name="ver_olvide_contrasena", response_model=None)
def ver_olvide_contrasena(request: Request) -> HTMLResponse:
    """Muestra cómo recuperar la contraseña (la gestiona el administrador).

    Args:
        request: Petición HTTP.

    Returns:
        Página con las instrucciones de recuperación.
    """
    contexto = contexto_base(None)
    contexto["titulo_pagina"] = "Recuperar contraseña"
    return plantillas.TemplateResponse(request, "olvide_contrasena.html", contexto)


def _login_con_error(request: Request, mensaje: str) -> HTMLResponse:
    """Muestra la pantalla de acceso con un mensaje de error de Google.

    Args:
        request: Petición HTTP.
        mensaje: Texto que se muestra a la persona.

    Returns:
        Página de login con código 401.
    """
    contexto = contexto_base(None)
    contexto.update(
        {
            "titulo_pagina": "Iniciar sesión",
            "error": mensaje,
            "registrado": False,
            "correo_ingresado": "",
        }
    )
    return plantillas.TemplateResponse(
        request, "login.html", contexto, status_code=status.HTTP_401_UNAUTHORIZED
    )


@router.get("/login/google", name="iniciar_google", response_model=None)
def iniciar_google() -> RedirectResponse:
    """Envía a la persona a elegir su cuenta de Gmail.

    Returns:
        Redirección a Google con una cookie de `state`, o al login si no hay
        credenciales configuradas.
    """
    if not acceso_google.google_activo():
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    estado = secrets.token_urlsafe(24)
    respuesta = RedirectResponse(
        url=acceso_google.url_autorizacion(estado), status_code=status.HTTP_303_SEE_OTHER
    )
    respuesta.set_cookie(
        NOMBRE_COOKIE_ESTADO,
        estado,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=obtener_configuracion().cookie_segura,
        path="/",
    )
    return respuesta


@router.get("/login/google/callback", name="callback_google", response_model=None)
def callback_google(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Recibe la respuesta de Google, crea o busca la cuenta y abre la sesión.

    Args:
        request: Petición HTTP con la cookie de `state`.
        code: Código de autorización.
        state: Valor que debe coincidir con la cookie.
        error: Motivo de error que informa Google, si lo hay.
        bd: Sesión de base de datos.

    Returns:
        Redirección al tablero con la sesión abierta, o el login con el error.
    """
    esperado = request.cookies.get(NOMBRE_COOKIE_ESTADO, "")
    if error or not code or not state or not esperado or not secrets.compare_digest(state, esperado):
        return _login_con_error(request, "No se pudo iniciar sesión con Google. Intenta de nuevo.")
    try:
        perfil = acceso_google.intercambiar_codigo(code)
    except acceso_google.AccesoGoogleError as fallo:
        return _login_con_error(request, str(fallo))

    correo = str(perfil["email"]).strip().lower()
    cuenta = usuarios.buscar_por_correo(bd, correo)
    if cuenta is None:
        alias = str(perfil.get("given_name") or perfil.get("name") or correo.split("@")[0])
        alias = alias.strip()[:40] or "Usuario"
        # Las cuentas de Google no usan contraseña local; se guarda una aleatoria que
        # nadie conoce y que cumple la política de contraseñas.
        cuenta = usuarios.crear_usuario(bd, correo, f"Aa1*{secrets.token_urlsafe(24)}", alias)
    if not cuenta.activo:
        return _login_con_error(request, "Tu cuenta está desactivada. Escribe al administrador.")

    # El administrador OLB_BYTE solo se asigna a quien demuestra el correo con Google;
    # un registro con contraseña no comprueba la propiedad del correo.
    if correo in obtener_configuracion().correos_admin_olb and cuenta.rol != usuarios.ROL_ADMIN:
        usuarios.cambiar_rol(bd, cuenta.id_usuario, usuarios.ROL_ADMIN)
        cuenta = usuarios.obtener_por_id(bd, cuenta.id_usuario) or cuenta

    # SRS v1.8: la foto de Google se guarda como enlace y se refresca en cada inicio
    # de sesión; si Google ya no envía una válida, se quita y aparecen las iniciales.
    usuarios.actualizar_avatar(bd, cuenta.id_usuario, str(perfil.get("picture") or "") or None)
    auditoria.registrar(bd, cuenta.id_usuario, "LOGIN_GOOGLE", "usuarios", "Sesión iniciada con Google")
    token = crear_token(cuenta.id_usuario, cuenta.rol, cuenta.alias)
    respuesta = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    _establecer_cookie(respuesta, token)
    respuesta.delete_cookie(NOMBRE_COOKIE_ESTADO, path="/")
    return respuesta


MENSAJE_RECUPERACION = (
    "Si el correo está registrado, te enviamos un enlace para crear una nueva contraseña. "
    "El enlace vence en 15 minutos."
)


def _base_publica(request: Request) -> str:
    """Dirección pública de la app para construir los enlaces del correo.

    Args:
        request: Petición HTTP.

    Returns:
        `APP_URL` si está configurada; si no, la base de la petición.
    """
    configurada = obtener_configuracion().app_url.rstrip("/")
    return configurada or str(request.base_url).rstrip("/")


def _pagina_olvide(request: Request, mensaje: str | None = None, correo: str = "") -> HTMLResponse:
    """Muestra el formulario de recuperación con un mensaje neutral.

    Args:
        request: Petición HTTP.
        mensaje: Texto de confirmación o None.
        correo: Correo escrito, para repoblar el campo.

    Returns:
        Página de recuperación.
    """
    contexto = contexto_base(None)
    contexto.update({"titulo_pagina": "Recuperar contraseña", "mensaje": mensaje, "correo_ingresado": correo})
    return plantillas.TemplateResponse(request, "olvide_contrasena.html", contexto)


def _cuenta_del_enlace(bd: Session, token: str) -> usuarios.Usuario | None:
    """Valida un enlace de recuperación contra la cuenta actual.

    Args:
        bd: Sesión de base de datos.
        token: Token del enlace.

    Returns:
        La cuenta si el enlace es válido, vigente y no se ha usado; si no, None.
    """
    if not token:
        return None
    try:
        contenido = decodificar_token_recuperacion(token)
    except TokenInvalido:
        return None
    cuenta = usuarios.obtener_por_id(bd, str(contenido["sub"]))
    if cuenta is None or not cuenta.activo:
        return None
    if usuarios.huella_contrasena(cuenta) != contenido.get("huella"):
        return None
    return cuenta


def _pagina_restablecer(
    request: Request, token: str, error: str | None = None, codigo: int = 200
) -> HTMLResponse:
    """Muestra el formulario de nueva contraseña o el aviso de enlace no válido.

    Args:
        request: Petición HTTP.
        token: Token del enlace.
        error: Mensaje de error opcional.
        codigo: Código HTTP de la respuesta.

    Returns:
        Página de restablecimiento.
    """
    contexto = contexto_base(None)
    contexto.update({"titulo_pagina": "Nueva contraseña", "token": token, "error": error})
    return plantillas.TemplateResponse(
        request, "restablecer_contrasena.html", contexto, status_code=codigo
    )


@router.post("/olvide-contrasena", response_class=HTMLResponse, name="procesar_olvide_contrasena", response_model=None)
def procesar_olvide_contrasena(
    request: Request,
    correo: Annotated[str, Form()] = "",
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Envía el enlace de recuperación por correo sin revelar si la cuenta existe.

    Args:
        request: Petición HTTP.
        correo: Correo de la cuenta.
        bd: Sesión de base de datos.

    Returns:
        Página con el mismo mensaje neutral en todos los casos.
    """
    correo_limpio = correo.strip().lower()[:254]
    cuenta = usuarios.buscar_por_correo(bd, correo_limpio) if correo_limpio else None
    if cuenta is not None and cuenta.activo:
        token = crear_token_recuperacion(
            cuenta.id_usuario, cuenta.rol, cuenta.alias, usuarios.huella_contrasena(cuenta)
        )
        enlace = f"{_base_publica(request)}/restablecer-contrasena?token={token}"
        cuerpo = (
            f"Hola {cuenta.alias}.\n\n"
            "Para crear una nueva contraseña abre este enlace. Vence en 15 minutos:\n"
            f"{enlace}\n\n"
            "Si no pediste este cambio, ignora este correo."
        )
        servicio_correo.enviar_correo(cuenta.correo, "Recupera tu contraseña · OLB Finanzas", cuerpo)
        auditoria.registrar(bd, cuenta.id_usuario, "RECUPERACION_SOLICITADA", "usuarios", "Enlace de recuperación enviado")
    else:
        auditoria.registrar(
            bd, None, "RECUPERACION_SOLICITADA", "usuarios", f"Solicitud sin cuenta activa: {correo_limpio[:120]}"
        )
    return _pagina_olvide(request, mensaje=MENSAJE_RECUPERACION)


@router.get("/restablecer-contrasena", response_class=HTMLResponse, name="ver_restablecer_contrasena", response_model=None)
def ver_restablecer_contrasena(
    request: Request,
    token: str = "",
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Muestra el formulario de nueva contraseña si el enlace es válido.

    Args:
        request: Petición HTTP.
        token: Token del enlace del correo.
        bd: Sesión de base de datos.

    Returns:
        Formulario o aviso de enlace no válido.
    """
    if _cuenta_del_enlace(bd, token) is None:
        return _pagina_restablecer(request, "", "El enlace no es válido o ya venció. Solicita uno nuevo.", 400)
    return _pagina_restablecer(request, token)


@router.post("/restablecer-contrasena", response_class=HTMLResponse, name="procesar_restablecer_contrasena", response_model=None)
def procesar_restablecer_contrasena(
    request: Request,
    token: Annotated[str, Form()] = "",
    contrasena: Annotated[str, Form()] = "",
    confirmacion: Annotated[str, Form()] = "",
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Cambia la contraseña con un enlace válido y lo invalida al usarlo.

    Args:
        request: Petición HTTP.
        token: Token del enlace.
        contrasena: Nueva contraseña.
        confirmacion: Repetición de la nueva contraseña.
        bd: Sesión de base de datos.

    Returns:
        Redirección al login con confirmación, o el formulario con el error.
    """
    cuenta = _cuenta_del_enlace(bd, token)
    if cuenta is None:
        return _pagina_restablecer(request, "", "El enlace no es válido o ya venció. Solicita uno nuevo.", 400)
    if contrasena != confirmacion:
        return _pagina_restablecer(request, token, "Las contraseñas no coinciden.", 400)
    try:
        usuarios.restablecer_contrasena(bd, cuenta.id_usuario, contrasena)
    except ValueError as fallo:
        return _pagina_restablecer(request, token, str(fallo), 400)
    auditoria.registrar(bd, cuenta.id_usuario, "CONTRASENA_RESTABLECIDA", "usuarios", "Contraseña cambiada por recuperación")
    return RedirectResponse(url="/login?restablecida=1", status_code=status.HTTP_303_SEE_OTHER)

