"""Rutas del presupuesto de gastos.

Responsabilidad
---------------
Registrar gastos fijos y variables, listarlos, mostrar el total del mes y
eliminarlos. El módulo complementa la nómina: el saldo del bolsillo menos los
gastos es el dinero realmente disponible.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, obtener_usuario_actual
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, gastos, pagos_metas, perfiles

router = APIRouter(tags=["Gastos"])


def _etiquetas_quincena(bd: Session, id_usuario: str) -> dict[int, str]:
    """Obtiene los rótulos «Quincena N · día X» del perfil del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil.

    Returns:
        Diccionario con la etiqueta de la quincena 1 y de la quincena 2.
    """
    return perfiles.etiquetas_quincena(perfiles.obtener_perfil(bd, id_usuario))


def _parsear_fecha(texto: str) -> date:
    """Convierte la fecha del formulario o devuelve la de hoy.

    Args:
        texto: Valor ``AAAA-MM-DD``; puede venir vacío.

    Returns:
        Fecha válida.

    Raises:
        ValueError: Si el texto no es una fecha ISO.
    """
    if not texto.strip():
        return date.today()
    return date.fromisoformat(texto.strip())


@router.get("/gastos", response_class=HTMLResponse, name="ver_gastos")
def ver_gastos(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra el presupuesto y el formulario de gastos.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.

    Returns:
        HTML del módulo.
    """
    hoy = date.today()
    pagos_metas.asegurar_gastos_de_metas(bd, usuario.id_usuario, hoy.year, hoy.month)
    lista = gastos.listar_gastos(bd, usuario.id_usuario)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Gastos",
            "gastos": lista,
            "resumen": gastos.resumen_por_categoria(bd, usuario.id_usuario),
            "total_mes": gastos.total_gastos_mes(bd, usuario.id_usuario, hoy.year, hoy.month),
            "fecha_hoy": hoy.isoformat(),
            "guardado": bool(guardado),
            "seccion": "gastos",
            "etiquetas_quincena": _etiquetas_quincena(bd, usuario.id_usuario),
        }
    )
    return plantillas.TemplateResponse(request, "gastos/index.html", contexto)


