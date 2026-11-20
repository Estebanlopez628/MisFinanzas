"""Punto de entrada de la aplicación **Finanzas y OLB_BYTE**.

Responsabilidad
---------------
Construir la aplicación FastAPI, montar los archivos estáticos, registrar los
routers, inicializar la base de datos y centralizar el manejo de la sesión
ausente. Se usa el patrón *application factory* para que las pruebas puedan
crear instancias aisladas.

Ejecución local:
    cd backend
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.base_datos import inicializar_base_datos
from app.core.config import obtener_configuracion
from app.core.middleware import MiddlewareSeguridad
from app.dependencias import OnboardingRequerido, SesionRequerida
from app.routers import (
    admin,
    auth,
    chancucos,
    deudas,
    finanzas,
    gastos,
    incapacidades,
    olb_byte,
    perfil,
    presupuesto,
    pwa,
    trabajos,
    vistas,
)

RUTA_APP = Path(__file__).resolve().parent
RUTA_ESTATICOS = RUTA_APP / "static"


def _pide_json(request: Request) -> bool:
    """Indica si el cliente espera una respuesta JSON.

    Se usa para distinguir la calculadora reactiva (``fetch``) de la navegación
    normal del navegador: la primera debe recibir 401 y la segunda una
    redirección al login.

    Args:
        request: Petición HTTP entrante.

    Returns:
        `True` si la cabecera ``Accept`` contiene ``application/json`` o si la
        petición se hizo con ``fetch`` (``X-Requested-With``).
    """
    acepta = request.headers.get("accept", "")
    return "application/json" in acepta or request.headers.get("x-requested-with") == "fetch"


def _manejar_sesion_requerida(request: Request, _error: SesionRequerida) -> JSONResponse | RedirectResponse:
    """Responde a una petición sin sesión válida.

    Args:
        request: Petición que disparó la excepción.
        _error: Excepción `SesionRequerida` (no se usa su contenido).

    Returns:
        JSON 401 para clientes de datos o redirección 303 al login para el
        navegador.
    """
    if _pide_json(request):
        return JSONResponse(
            {"ok": False, "errores": ["Debes iniciar sesión para continuar."]},
            status_code=401,
        )
    return RedirectResponse(url="/login", status_code=303)


def _manejar_onboarding(
    request: Request, _error: OnboardingRequerido
) -> JSONResponse | RedirectResponse:
    """Envía al onboarding cuando el perfil financiero aún no existe.

    Args:
        request: Petición que disparó la excepción.
        _error: Excepción `OnboardingRequerido` (no se usa su contenido).

    Returns:
        JSON 409 para clientes de datos o redirección 303 a la vista de perfil
        para el navegador.
    """
    if _pide_json(request):
        return JSONResponse(
            {
                "ok": False,
                "errores": ["Completa tu perfil financiero antes de continuar."],
            },
            status_code=409,
        )
    return RedirectResponse(url="/perfil?bienvenida=1", status_code=303)


def _pagina_dato_invalido(mensaje: str) -> str:
    """Arma una página mínima para un dato rechazado en el servidor.

    SRS v1.8: la red de seguridad del blindaje de formularios. Si un valor
    inesperado llega hasta una vista que no lo esperaba, se muestra este aviso en
    lugar de una página de error sin explicación.

    Args:
        mensaje: Explicación legible para el usuario.

    Returns:
        Documento HTML completo con el aviso y un enlace de regreso.
    """
    seguro = html.escape(mensaje)
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        "<title>Datos por corregir</title>"
        '<link rel="stylesheet" href="/estaticos/css/estilos.css" /></head>'
        '<body class="pagina"><main class="contenedor">'
        '<section class="panel">'
        '<h1 class="panel__titulo">Datos por corregir</h1>'
        f'<div class="alerta alerta--error" role="alert">{seguro}</div>'
        '<p class="ayuda">Corrige el dato e inténtalo de nuevo.</p>'
        '<div class="acciones-formulario">'
        '<a class="boton boton--secundario" href="javascript:history.back()">'
        "← Volver al formulario</a></div>"
        "</section></main></body></html>"
    )


def _manejar_dato_invalido(request: Request, error: ValueError) -> HTMLResponse | JSONResponse:
    """Responde a un `ValueError` no controlado con un aviso en pantalla.

    Args:
        request: Petición que disparó la excepción.
        error: Excepción con el mensaje para el usuario.

    Returns:
        400 con JSON para clientes de datos o con una página HTML para el
        navegador.
    """
    mensaje = str(error) or "Revisa los datos e ingrésalos de nuevo."
    if _pide_json(request):
        return JSONResponse({"ok": False, "errores": [mensaje]}, status_code=400)
    return HTMLResponse(_pagina_dato_invalido(mensaje), status_code=400)


def crear_aplicacion() -> FastAPI:
    """Crea y configura la instancia principal de FastAPI.

    Monta el directorio de estáticos bajo ``/estaticos``, registra los routers,
    inicializa el esquema SQLite y siembra las cuentas de demostración.

    Returns:
        Aplicación FastAPI lista para ser servida por Uvicorn.
    """
    configuracion = obtener_configuracion()
    # En producción, una clave débil debe impedir el arranque.
    configuracion.validar_para_produccion()

    aplicacion = FastAPI(
        title=configuracion.nombre,
        version=configuracion.version,
        description=(
            "Plataforma de finanzas personales, liquidación de nómina colombiana "
            "y administración comercial OLB_BYTE."
        ),
        docs_url="/docs" if configuracion.documentacion_habilitada else None,
        redoc_url=None,
    )

    # Los estáticos se sirven desde /estaticos para no colisionar con rutas de negocio.
    aplicacion.mount(
        "/estaticos",
        StaticFiles(directory=str(RUTA_ESTATICOS)),
        name="estaticos",
    )

    aplicacion.add_middleware(MiddlewareSeguridad)

    # Sesión ausente: el navegador vuelve al login y la UI reactiva recibe 401.
    aplicacion.add_exception_handler(SesionRequerida, _manejar_sesion_requerida)
    # Perfil incompleto: ninguna ruta de negocio se abre antes del onboarding.
    aplicacion.add_exception_handler(OnboardingRequerido, _manejar_onboarding)
    # SRS v1.8: un dato inválido que se escape de una vista se explica en
    # pantalla; nunca se rompe la aplicación con una página de error muda.
    aplicacion.add_exception_handler(ValueError, _manejar_dato_invalido)

    # La base de datos se prepara antes de atender la primera petición.
    inicializar_base_datos()

    aplicacion.include_router(vistas.router)
    aplicacion.include_router(pwa.router)
    aplicacion.include_router(auth.router)
    aplicacion.include_router(perfil.router)
    aplicacion.include_router(admin.router)
    aplicacion.include_router(finanzas.router)
    aplicacion.include_router(incapacidades.router)
    aplicacion.include_router(gastos.router)
    aplicacion.include_router(presupuesto.router)
    aplicacion.include_router(chancucos.router)
    aplicacion.include_router(deudas.router)
    aplicacion.include_router(trabajos.router)
    aplicacion.include_router(olb_byte.router)

    return aplicacion


# Instancia que consume Uvicorn: `uvicorn app.main:app`.
app = crear_aplicacion()
