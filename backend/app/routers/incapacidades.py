"""Rutas del módulo de incapacidades.

Responsabilidad
---------------
- Servir el formulario de registro.
- Calcular y previsualizar el descuento del mes y el desglose por mes.
- Persistir la incapacidad, listar las registradas y eliminarlas.

SRS v1.5: los días se calculan desde las fechas y cada mes descuenta solo su
tramo. Ya no hay saldos que se arrastren.

El formulario se recalcula en vivo con `static/js/incapacidades.js`; el POST
clásico a `/incapacidades/calcular` sigue disponible como respaldo.
La aritmética vive en `app.servicios.incapacidad`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.core.texto import parsear_monto, parsear_periodo_mes
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, perfiles, registro_incapacidades
from app.servicios.incapacidad import calcular_incapacidad, liquidar_mes_incapacidad

router = APIRouter(tags=["Incapacidades"])

# Campos del formulario; se usan también para repoblarlo tras un error.
CAMPOS_FORMULARIO = ("fecha_inicio", "fecha_fin", "sueldo_basico", "periodo_mes", "numero_incapacidad")


def _valores_del_formulario(formulario: Any) -> dict[str, str]:
    """Extrae y normaliza los campos del formulario.

    Args:
        formulario: `FormData` de Starlette.

    Returns:
        Diccionario ``campo → texto`` listo para repoblar la plantilla.
    """
    return {campo: str(formulario.get(campo, "") or "").strip() for campo in CAMPOS_FORMULARIO}


def _parsear_fecha(texto: str, etiqueta: str, errores: list[str]) -> date | None:
    """Convierte una fecha ISO del formulario, acumulando el error si falla.

    Args:
        texto: Valor del campo (formato ``AAAA-MM-DD``).
        etiqueta: Nombre legible del campo para el mensaje de error.
        errores: Lista compartida donde se agregan los mensajes.

    Returns:
        La fecha convertida o `None` si el valor es inválido.
    """
    if not texto:
        errores.append(f"La {etiqueta} es obligatoria.")
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        errores.append(f"La {etiqueta} no tiene un formato válido (AAAA-MM-DD).")
        return None


def _validar(
    valores: dict[str, str], usuario: UsuarioSesion, bd: Session
) -> tuple[date | None, date | None, Decimal | None, tuple[int, int] | None, list[str]]:
    """Valida los datos del formulario de incapacidades.

    Args:
        valores: Campos normalizados.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Tupla con fecha de inicio, fecha de fin, sueldo, periodo y errores.
    """
    errores: list[str] = []
    fecha_inicio = _parsear_fecha(valores["fecha_inicio"], "fecha de inicio", errores)
    fecha_fin = _parsear_fecha(valores["fecha_fin"], "fecha de fin", errores)

    texto_sueldo = valores["sueldo_basico"]
    if not texto_sueldo:
        perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
        if perfil is not None:
            texto_sueldo = f"{perfil.sueldo_basico:.2f}"
            valores["sueldo_basico"] = texto_sueldo

    sueldo: Decimal | None = None
    if not texto_sueldo:
        errores.append("El sueldo básico es obligatorio. Configúralo en Mi perfil.")
    else:
        try:
            sueldo = parsear_monto(texto_sueldo)
            if sueldo <= Decimal("0"):
                errores.append("El sueldo básico debe ser mayor que cero.")
        except ValueError as error:
            errores.append(str(error))

    periodo: tuple[int, int] | None = None
    if valores["periodo_mes"]:
        try:
            periodo = parsear_periodo_mes(valores["periodo_mes"])
        except ValueError as error:
            errores.append(str(error))

    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        errores.append("La fecha de fin no puede ser anterior a la fecha de inicio.")

    return fecha_inicio, fecha_fin, sueldo, periodo, errores


def _contexto(
    usuario: UsuarioSesion,
    bd: Session,
    valores: dict[str, str],
    *,
    errores: list[str] | None = None,
    resultado: object | None = None,
    liquidacion: object | None = None,
    guardado: bool = False,
) -> dict[str, object]:
    """Construye el contexto de la vista de incapacidades.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        valores: Campos del formulario.
        errores: Errores de validación.
        resultado: Liquidación del mes.
        liquidacion: Cálculo completo del rango.
        guardado: Bandera de éxito del guardado.

    Returns:
        Diccionario para la plantilla.
    """
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Incapacidades",
            "valores": valores,
            "errores": errores or [],
            "resultado": resultado,
            "liquidacion": liquidacion,
            "guardado": guardado,
            "seccion": "incapacidades",
            "perfil": perfiles.obtener_perfil(bd, usuario.id_usuario),
            "incapacidades": registro_incapacidades.listar_incapacidades(
                bd, usuario.id_usuario
            ),
        }
    )
    return contexto


@router.get("/incapacidades", response_class=HTMLResponse, name="ver_incapacidades")
def ver_incapacidades(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra el formulario y las incapacidades registradas.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.

    Returns:
        HTML del formulario.
    """
    valores = {campo: "" for campo in CAMPOS_FORMULARIO}
    perfil = perfiles.obtener_perfil(bd, usuario.id_usuario)
    if perfil is not None:
        valores["sueldo_basico"] = f"{perfil.sueldo_basico:.2f}"
    contexto = _contexto(usuario, bd, valores, guardado=bool(guardado))
    return plantillas.TemplateResponse(request, "incapacidades/index.html", contexto)


