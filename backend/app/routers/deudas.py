"""Rutas del módulo "Registro y Detalles de deudas".

Responsabilidad
---------------
- Registrar pasivos con seis datos: acreedor, descripción, saldo, cuota, cuotas
  pendientes y periodicidad.
- Aplicar automáticamente las cuotas vencidas al abrir el módulo.
- Mostrar el plan de amortización de cada deuda y los totales de cartera.

Es un módulo de acceso general: cada usuario ve únicamente sus propias deudas
(SRS v1.2). La aritmética vive en `app.servicios.deudas`; este router solo valida
entradas, invoca el servicio y presenta resultados.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import esquemas
from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.modelos import Deuda
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, deudas

router = APIRouter(tags=["Deudas"])

# SRS v2.0, sección 2.2: rótulo legible del formulario que envió al usuario a
# registrar su deuda. La clave es el valor del parámetro `volver` que ya usaba
# la versión anterior, así que no se rompe ningún enlace existente.
ETIQUETAS_ORIGEN: dict[str, str] = {
    "deducciones": "Deducciones Fijas",
    "finanzas": "Gastos Fijos - Finanzas",
    "trabajos": "Gastos Fijos - Trabajos Extras",
}

# SRS v4.4, sección 7: idempotencia del alta. Un doble clic (o una petición
# reintentada) con el mismo usuario y los mismos valores en menos de diez
# segundos devuelve la deuda ya creada en vez de duplicarla. Es complementaria
# al bloqueo síncrono del botón en `deudas.js`.
VENTANA_IDEMPOTENCIA = 10.0
_ULTIMOS_REGISTROS: dict[tuple[str, tuple[str, ...]], tuple[float, str]] = {}
_BLOQUEO_IDEMPOTENCIA = Lock()


def _clave_idempotencia(id_usuario: str, valores: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Construye la clave del registro reciente.

    Args:
        id_usuario: Dueño de la deuda.
        valores: Campos normalizados del formulario.

    Returns:
        Clave inmutable para la caché de idempotencia.
    """
    return id_usuario, valores


def _deuda_reciente(id_usuario: str, valores: tuple[str, ...]) -> str | None:
    """Devuelve el identificador de una deuda creada hace menos de diez segundos.

    Args:
        id_usuario: Dueño de la deuda.
        valores: Campos normalizados del formulario.

    Returns:
        Identificador de la deuda, o `None` si no hay un registro reciente.
    """
    clave = _clave_idempotencia(id_usuario, valores)
    ahora = time.monotonic()
    with _BLOQUEO_IDEMPOTENCIA:
        registro = _ULTIMOS_REGISTROS.get(clave)
        if registro and ahora - registro[0] <= VENTANA_IDEMPOTENCIA:
            return registro[1]
        if registro:
            _ULTIMOS_REGISTROS.pop(clave, None)
    return None


def _recordar_deuda(id_usuario: str, valores: tuple[str, ...], id_deuda: str) -> None:
    """Guarda el resultado del alta para detectar reintentos.

    Args:
        id_usuario: Dueño de la deuda.
        valores: Campos normalizados del formulario.
        id_deuda: Deuda recién creada.
    """
    clave = _clave_idempotencia(id_usuario, valores)
    with _BLOQUEO_IDEMPOTENCIA:
        # Se descartan las entradas vencidas para que la caché no crezca sin límite.
        ahora = time.monotonic()
        vencidas = [
            clave_antigua
            for clave_antigua, (instante, _) in _ULTIMOS_REGISTROS.items()
            if ahora - instante > VENTANA_IDEMPOTENCIA
        ]
        for clave_antigua in vencidas:
            _ULTIMOS_REGISTROS.pop(clave_antigua, None)
        _ULTIMOS_REGISTROS[clave] = (ahora, id_deuda)


def _contexto(
    usuario: UsuarioSesion,
    bd: Session,
    *,
    error: str | None = None,
    guardado: bool = False,
    aplicadas: int = 0,
    valores: dict[str, str] | None = None,
    volver: str | None = None,
) -> dict[str, object]:
    """Prepara el contexto de la vista de deudas.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error opcional.
        guardado: Bandera de éxito al registrar una deuda.
        aplicadas: Cuotas descontadas automáticamente en esta visita.
        valores: Datos ya escritos en el formulario, para no perderlos al
            corregir un error.
        volver: Módulo de origen de un flujo de vinculación (sección 3.2).

    Returns:
        Diccionario para la plantilla.
    """
    contexto = contexto_base(usuario)
    lista = deudas.listar_deudas(bd, usuario.id_usuario)
    # SRS v1.9: la tabla muestra una fila por deuda, sin calendarios ni bloques
    # de cuotas; las cuotas aplicadas se consultan en el servidor cuando hace falta.
    contexto.update(
        {
            "titulo_pagina": "Registro y Detalles de deudas",
            "deudas": lista,
            "resumen": deudas.resumen_deudas(bd, usuario.id_usuario),
            # SRS v4.4, sección 5.1: columna «Vinculación» de la tabla.
            "vinculaciones": deudas.vinculaciones_de_deudas(bd, usuario.id_usuario),
            "periodicidades": deudas.PERIODICIDADES,
            "error": error,
            "guardado": guardado,
            "aplicadas": aplicadas,
            "valores": valores or {},
            "volver": volver,
            "volver_etiqueta": ETIQUETAS_ORIGEN.get(volver or "", "") if volver else "",
            "deuda_reciente": max(lista, key=lambda deuda: deuda.fecha_creacion) if lista else None,
        }
    )
    return contexto


