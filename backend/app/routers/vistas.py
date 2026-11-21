"""Rutas de navegación principal y endpoint de salud.

Responsabilidad
---------------
- Renderizar el tablero con las cuatro tarjetas principales (SRS v1.2).
- Servir el endpoint de salud.

La visibilidad de las tarjetas se resuelve en Python, de modo que un
`USER_FINANZAS` nunca recibe el HTML de un módulo privado.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import categorias as catalogo
from app.core.base_datos import obtener_bd
from app.core.config import obtener_configuracion, obtener_parametros
from app.servicios import acceso_google, factura_pdf, feedback
from app.core.texto import (
    formatear_cop,
    formatear_fecha,
    formatear_mes_anio,
    formatear_porcentaje,
)
from app.dependencias import UsuarioSesion, obtener_usuario_actual

RUTA_APP = Path(__file__).resolve().parent.parent
RUTA_PLANTILLAS = RUTA_APP / "templates"

router = APIRouter(tags=["Vistas"])

plantillas = Jinja2Templates(directory=str(RUTA_PLANTILLAS))
# Filtros de presentación reutilizables en todas las plantillas.
plantillas.env.filters["cop"] = formatear_cop
plantillas.env.filters["porcentaje"] = formatear_porcentaje
plantillas.env.filters["fecha_larga"] = formatear_fecha
plantillas.env.filters["mes_anio"] = formatear_mes_anio

# ---------------------------------------------------------------------------
# Tarjetas del dashboard (SRS v1.2, bloque 2): solo los cuatro módulos
# principales. Los submódulos (gastos, historial, incapacidades y chancucos)
# viven dentro de "Mis Finanzas", no como tarjetas externas.
# `solo_admin=True` hace que la tarjeta se omita por completo para los usuarios
# públicos, garantizando que la restricción no dependa del navegador.
# ---------------------------------------------------------------------------
TARJETAS_DASHBOARD: list[dict[str, Any]] = [
    {
        "clave": "finanzas",
        "titulo": "Mis Finanzas",
        "descripcion": "Quincenas, liquidación de nómina, gastos, incapacidades y chancucos.",
        "icono": "💰",
        "url": "/finanzas",
        "solo_autorizados": False,
        "disponible": True,
        "acento": "verde",
    },
    {
        "clave": "olb-byte",
        "titulo": "OLB_BYTE",
        "descripcion": "Inventario, ventas, cartera y abonos de la tienda.",
        "icono": "🛠️",
        "url": "/olb-byte",
        "solo_autorizados": True,
        "disponible": True,
        "acento": "azul",
    },
    {
        "clave": "deudas",
        "titulo": "Registro y Detalles de deudas",
        "descripcion": "Control de pasivos, cuotas y fechas límite.",
        "icono": "📉",
        "url": "/deudas",
        "solo_autorizados": False,
        "disponible": True,
        "acento": "rojo",
    },
    {
        "clave": "trabajos-extras",
        "titulo": "Trabajos Extras",
        "descripcion": "Ingresos independientes por fuera del salario base.",
        "icono": "🚀",
        "url": "/trabajos-extras",
        "solo_autorizados": False,
        "disponible": True,
        "acento": "ambar",
    },
    {
        # SRS v2.0, sección 5.5: tarjeta exclusiva del administrador, al lado
        # de «Trabajos Extras», con contador de solicitudes pendientes.
        "clave": "comentarios",
        "titulo": "Comentarios y Reportes",
        "descripcion": "Gestiona las solicitudes y fallas reportadas por los usuarios.",
        "icono": "📮",
        "url": "/admin/comentarios",
        "solo_autorizados": False,
        "solo_admin": True,
        "disponible": True,
        "acento": "rojo",
    },
]


def iniciales_alias(alias: str | None) -> str:
    """Obtiene las dos iniciales del alias para el avatar de respaldo (SRS v1.8).

    Con dos o más palabras usa la inicial de las dos primeras («Oscar Lopez» → «OL»).
    Con una sola palabra usa sus dos primeras letras («ana» → «AN»).

    Args:
        alias: Apodo del usuario.

    Returns:
        Hasta dos letras en mayúsculas; cadena vacía si el alias no tiene letras.
    """
    palabras = (alias or "").split()
    if len(palabras) >= 2:
        return (palabras[0][0] + palabras[1][0]).upper()
    if palabras:
        return palabras[0][:2].upper()
    return ""


plantillas.env.filters["iniciales"] = iniciales_alias


def contexto_base(usuario: UsuarioSesion | None) -> dict[str, Any]:
    """Construye el contexto común a todas las plantillas.

    Args:
        usuario: Usuario autenticado o `None` en las pantallas públicas
            (login y registro).

    Returns:
        Diccionario con usuario, configuración, parámetros y año actual.
    """
    configuracion = obtener_configuracion()
    return {
        "usuario": usuario,
        "configuracion": configuracion,
        "parametros": obtener_parametros(),
        "anio_actual": date.today().year,
        # Catálogo cerrado de ocho categorías: el selector de los formularios y
        # la leyenda de la dona leen los mismos nombres y colores del backend.
        "categorias": catalogo.lista_categorias(),
        "google_activo": acceso_google.google_activo(),
        # Apoyo voluntario: solo el QR de Bre-B (data URI). No se expone ningún número.
        "cafe": {
            "monto": "$6.000 COP",
            "qr_bre_b": factura_pdf.logo_como_data_uri("bre_b_qr"),
        },
    }


@router.get("/salud", tags=["Sistema"], response_model=None)
def verificar_salud(bd: Session = Depends(obtener_bd)) -> dict[str, str] | JSONResponse:
    """Endpoint de salud para monitoreo y despliegue, con consulta a la base.

    Ejecuta `SELECT 1` contra la base activa (Neon en producción). Responde 200 si
    la base contesta y 503 si no, para que el proveedor no envíe tráfico a una
    instancia sin base de datos.

    Args:
        bd: Sesión de base de datos de la petición.

    Returns:
        Estado de la aplicación y de la base en JSON, o 503 si la base no responde.
    """
    try:
        bd.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503, content={"estado": "error", "base_datos": "no disponible"}
        )
    return {"estado": "ok", "base_datos": "ok", "servicio": obtener_configuracion().nombre}


@router.get("/", response_class=HTMLResponse, name="ver_dashboard")
def ver_dashboard(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Renderiza el tablero principal con las tarjetas permitidas por rol.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado de la petición.
        bd: Sesión de base de datos.
        guardado: Bandera de la URL que confirma el onboarding.

    Returns:
        HTML del dashboard.
    """
    tarjetas_visibles = [
        tarjeta
        for tarjeta in TARJETAS_DASHBOARD
        if (usuario.puede_ver_olb_byte or not tarjeta["solo_autorizados"])
        and (not tarjeta.get("solo_admin") or usuario.es_administrador)
    ]

    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Panel principal",
            "tarjetas": tarjetas_visibles,
            "guardado": bool(guardado),
            # Contador del badge circular de la tarjeta administrativa.
            "comentarios_pendientes": feedback.contar_pendientes(bd),
        }
    )
    return plantillas.TemplateResponse(request, "dashboard.html", contexto)