@router.post(
    "/incapacidades/calcular",
    response_class=HTMLResponse,
    name="calcular_incapacidad_formulario",
)
async def calcular_incapacidad_formulario(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Valida el formulario y liquida la incapacidad del mes indicado.

    Args:
        request: Petición HTTP con los campos del formulario.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML con el resultado de la liquidación o los errores encontrados.
    """
    formulario = await request.form()
    valores = _valores_del_formulario(formulario)
    fecha_inicio, fecha_fin, sueldo, periodo, errores = _validar(valores, usuario, bd)

    resultado = None
    liquidacion = None
    if not errores and fecha_inicio and fecha_fin and sueldo is not None:
        anio, mes = periodo if periodo is not None else (fecha_inicio.year, fecha_inicio.month)
        resultado = liquidar_mes_incapacidad(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            sueldo_basico=sueldo,
            anio=anio,
            mes=mes,
        )
        liquidacion = calcular_incapacidad(fecha_inicio, fecha_fin, sueldo)

    contexto = _contexto(
        usuario, bd, valores, errores=errores, resultado=resultado, liquidacion=liquidacion
    )
    return plantillas.TemplateResponse(request, "incapacidades/index.html", contexto)


@router.post("/incapacidades/guardar", name="guardar_incapacidad", response_model=None)
async def guardar_incapacidad(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Persiste la incapacidad con su rango de fechas.

    Args:
        request: Petición HTTP con los campos del formulario.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al módulo si se guarda; el formulario con errores en caso
        contrario.
    """
    formulario = await request.form()
    valores = _valores_del_formulario(formulario)
    fecha_inicio, fecha_fin, sueldo, _periodo, errores = _validar(valores, usuario, bd)

    if not errores and fecha_inicio and fecha_fin and sueldo is not None:
        try:
            registro_incapacidades.registrar_incapacidad(
                bd,
                usuario.id_usuario,
                fecha_inicio,
                fecha_fin,
                sueldo,
                valores["numero_incapacidad"] or None,
            )
        except ValueError as error:
            errores.append(str(error))

    if errores:
        contexto = _contexto(usuario, bd, valores, errores=errores)
        return plantillas.TemplateResponse(
            request, "incapacidades/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    auditoria.registrar(
        bd,
        usuario.id_usuario,
        "INCAPACIDAD_GUARDADA",
        "incapacidades",
        f"{fecha_inicio} → {fecha_fin}",
    )
    return RedirectResponse(url="/incapacidades?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/incapacidades/{id_incapacidad}/eliminar", name="eliminar_incapacidad")
def eliminar_incapacidad(
    id_incapacidad: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina una incapacidad y sus saldos heredados del modelo anterior.

    Args:
        id_incapacidad: Incapacidad a eliminar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al módulo.
    """
    if registro_incapacidades.eliminar_incapacidad(
        bd, usuario.id_usuario, id_incapacidad
    ):
        auditoria.registrar(
            bd,
            usuario.id_usuario,
            "INCAPACIDAD_ELIMINADA",
            "incapacidades",
            id_incapacidad,
        )
    return RedirectResponse(url="/incapacidades", status_code=status.HTTP_303_SEE_OTHER)
