"""Middlewares de seguridad HTTP.

Responsabilidad
---------------
- Rechazar peticiones de escritura con `Origin` ajeno (protección CSRF sin
  obligar a incrustar tokens en cada formulario).
- Añadir cabeceras de endurecimiento a todas las respuestas (CSP, nosniff,
  política de referencia y de permisos).

La decisión se documenta en `MEMORY.md` (ADR-10). Si en el futuro se sirve la
aplicación detrás de un proxy, el proxy debe reenviar `Host` y `Origin` sin
alterarlos para que la comparación siga siendo válida.
"""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

CABECERAS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


class MiddlewareSeguridad(BaseHTTPMiddleware):
    """Aplica CSRF por origen y cabeceras de seguridad."""

    @staticmethod
    def _con_cabeceras(respuesta: Response) -> Response:
        """Añade las cabeceras de endurecimiento si no están presentes.

        Args:
            respuesta: Respuesta que se enviará al cliente.

        Returns:
            La misma respuesta con las cabeceras aplicadas.
        """
        for nombre, valor in CABECERAS_SEGURIDAD.items():
            respuesta.headers.setdefault(nombre, valor)
        return respuesta

    async def dispatch(self, request: Request, call_next) -> Response:
        """Procesa la petición y aplica las políticas.

        Args:
            request: Petición entrante.
            call_next: Siguiente capa de la aplicación.

        Returns:
            Respuesta con las cabeceras de seguridad o un 403 si el origen es
            ajeno en un método de escritura.
        """
        if request.method not in METODOS_SEGUROS:
            origen = request.headers.get("origin")
            if origen:
                anfitrion_solicitud = request.url.netloc.lower()
                anfitrion_origen = urlparse(origen).netloc.lower()
                if anfitrion_origen != anfitrion_solicitud:
                    return self._con_cabeceras(
                        JSONResponse(
                            {
                                "ok": False,
                                "errores": ["Origen no permitido para esta operación."],
                            },
                            status_code=403,
                        )
                    )
            elif request.headers.get("sec-fetch-site", "").lower() == "cross-site":
                return self._con_cabeceras(
                    JSONResponse(
                        {
                            "ok": False,
                            "errores": ["Origen no permitido para esta operación."],
                        },
                        status_code=403,
                    )
                )

        respuesta = await call_next(request)
        return self._con_cabeceras(respuesta)
