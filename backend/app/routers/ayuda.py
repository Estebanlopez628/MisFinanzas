"""Vista «Ayuda y comentarios» del usuario estándar (SRS v2.0, Fase C).

Responsabilidad
---------------
- Mostrar el centro de ayuda, las guías de instalación, las preguntas
  frecuentes, el formulario de reportes y la información legal.
- Alimentar los selectores del formulario con los catálogos públicos del
  servicio de soporte: OLB_BYTE y facturación nunca aparecen aquí.

El envío lo hace la API `POST /feedback` de la Fase A; esta vista solo renderiza.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.core.config import obtener_configuracion
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import feedback

router = APIRouter(tags=["Ayuda"])


@router.get("/ayuda", response_class=HTMLResponse, name="ver_ayuda")
def ver_ayuda(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
) -> HTMLResponse:
    """Renderiza la vista de ayuda, guías y textos legales.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.

    Returns:
        HTML del módulo de ayuda.
    """
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Ayuda y comentarios",
            "version": obtener_configuracion().version,
            "tipos_reporte": feedback.tipos_reporte_para_ui(),
            "modulos": feedback.MODULOS,
        }
    )
    return plantillas.TemplateResponse(request, "ayuda/index.html", contexto)