@router.post("/gastos", name="crear_gasto", response_model=None)
def crear_gasto(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    categoria: Annotated[str, Form()] = "",
    descripcion: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
    fecha: Annotated[str, Form()] = "",
    es_fijo: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "",
    origen: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra un gasto.

    Args:
        request: Petición HTTP.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        categoria: Categoría del gasto.
        descripcion: Detalle.
        valor: Monto.
        fecha: Fecha ISO; si falta se usa hoy.
        es_fijo: ``1`` si es recurrente.
        quincena: ``1`` o ``2`` para gastos fijos de una quincena.
        origen: ``finanzas`` cuando el formulario vive en "Mis Finanzas"; en ese
            caso se vuelve al panel de quincenas tras guardar.

    Returns:
        Redirección al listado o a Mis Finanzas, o la vista con el error.
    """
    try:
        gasto = gastos.crear_gasto(
            bd,
            usuario.id_usuario,
            categoria,
            descripcion,
            valor,
            _parsear_fecha(fecha),
            es_fijo=es_fijo == "1",
            quincena=quincena,
        )
        auditoria.registrar(
            bd, usuario.id_usuario, "GASTO_CREADO", "gastos", gasto.descripcion
        )
    except (ValueError, ArithmeticError) as error:
        if origen == "finanzas":
            return RedirectResponse(
                url=f"/finanzas?error_gasto={quote(str(error))}#quincenas",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if origen == "trabajos":
            return RedirectResponse(
                url=f"/trabajos-extras?error={quote(str(error))}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        hoy = date.today()
        contexto = contexto_base(usuario)
        contexto.update(
            {
                "titulo_pagina": "Gastos",
                "gastos": gastos.listar_gastos(bd, usuario.id_usuario),
                "resumen": gastos.resumen_por_categoria(bd, usuario.id_usuario),
                "total_mes": gastos.total_gastos_mes(
                    bd, usuario.id_usuario, hoy.year, hoy.month
                ),
                "fecha_hoy": hoy.isoformat(),
                "guardado": False,
                "seccion": "gastos",
                "error": str(error),
                "etiquetas_quincena": _etiquetas_quincena(bd, usuario.id_usuario),
            }
        )
        return plantillas.TemplateResponse(
            request, "gastos/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    if origen == "finanzas":
        return RedirectResponse(
            url="/finanzas?guardado_gasto=1#quincenas",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if origen == "trabajos":
        return RedirectResponse(
            url="/trabajos-extras?guardado_gasto=1", status_code=status.HTTP_303_SEE_OTHER
        )
    return RedirectResponse(url="/gastos?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/gastos/{id_gasto}/editar", name="editar_gasto", response_model=None)
def editar_gasto(
    request: Request,
    id_gasto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    descripcion: Annotated[str, Form()] = "",
    valor: Annotated[str, Form()] = "",
    categoria: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "",
    origen: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Actualiza el valor o la descripción de un gasto ya registrado.

    La SRS v1.3 exige poder corregir un gasto fijo sin eliminarlo, porque los
    recibos de servicios cambian mes a mes y el saldo de la quincena debe
    recalcularse con el monto nuevo.

    Args:
        request: Petición HTTP.
        id_gasto: Identificador del gasto a modificar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        descripcion: Nuevo detalle legible.
        valor: Nuevo monto en pesos.
        categoria: Categoría nueva; si llega vacía se conserva la actual.
        quincena: `1` o `2` para la quincena del gasto; vacío para el mes completo.
        origen: ``finanzas`` cuando el formulario vive en "Mis Finanzas"; en ese
            caso se vuelve al panel de quincenas tras guardar.

    Returns:
        Redirección al listado o a Mis Finanzas, o la vista con el error.
    """
    try:
        gasto = gastos.actualizar_gasto(
            bd,
            usuario.id_usuario,
            id_gasto,
            descripcion,
            valor,
            categoria=categoria or None,
            quincena=quincena,
        )
    except (ValueError, ArithmeticError) as error:
        if origen == "finanzas":
            return RedirectResponse(
                url=f"/finanzas?error_gasto={quote(str(error))}#quincenas",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if origen == "trabajos":
            return RedirectResponse(
                url=f"/trabajos-extras?error={quote(str(error))}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        hoy = date.today()
        contexto = contexto_base(usuario)
        contexto.update(
            {
                "titulo_pagina": "Gastos",
                "gastos": gastos.listar_gastos(bd, usuario.id_usuario),
                "resumen": gastos.resumen_por_categoria(bd, usuario.id_usuario),
                "total_mes": gastos.total_gastos_mes(
                    bd, usuario.id_usuario, hoy.year, hoy.month
                ),
                "fecha_hoy": hoy.isoformat(),
                "guardado": False,
                "seccion": "gastos",
                "error": str(error),
                "etiquetas_quincena": _etiquetas_quincena(bd, usuario.id_usuario),
            }
        )
        return plantillas.TemplateResponse(
            request, "gastos/index.html", contexto, status_code=status.HTTP_400_BAD_REQUEST
        )

    if gasto is None:
        # El gasto no existe o pertenece a otro usuario: se responde igual que
        # un listado vacío para no revelar información ajena.
        if origen == "finanzas":
            return RedirectResponse(
                url="/finanzas?error_gasto=El%20gasto%20no%20existe.#quincenas",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(url="/gastos", status_code=status.HTTP_303_SEE_OTHER)

    pagos_metas.propagar_valor(bd, gasto)
    auditoria.registrar(
        bd, usuario.id_usuario, "GASTO_ACTUALIZADO", "gastos", gasto.descripcion
    )

    if origen == "finanzas":
        return RedirectResponse(
            url="/finanzas?guardado_gasto=1#quincenas",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if origen == "trabajos":
        return RedirectResponse(
            url="/trabajos-extras?guardado=1", status_code=status.HTTP_303_SEE_OTHER
        )
    return RedirectResponse(url="/gastos?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


def _volver(origen: str) -> RedirectResponse:
    """Redirige al panel de origen tras una acción sobre pagos.

    Args:
        origen: ``finanzas`` para volver a Mis Finanzas, ``trabajos`` para
            volver a Trabajos Extras; cualquier otro valor vuelve al listado de
            gastos.

    Returns:
        Redirección 303 al destino.
    """
    if origen == "finanzas":
        return RedirectResponse(url="/finanzas#quincenas", status_code=status.HTTP_303_SEE_OTHER)
    if origen == "trabajos":
        return RedirectResponse(
            url="/trabajos-extras", status_code=status.HTTP_303_SEE_OTHER
        )
    return RedirectResponse(url="/gastos", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/gastos/{id_gasto}/eliminar", name="eliminar_gasto")
def eliminar_gasto(
    id_gasto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Quita un gasto fijo con la × según sea manual o de una meta.

    Un gasto manual se elimina. Un gasto de meta se inhabilita en su quincena
    durante 8 días y su pago se retira; la meta se conserva (SRS v1.6).

    Args:
        id_gasto: Identificador del gasto.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        origen: ``finanzas`` cuando la acción se lanza desde el panel de
            quincenas; en ese caso se vuelve allí.

    Returns:
        Redirección al listado correspondiente.
    """
    hoy = date.today()
    accion = pagos_metas.quitar_gasto(bd, usuario.id_usuario, id_gasto, hoy)
    if accion == pagos_metas.ACCION_INHABILITADO:
        auditoria.registrar(bd, usuario.id_usuario, "PAGO_INHABILITADO", "gastos", id_gasto)
    elif accion == pagos_metas.ACCION_ELIMINADO:
        auditoria.registrar(bd, usuario.id_usuario, "GASTO_ELIMINADO", "gastos", id_gasto)
    return _volver(origen)


@router.post("/gastos/{id_gasto}/pagado", name="marcar_pagado_gasto")
def marcar_pagado_gasto(
    id_gasto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Marca el ✔ de un gasto fijo, registrando su pago y su abono de meta.

    Args:
        id_gasto: Gasto a marcar.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        origen: ``finanzas`` para volver al panel de quincenas.

    Returns:
        Redirección al panel de origen.
    """
    try:
        gasto = pagos_metas.marcar_pagado(bd, usuario.id_usuario, id_gasto, date.today())
    except ValueError:
        return _volver(origen)
    if gasto is not None:
        auditoria.registrar(bd, usuario.id_usuario, "GASTO_PAGADO", "gastos", id_gasto)
    return _volver(origen)


@router.post("/gastos/{id_gasto}/no-pagado", name="desmarcar_pagado_gasto")
def desmarcar_pagado_gasto(
    id_gasto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Quita el ✔ de un gasto fijo y revierte su pago (SRS v1.7).

    El gasto vuelve a restar en su quincena y su abono de meta se recalcula. Es
    la corrección de un check marcado por error, distinta del borrado masivo,
    que conserva los pagos.

    Args:
        id_gasto: Gasto marcado por error.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        origen: ``finanzas`` para volver al panel de quincenas.

    Returns:
        Redirección al panel de origen.
    """
    gasto = pagos_metas.desmarcar_pagado(bd, usuario.id_usuario, id_gasto)
    if gasto is not None:
        auditoria.registrar(
            bd, usuario.id_usuario, "GASTO_DESMARCADO", "gastos", id_gasto
        )
    return _volver(origen)


@router.post("/gastos/{id_gasto}/abono", name="registrar_abono_gasto")
def registrar_abono_gasto(
    id_gasto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    valor: Annotated[str, Form()] = "",
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Registra un abono manual en un pago saltado de una meta (SRS v1.6).

    Args:
        id_gasto: Gasto saltado con ×.
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        valor: Monto que se abona.
        origen: ``finanzas`` para volver al panel de quincenas.

    Returns:
        Redirección al panel de origen; si hay error, se muestra en el panel.
    """
    try:
        gasto = pagos_metas.registrar_abono_manual(
            bd, usuario.id_usuario, id_gasto, valor, date.today()
        )
    except ValueError as error:
        if origen == "finanzas":
            return RedirectResponse(
                url=f"/finanzas?error_gasto={quote(str(error))}#quincenas",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return _volver(origen)
    if gasto is not None:
        auditoria.registrar(bd, usuario.id_usuario, "ABONO_MANUAL", "gastos", id_gasto)
    return _volver(origen)


@router.post("/gastos/limpiar-pagos", name="limpiar_pagos_gastos")
def limpiar_pagos_gastos(
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    anio: Annotated[str, Form()] = "",
    mes: Annotated[str, Form()] = "",
    quincena: Annotated[str, Form()] = "0",
    origen: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Oculta los checks de una quincena; los pagos registrados se conservan.

    Args:
        usuario: Usuario autenticado.
        bd: Sesión de base de datos.
        anio: Año del periodo visible.
        mes: Mes del periodo visible.
        quincena: `1` o `2` para una quincena; `0` para limpiar todo el mes.
        origen: ``finanzas`` para volver al panel de quincenas.

    Returns:
        Redirección al panel de origen.
    """
    hoy = date.today()
    try:
        numero_anio = int(anio) if anio else hoy.year
        numero_mes = int(mes) if mes else hoy.month
        numero_quincena = int(quincena) if quincena else 0
    except ValueError:
        return _volver(origen)
    if numero_quincena not in (0, 1, 2) or not 1 <= numero_mes <= 12:
        return _volver(origen)

    limpiados = pagos_metas.limpiar_checks(
        bd, usuario.id_usuario, numero_anio, numero_mes, numero_quincena
    )
    if limpiados:
        auditoria.registrar(
            bd,
            usuario.id_usuario,
            "CHECKS_LIMPIADOS",
            "gastos",
            f"{numero_anio}-{numero_mes} quincena {numero_quincena}",
        )
    return _volver(origen)