@router.get("/deudas", response_class=HTMLResponse, name="ver_deudas")
def ver_deudas(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra las deudas, aplica las cuotas vencidas y lista los planes.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito del registro.

    Returns:
        HTML del módulo.
    """
    aplicadas = deudas.aplicar_cuotas_vencidas(bd, usuario.id_usuario)
    return plantillas.TemplateResponse(
        request,
        "deudas/index.html",
        _contexto(
            usuario,
            bd,
            guardado=bool(guardado),
            aplicadas=aplicadas,
            volver=request.query_params.get("volver"),
        ),
    )


@router.get("/api/deudas", name="api_deudas")
def api_deudas(
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> dict[str, object]:
    """Devuelve las deudas con su estado de vinculación (SRS v4.4, sección 5.1).

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Diccionario con la lista ``deudas`` y sus módulos vinculados.
    """
    vinculaciones = deudas.vinculaciones_de_deudas(bd, usuario.id_usuario)
    filas: list[dict[str, object]] = []
    for deuda in deudas.listar_deudas(bd, usuario.id_usuario):
        vinculacion = vinculaciones.get(
            deuda.id_deuda, {"esta_vinculada": False, "modulos_vinculados": []}
        )
        filas.append(
            {
                "id_deuda": deuda.id_deuda,
                "acreedor": deuda.acreedor,
                "descripcion": deuda.descripcion or "",
                "saldo_total": str(deuda.saldo_total),
                "cuota_mensual": str(deuda.cuota_mensual),
                "cuotas_pendientes": deuda.cuotas_pendientes,
                "periodicidad": deuda.periodicidad,
                "estado": deuda.estado,
                "esta_vinculada": vinculacion["esta_vinculada"],
                "modulos_vinculados": vinculacion["modulos_vinculados"],
            }
        )
    return {"deudas": filas}


@router.delete("/api/deudas/{id_deuda}", name="api_eliminar_deuda")
def api_eliminar_deuda(
    id_deuda: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> JSONResponse:
    """Elimina una deuda propia desde el modal de edición (SRS v4.4, sección 5.2).

    Args:
        id_deuda: Deuda a eliminar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        JSON con ``ok`` o un 404 si la deuda no pertenece al usuario.
    """
    if not deudas.eliminar_deuda(bd, usuario.id_usuario, id_deuda):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"ok": False, "detail": "La deuda no existe."},
        )
    auditoria.registrar(bd, usuario.id_usuario, "DEUDA_ELIMINADA", "deudas", id_deuda)
    return JSONResponse(content={"ok": True, "id_deuda": id_deuda})


@router.post("/deudas", name="crear_deuda", response_model=None)
def crear_deuda(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    acreedor: Annotated[str, Form()] = "",
    descripcion: Annotated[str, Form()] = "",
    saldo_total: Annotated[str, Form()] = "",
    cuota: Annotated[str, Form()] = "",
    cuotas_pendientes: Annotated[str, Form()] = "",
    periodicidad: Annotated[str, Form()] = deudas.PERIODICIDAD_MENSUAL,
    volver: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra una deuda con su plan de pagos.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        acreedor: Acreedor.
        descripcion: Detalle.
        saldo_total: Capital pendiente inicial.
        cuota: Valor de cada pago.
        cuotas_pendientes: Número de pagos que faltan.
        periodicidad: `QUINCENAL` o `MENSUAL`.
        volver: Módulo de origen del flujo de vinculación; se conserva en la
            redirección para que el enlace de retorno no desaparezca al guardar.

    Returns:
        Redirección o vista con error.
    """
    try:
        datos = esquemas.validar_formulario(
            esquemas.DeudaNueva,
            acreedor=acreedor,
            descripcion=descripcion,
            saldo_total=saldo_total,
            cuota=cuota,
            cuotas_pendientes=cuotas_pendientes,
            periodicidad=periodicidad,
        )
        # SRS v4.4, sección 7: un reenvío idéntico en menos de diez segundos no
        # crea otra deuda. Se devuelve la misma que ya se había registrado.
        valores_idempotencia = (
            datos.acreedor.strip().lower(),
            (datos.descripcion or "").strip().lower(),
            str(datos.saldo_total),
            str(datos.cuota),
            str(datos.cuotas_pendientes),
            datos.periodicidad,
        )
        anterior = _deuda_reciente(usuario.id_usuario, valores_idempotencia)
        if anterior:
            deuda = bd.get(Deuda, anterior)
            if deuda is not None:
                destino_anterior = (
                    f"/deudas?guardado=1&volver={quote(volver)}" if volver else "/deudas?guardado=1"
                )
                return RedirectResponse(
                    url=destino_anterior, status_code=status.HTTP_303_SEE_OTHER
                )
        deuda = deudas.crear_deuda(
            bd,
            usuario.id_usuario,
            datos.acreedor,
            datos.saldo_total,
            datos.cuota,
            datos.cuotas_pendientes,
            datos.periodicidad,
            datos.descripcion or None,
        )
        _recordar_deuda(usuario.id_usuario, valores_idempotencia, deuda.id_deuda)
        auditoria.registrar(bd, usuario.id_usuario, "DEUDA_CREADA", "deudas", deuda.acreedor)
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "deudas/index.html",
            _contexto(
                usuario,
                bd,
                error=str(error),
                valores={
                    "acreedor": acreedor,
                    "descripcion": descripcion,
                    "saldo_total": saldo_total,
                    "cuota": cuota,
                    "cuotas_pendientes": cuotas_pendientes,
                    "periodicidad": periodicidad,
                },
                volver=volver or None,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    destino = f"/deudas?guardado=1&volver={quote(volver)}" if volver else "/deudas?guardado=1"
    return RedirectResponse(url=destino, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/deudas/{id_deuda}/editar", name="editar_deuda", response_model=None)
def editar_deuda(
    request: Request,
    id_deuda: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    acreedor: Annotated[str, Form()] = "",
    descripcion: Annotated[str, Form()] = "",
    saldo_total: Annotated[str, Form()] = "",
    cuota: Annotated[str, Form()] = "",
    cuotas_pendientes: Annotated[str, Form()] = "",
    periodicidad: Annotated[str, Form()] = deudas.PERIODICIDAD_MENSUAL,
) -> HTMLResponse | RedirectResponse:
    """Corrige el plan de pagos de una deuda propia.

    Args:
        request: Petición HTTP.
        id_deuda: Deuda a modificar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        acreedor: Acreedor.
        descripcion: Detalle.
        saldo_total: Capital pendiente inicial.
        cuota: Valor de cada pago.
        cuotas_pendientes: Número de pagos que faltan.
        periodicidad: `QUINCENAL` o `MENSUAL`.

    Returns:
        Redirección al listado o la vista con el error de validación.
    """
    try:
        datos = esquemas.validar_formulario(
            esquemas.DeudaEditar,
            acreedor=acreedor,
            descripcion=descripcion,
            saldo_total=saldo_total,
            cuota=cuota,
            cuotas_pendientes=cuotas_pendientes,
            periodicidad=periodicidad,
        )
        deuda = deudas.actualizar_deuda(
            bd,
            usuario.id_usuario,
            id_deuda,
            datos.acreedor,
            datos.saldo_total,
            datos.cuota,
            datos.cuotas_pendientes,
            datos.periodicidad,
            datos.descripcion or None,
        )
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "deudas/index.html",
            _contexto(
                usuario,
                bd,
                error=str(error),
                valores={
                    "acreedor": acreedor,
                    "descripcion": descripcion,
                    "saldo_total": saldo_total,
                    "cuota": cuota,
                    "cuotas_pendientes": cuotas_pendientes,
                    "periodicidad": periodicidad,
                },
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if deuda is None:
        return RedirectResponse(
            url=f"/deudas?error={quote('La deuda no existe.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    auditoria.registrar(bd, usuario.id_usuario, "DEUDA_ACTUALIZADA", "deudas", deuda.acreedor)
    return RedirectResponse(url="/deudas?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/deudas/{id_deuda}/eliminar", name="eliminar_deuda")
def eliminar_deuda(
    id_deuda: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> RedirectResponse:
    """Elimina una deuda y sus pagos registrados.

    Args:
        id_deuda: Deuda a eliminar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al listado.
    """
    if deudas.eliminar_deuda(bd, usuario.id_usuario, id_deuda):
        auditoria.registrar(bd, usuario.id_usuario, "DEUDA_ELIMINADA", "deudas", id_deuda)
    return RedirectResponse(url="/deudas", status_code=status.HTTP_303_SEE_OTHER)
