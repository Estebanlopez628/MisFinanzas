"""Recursos PWA: manifiesto, service worker y favicon.

Responsabilidad
---------------
Servir el manifiesto y el service worker desde la raíz del sitio para que el
navegador pueda instalarlos con el alcance correcto. Los íconos y el favicon
viven en `static/img`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(tags=["PWA"])

RUTA_ESTATICOS = Path(__file__).resolve().parent.parent / "static"


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifiesto() -> FileResponse:
    """Entrega el manifiesto de instalación.

    Returns:
        Archivo `manifest.webmanifest` con tipo MIME correcto.
    """
    return FileResponse(
        RUTA_ESTATICOS / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    """Entrega el service worker en la raíz del sitio.

    El alcance de un service worker está limitado por su ruta, por eso se sirve
    en `/sw.js` y no bajo `/estaticos`.

    Returns:
        Archivo JavaScript del service worker.
    """
    return FileResponse(RUTA_ESTATICOS / "js" / "sw.js", media_type="application/javascript")


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    """Redirige el favicon clásico al ícono SVG del proyecto.

    Returns:
        Redirección permanente al SVG.
    """
    return RedirectResponse(url="/estaticos/img/favicon.svg", status_code=301)
