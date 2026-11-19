"""Dependencias de sesión y autorización (RBAC).

Responsabilidad
---------------
- Leer la cookie de sesión, verificar el token y reconstruir el usuario desde la
  base de datos (una cuenta desactivada pierde el acceso de inmediato).
- Exponer dos dependencias: una estricta (`obtener_usuario_actual`) y una
  opcional (`usuario_opcional`, útil en login y registro).
- Centralizar la comprobación de rol administrador.

La sesión vive en una cookie `HttpOnly`, por lo que no puede ser leída ni
alterada desde JavaScript.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.core.config import obtener_configuracion
from app.core.seguridad import TokenInvalido, decodificar_token
from app.servicios import perfiles, usuarios

# Nombre de la cookie de sesión en todo el proyecto.
NOMBRE_COOKIE = "sesion"

ROL_ADMIN = usuarios.ROL_ADMIN
ROL_USUARIO = usuarios.ROL_USUARIO
ROLES_VALIDOS: tuple[str, ...] = (ROL_ADMIN, ROL_USUARIO)


class SesionRequerida(Exception):
    """Se lanza cuando una ruta protegida se invoca sin sesión válida.

    La aplicación la captura en `app.main` para redirigir al login (HTML) o
    responder 401 (JSON).
    """


class OnboardingRequerido(Exception):
    """Se lanza cuando el usuario aún no configuró su perfil financiero.

    La aplicación la captura en `app.main` para enviar al onboarding (HTML) o
    responder 409 (JSON). Así ningún módulo queda accesible antes de capturar el
    sueldo y la modalidad de pago (SRS v1.2, bloque 1).
    """


@dataclass(frozen=True)
class UsuarioSesion:
    """Usuario autenticado durante la petición.

    Attributes:
        id_usuario: Identificador del usuario.
        correo: Correo de la cuenta.
        alias: Apodo para los saludos personalizados.
        rol: Rol RBAC; determina tarjetas y rutas visibles.
        perfil_configurado: `True` si ya existe su perfil financiero. Se calcula
            en cada petición para que el onboarding se libere al guardar.
        avatar_url: Foto de perfil de Google, o `None` para mostrar las iniciales.
    """

    id_usuario: str
    correo: str
    alias: str
    rol: str
    perfil_configurado: bool = False
    avatar_url: str | None = None

    @property
    def es_administrador(self) -> bool:
        """Indica si el usuario tiene privilegios de administrador.

        Returns:
            `True` si el rol es ``ADMIN_OLB``.
        """
        return self.rol == ROL_ADMIN

    @property
    def puede_ver_olb_byte(self) -> bool:
        """Indica si el correo está autorizado para el módulo OLB_BYTE.

        Returns:
            `True` si el correo figura en `CORREOS_OLB_BYTE`.
        """
        return self.correo.strip().lower() in obtener_configuracion().correos_olb_byte


def _usuario_desde_token(bd: Session, token: str) -> UsuarioSesion | None:
    """Valida un token y construye el usuario de sesión.

    Además de verificar la firma, se consulta la base de datos para detectar
    cuentas eliminadas o desactivadas después de emitir el token.

    Args:
        bd: Sesión de base de datos.
        token: Token JWT de la cookie de sesión.

    Returns:
        El usuario autenticado o `None` si el token no es válido.
    """
    try:
        contenido = decodificar_token(token)
    except TokenInvalido:
        return None

    usuario = usuarios.obtener_por_id(bd, str(contenido["sub"]))
    if usuario is None or not usuario.activo:
        return None

    return UsuarioSesion(
        id_usuario=usuario.id_usuario,
        correo=usuario.correo,
        alias=usuario.alias,
        rol=usuario.rol,
        perfil_configurado=perfiles.perfil_configurado(bd, usuario.id_usuario),
        avatar_url=usuario.avatar_url,
    )


def usuario_opcional(
    request: Request, bd: Session = Depends(obtener_bd)
) -> UsuarioSesion | None:
    """Devuelve el usuario si hay sesión válida, sin exigirla.

    Args:
        request: Petición HTTP con las cookies.
        bd: Sesión de base de datos inyectada por FastAPI.

    Returns:
        El usuario autenticado o `None`.
    """
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        return None
    return _usuario_desde_token(bd, token)


def obtener_usuario_actual(
    request: Request, bd: Session = Depends(obtener_bd)
) -> UsuarioSesion:
    """Exige una sesión válida y un perfil financiero configurado.

    Args:
        request: Petición HTTP con las cookies.
        bd: Sesión de base de datos inyectada por FastAPI.

    Returns:
        El usuario autenticado con su onboarding completo.

    Raises:
        SesionRequerida: Si no hay cookie, el token es inválido o la cuenta ya
            no está activa.
        OnboardingRequerido: Si el usuario todavía no guardó su perfil.
    """
    usuario = usuario_opcional(request, bd)
    if usuario is None:
        raise SesionRequerida()
    if not usuario.perfil_configurado:
        raise OnboardingRequerido()
    return usuario


def obtener_usuario_sin_onboarding(
    request: Request, bd: Session = Depends(obtener_bd)
) -> UsuarioSesion:
    """Exige sesión válida sin bloquear por onboarding.

    Se usa en las rutas del propio perfil (y en el cambio de contraseña) para
    que el usuario pueda completar su configuración sin entrar en un bucle de
    redirecciones.

    Args:
        request: Petición HTTP con las cookies.
        bd: Sesión de base de datos inyectada por FastAPI.

    Returns:
        El usuario autenticado, aunque no tenga perfil financiero.

    Raises:
        SesionRequerida: Si no hay cookie o la cuenta no está activa.
    """
    usuario = usuario_opcional(request, bd)
    if usuario is None:
        raise SesionRequerida()
    return usuario


def exigir_administrador(usuario: UsuarioSesion) -> None:
    """Valida que el usuario sea administrador antes de una acción privada.

    Args:
        usuario: Usuario autenticado de la petición.

    Raises:
        HTTPException: 403 si el rol no es ``ADMIN_OLB``.
    """
    if not usuario.es_administrador:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido al administrador OLB_BYTE.",
        )


def exigir_olb_byte(usuario: UsuarioSesion) -> UsuarioSesion:
    """Permite el módulo OLB_BYTE solo a los correos autorizados (SRS v1.8).

    Args:
        usuario: Usuario autenticado de la petición.

    Returns:
        El mismo usuario si puede entrar.

    Raises:
        HTTPException: 403 si su correo no está autorizado.
    """
    if not usuario.puede_ver_olb_byte:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este módulo está disponible solo para los usuarios autorizados.",
        )
    return usuario
