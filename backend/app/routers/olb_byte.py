"""Módulo comercial OLB_BYTE: ventas a crédito, cobros, anulaciones y factura.

Responsabilidad
---------------
Servir el panel operativo de la tienda y traducir los formularios a llamadas de
`servicios.comercial`. El formulario de venta envía listas paralelas (una entrada
por producto) para admitir varias filas sin JavaScript de cálculo. Incluye la
factura imprimible y los enlaces de WhatsApp.

El catálogo de productos y el control de stock ya no existen (ADR-35): cada
producto se escribe en la venta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, exigir_administrador, obtener_usuario_actual
from app.modelos import Cliente, Venta, VentaDetalle
from app.routers.vistas import contexto_base, plantillas
from app.servicios import analitica, auditoria, comercial, factura_pdf

router = APIRouter(tags=["OLB_BYTE"])

CAMPOS_LINEA = (
    "producto_nombre",
    "referencia",
    "cantidad",
    "costo_unitario",
    "precio_unitario",
    "garantia_meses",
)


@dataclass(frozen=True)
class DetalleVenta:
    """Fila de detalle lista para plantillas y facturas.

    Attributes:
        nombre: Nombre del producto tal como se vendió.
        referencia: Modelo o referencia.
        cantidad: Unidades vendidas.
        precio_unitario: Precio aplicado.
        subtotal: Precio por cantidad.
        garantia_texto: Garantía de la línea.
    """

    nombre: str
    referencia: str | None
    cantidad: int
    precio_unitario: object
    subtotal: object
    garantia_texto: str | None


def _detalle_de_venta(bd: Session, id_venta: str) -> list[DetalleVenta]:
    """Recupera las líneas de una venta con los datos guardados en la orden.

    Args:
        bd: Sesión de base de datos.
        id_venta: Venta consultada.

    Returns:
        Lista de detalles.
    """
    detalles = bd.scalars(select(VentaDetalle).where(VentaDetalle.id_venta == id_venta)).all()
    return [
        DetalleVenta(
            nombre=detalle.producto_nombre,
            referencia=detalle.referencia,
            cantidad=detalle.cantidad,
            precio_unitario=detalle.precio_unitario,
            subtotal=detalle.subtotal_item,
            garantia_texto=detalle.garantia_texto,
        )
        for detalle in detalles
    ]


def _filas_del_formulario(formulario) -> list[dict[str, str]]:
    """Lee las filas de producto tal como se escribieron en el formulario.

    Una fila en la que el usuario no escribió producto, referencia, costo ni precio
    se ignora: la cantidad y la garantía siempre traen un valor por defecto y no
    cuentan como datos.

    Args:
        formulario: Datos del formulario ya leídos.

    Returns:
        Filas con los campos de `CAMPOS_LINEA` como texto.
    """
    columnas = {campo: formulario.getlist(campo) for campo in CAMPOS_LINEA}
    filas: list[dict[str, str]] = []
    for indice in range(len(columnas["producto_nombre"])):
        fila = {
            campo: str(columnas[campo][indice]).strip() if indice < len(columnas[campo]) else ""
            for campo in CAMPOS_LINEA
        }
        if any(fila[campo] for campo in ("producto_nombre", "referencia", "costo_unitario", "precio_unitario")):
            filas.append(fila)
    return filas


def _lineas_desde_filas(filas: list[dict[str, str]]) -> list[comercial.LineaVenta]:
    """Convierte las filas escritas en líneas de venta para el servicio.

    Args:
        filas: Filas leídas con `_filas_del_formulario`.

    Returns:
        Líneas listas para `registrar_venta`.

    Raises:
        ValueError: Si la cantidad o los meses de garantía no son números enteros,
            o si falta el precio de un producto.
    """
    lineas: list[comercial.LineaVenta] = []
    for fila in filas:
        nombre = fila["producto_nombre"] or "(sin nombre)"
        try:
            cantidad = int(fila["cantidad"] or "0")
        except ValueError as error:
            raise ValueError(f"La cantidad de {nombre} debe ser un número entero.") from error
        if not fila["precio_unitario"]:
            raise ValueError(f"Escribe el precio de venta de {nombre}.")
        try:
            meses = (
                int(fila["garantia_meses"])
                if fila["garantia_meses"]
                else comercial.GARANTIA_MESES_DEFECTO
            )
        except ValueError as error:
            raise ValueError(f"La garantía de {nombre} debe ser un número de meses.") from error
        lineas.append(
            comercial.LineaVenta(
                nombre=fila["producto_nombre"],
                cantidad=cantidad,
                precio_unitario=fila["precio_unitario"],
                costo_unitario=fila["costo_unitario"] or "0",
                referencia=fila["referencia"] or None,
                garantia_meses=meses,
            )
        )
    return lineas


def _contexto(
    usuario: UsuarioSesion,
    bd: Session,
    *,
    error: str | None = None,
    guardado: bool = False,
    borrador: dict[str, object] | None = None,
) -> dict[str, object]:
    """Prepara el contexto del panel comercial.

    Args:
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error opcional.
        guardado: Bandera de éxito.
        borrador: Datos del formulario de venta para repoblarlo tras un error.

    Returns:
        Diccionario para la plantilla.
    """
    hoy = datetime.now(comercial.ZONA_TIENDA).date()
    ventas = comercial.listar_ventas(bd)
    clientes = comercial.listar_clientes(bd)
    ventas_info = []
    for venta in ventas:
        lineas = _detalle_de_venta(bd, venta.id_venta)
        semaforo, dias = comercial.estado_garantia(venta, hoy)
        ventas_info.append(
            {
                "venta": venta,
                "lineas": lineas,
                "enlace_whatsapp": comercial.enlace_whatsapp_factura(
                    venta,
                    [
                        {
                            "nombre": linea.nombre,
                            "cantidad": linea.cantidad,
                            "subtotal": linea.subtotal,
                        }
                        for linea in lineas
                    ],
                ),
                "semaforo": semaforo,
                "dias_garantia": dias,
                "pendiente_devolver": comercial.pendiente_devolver(bd, venta),
            }
        )

    cartera = comercial.resumen_cartera(bd)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "OLB_BYTE",
            "clientes": clientes,
            "ventas": ventas_info,
            "pendientes_total": len(comercial.cartera(bd)),
            "resumen": cartera,
            "total_ventas": sum((v.total for v in ventas if v.estado_orden == comercial.ESTADO_ACTIVA), start=0),
            "numero_ventas": sum(1 for v in ventas if v.estado_orden == comercial.ESTADO_ACTIVA),
            "metodos_pago": comercial.METODOS_PAGO,
            "error": error,
            "guardado": guardado,
            "borrador": borrador,
            "meses_defecto": comercial.GARANTIA_MESES_DEFECTO,
        }
    )
    return contexto


def _contexto_pendientes(
    usuario: UsuarioSesion,
    bd: Session,
    *,
    q: str = "",
    error: str | None = None,
) -> dict[str, object]:
    """Prepara la vista filtrada de clientes pendientes de pago (RF-06).

    Args:
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        q: Texto de búsqueda por cliente, celular o número de orden.
        error: Mensaje de error opcional.

    Returns:
        Diccionario para la plantilla, con cada orden, sus abonos y el enlace de cobro.
    """
    pendientes = []
    for venta in comercial.buscar_cartera(bd, q):
        abonos = comercial.abonos_de_venta(bd, venta.id_venta)
        pendientes.append(
            {
                "venta": venta,
                "abonos": abonos,
                "ultimo_abono": abonos[-1] if abonos else None,
                "enlace_cobro": comercial.enlace_whatsapp_cobro(venta),
            }
        )
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Pendientes de pago · OLB_BYTE",
            "pendientes": pendientes,
            "q": q,
            "metodos_pago": comercial.METODOS_PAGO,
            "error": error,
        }
    )
    return contexto


def _pagina_con_error(
    request: Request,
    bd: Session,
    usuario: UsuarioSesion,
    error: str,
    borrador: dict[str, object] | None = None,
) -> HTMLResponse:
    """Vuelve a mostrar el panel con un error y descarta cambios a medias.

    Args:
        request: Petición HTTP.
        bd: Sesión de base de datos.
        usuario: Administrador autenticado.
        error: Mensaje para el usuario.
        borrador: Datos del formulario para repoblarlo.

    Returns:
        Panel con código 400.
    """
    bd.rollback()
    return plantillas.TemplateResponse(
        request,
        "olb_byte/index.html",
        _contexto(usuario, bd, error=error, borrador=borrador),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/olb-byte", response_class=HTMLResponse, name="ver_olb_byte")
def ver_olb_byte(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra el panel comercial.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.

    Returns:
        HTML del panel.

    Raises:
        HTTPException: 403 si el usuario no es administrador.
    """
    exigir_administrador(usuario)
    return plantillas.TemplateResponse(
        request, "olb_byte/index.html", _contexto(usuario, bd, guardado=bool(guardado))
    )


@router.post("/olb-byte/clientes", name="crear_cliente", response_model=None)
def crear_cliente(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    nombre: Annotated[str, Form()] = "",
    telefono_whatsapp: Annotated[str, Form()] = "",
    correo: Annotated[str, Form()] = "",
    direccion: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra un cliente desde la agenda de administración.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        nombre: Nombre del cliente.
        telefono_whatsapp: Celular de 10 dígitos.
        correo: Correo.
        direccion: Dirección.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    try:
        cliente = comercial.registrar_cliente(
            bd, nombre, telefono_whatsapp or None, correo or None, direccion or None
        )
        auditoria.registrar(bd, usuario.id_usuario, "CLIENTE_CREADO", "clientes", cliente.nombre)
    except ValueError as error:
        return _pagina_con_error(request, bd, usuario, str(error))
    return RedirectResponse(url="/olb-byte?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/olb-byte/ventas", name="registrar_venta", response_model=None)
async def registrar_venta(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Registra una orden de venta con una o varias líneas.

    Args:
        request: Petición HTTP con el formulario.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección al panel o vista con error y datos repoblados.
    """
    exigir_administrador(usuario)
    formulario = await request.form()
    cliente_nombre = str(formulario.get("cliente_nombre", "")).strip()
    cliente_telefono = str(formulario.get("cliente_telefono", "")).strip()
    borrador: dict[str, object] = {
        "cliente_nombre": cliente_nombre,
        "cliente_telefono": cliente_telefono,
    }
    filas = _filas_del_formulario(formulario)
    borrador["filas"] = filas
    try:
        lineas = _lineas_desde_filas(filas)
        venta = comercial.registrar_venta(bd, cliente_nombre, cliente_telefono or None, lineas)
        auditoria.registrar(
            bd, usuario.id_usuario, "VENTA_REGISTRADA", "ventas", f"No. {venta.numero_orden}"
        )
    except (ValueError, ArithmeticError) as error:
        return _pagina_con_error(request, bd, usuario, str(error), borrador)
    return RedirectResponse(url="/olb-byte?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/olb-byte/ventas/{id_venta}/abonos", name="registrar_abono", response_model=None)
def registrar_abono(
    request: Request,
    id_venta: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    monto: Annotated[str, Form()] = "",
    metodo_pago: Annotated[str, Form()] = "EFECTIVO",
    fecha_abono: Annotated[str, Form()] = "",
    q: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Aplica un abono a una orden activa y muestra su recibo.

    Args:
        request: Petición HTTP.
        id_venta: Orden abonada.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        monto: Dinero recibido.
        metodo_pago: `EFECTIVO` o `TRANSFERENCIA`.
        fecha_abono: Fecha y hora del pago (`AAAA-MM-DDTHH:MM`); vacía significa ahora.
        q: Filtro de la vista de pendientes desde la que se cobró.

    Returns:
        Redirección al recibo del abono, o la vista de pendientes con el error.
    """
    exigir_administrador(usuario)
    try:
        momento = (
            datetime.fromisoformat(fecha_abono).replace(tzinfo=comercial.ZONA_TIENDA)
            if fecha_abono.strip()
            else None
        )
        abono = comercial.registrar_abono(bd, id_venta, monto, metodo_pago, momento)
        auditoria.registrar(bd, usuario.id_usuario, "ABONO_REGISTRADO", "abonos", abono.id_abono)
    except (ValueError, ArithmeticError) as error:
        bd.rollback()
        return plantillas.TemplateResponse(
            request,
            "olb_byte/pendientes.html",
            _contexto_pendientes(usuario, bd, q=q, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        url=f"/olb-byte/recibos/{abono.id_abono}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/olb-byte/pendientes", response_class=HTMLResponse, name="ver_pendientes")
def ver_pendientes(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    q: str = "",
) -> HTMLResponse:
    """Muestra los clientes con saldo pendiente, con búsqueda (RF-06).

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        q: Texto a buscar por cliente, celular o número de orden.

    Returns:
        HTML de la vista de pendientes.
    """
    exigir_administrador(usuario)
    return plantillas.TemplateResponse(
        request, "olb_byte/pendientes.html", _contexto_pendientes(usuario, bd, q=q)
    )


@router.get("/olb-byte/recibos/{id_abono}", response_class=HTMLResponse, name="ver_recibo")
def ver_recibo(
    request: Request,
    id_abono: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Muestra el recibo compacto de un abono, listo para compartir (RF-07).

    Args:
        request: Petición HTTP.
        id_abono: Abono del recibo.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML del recibo.

    Raises:
        HTTPException: 403 si el usuario no es administrador; 404 si el abono no existe.
    """
    exigir_administrador(usuario)
    abono = comercial.obtener_abono(bd, id_abono)
    if abono is None:
        raise HTTPException(status_code=404, detail="Recibo no encontrado.")
    venta = comercial.obtener_venta(bd, abono.id_venta)
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")

    abonos = comercial.abonos_de_venta(bd, venta.id_venta)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": f"Recibo de abono · No. {venta.numero_orden}",
            "abono": abono,
            "venta": venta,
            "abonos": abonos,
            "saldada": venta.saldo_pendiente <= 0,
            "enlace_whatsapp": comercial.enlace_whatsapp_recibo(venta, abono),
        }
    )
    return plantillas.TemplateResponse(request, "olb_byte/recibo.html", contexto)


@router.post("/olb-byte/ventas/{id_venta}/anular", name="anular_venta", response_model=None)
def anular_venta(
    request: Request,
    id_venta: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    motivo: Annotated[str, Form()] = "",
    monto_devuelto: Annotated[str, Form()] = "",
    metodo_devolucion: Annotated[str, Form()] = "EFECTIVO",
) -> HTMLResponse | RedirectResponse:
    """Anula una orden con motivo y devuelve el dinero si corresponde.

    Args:
        request: Petición HTTP.
        id_venta: Orden a anular.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        motivo: Razón de la anulación.
        monto_devuelto: Dinero devuelto ahora al cliente; vacío es cero.
        metodo_devolucion: `EFECTIVO` o `TRANSFERENCIA`.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    try:
        comercial.anular_venta(
            bd, id_venta, motivo, monto_devuelto or "0", metodo_devolucion
        )
        auditoria.registrar(bd, usuario.id_usuario, "VENTA_ANULADA", "ventas", id_venta)
    except (ValueError, ArithmeticError) as error:
        return _pagina_con_error(request, bd, usuario, str(error))
    return RedirectResponse(url="/olb-byte?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/olb-byte/ventas/{id_venta}/devolucion", name="registrar_devolucion", response_model=None)
def registrar_devolucion(
    request: Request,
    id_venta: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    monto: Annotated[str, Form()] = "",
    metodo_pago: Annotated[str, Form()] = "EFECTIVO",
) -> HTMLResponse | RedirectResponse:
    """Registra una devolución pendiente de una orden anulada.

    Args:
        request: Petición HTTP.
        id_venta: Orden anulada.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        monto: Dinero devuelto.
        metodo_pago: `EFECTIVO` o `TRANSFERENCIA`.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    try:
        comercial.registrar_devolucion(bd, id_venta, monto, metodo_pago)
        auditoria.registrar(bd, usuario.id_usuario, "DEVOLUCION_REGISTRADA", "ventas", id_venta)
    except (ValueError, ArithmeticError) as error:
        return _pagina_con_error(request, bd, usuario, str(error))
    return RedirectResponse(url="/olb-byte?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/olb-byte/factura/{id_venta}", response_class=HTMLResponse, name="ver_factura")
def ver_factura(
    request: Request,
    id_venta: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Muestra la factura imprimible de una orden.

    Args:
        request: Petición HTTP.
        id_venta: Orden facturada.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML de la factura.

    Raises:
        HTTPException: 403 si el usuario no es administrador; 404 si la orden no existe.
    """
    exigir_administrador(usuario)
    venta: Venta | None = comercial.obtener_venta(bd, id_venta)
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")

    cliente: Cliente | None = bd.get(Cliente, venta.id_cliente)
    lineas = _detalle_de_venta(bd, id_venta)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": f"Factura No. {venta.numero_orden}",
            "venta": venta,
            "nombre_archivo": factura_pdf.nombre_archivo(venta.numero_orden, venta.cliente_nombre),
            "cliente": cliente,
            "lineas": lineas,
            "total": venta.total,
            "enlace_whatsapp": comercial.enlace_whatsapp_factura(
                venta,
                [
                    {
                        "nombre": linea.nombre,
                        "cantidad": linea.cantidad,
                        "subtotal": linea.subtotal,
                    }
                    for linea in lineas
                ],
            ),
        }
    )
    return plantillas.TemplateResponse(request, "olb_byte/factura.html", contexto)


def _contexto_cartera(usuario: UsuarioSesion, bd: Session, *, error: str | None = None) -> dict[str, object]:
    """Prepara la vista de cartera, liquidez y deuda con el proveedor (RF-08 a RF-11).

    Args:
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error opcional.

    Returns:
        Diccionario para la plantilla.
    """
    resumen = comercial.resumen_cartera(bd)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Cartera y liquidez · OLB_BYTE",
            "filas_balance": comercial.tabla_balance(resumen),
            "segmentos": comercial.segmentos_dona(resumen["cartera_clientes"], resumen["deuda_proveedor"]),
            "movimientos": comercial.listar_movimientos_proveedor(bd),
            "deuda": resumen["deuda_proveedor"],
            "error": error,
        }
    )
    return contexto


@router.get("/olb-byte/cartera", response_class=HTMLResponse, name="ver_cartera")
def ver_cartera(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra el balance de cartera, la gráfica y el libro del proveedor.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito tras registrar un pago.

    Returns:
        HTML de la vista de cartera.
    """
    exigir_administrador(usuario)
    contexto = _contexto_cartera(usuario, bd)
    contexto["guardado"] = bool(guardado)
    return plantillas.TemplateResponse(request, "olb_byte/cartera.html", contexto)


@router.post("/olb-byte/proveedor/abonos", name="registrar_abono_proveedor", response_model=None)
def registrar_abono_proveedor(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    monto: Annotated[str, Form()] = "",
    concepto: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra un pago al proveedor que reduce la deuda acumulada (RF-08).

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        monto: Dinero pagado al proveedor.
        concepto: Descripción del pago; vacía usa el texto por defecto.

    Returns:
        Redirección a la vista de cartera o la misma vista con el error.
    """
    exigir_administrador(usuario)
    try:
        movimiento = comercial.registrar_abono_proveedor(
            bd, monto, concepto.strip() or "Abono al proveedor"
        )
        auditoria.registrar(
            bd, usuario.id_usuario, "ABONO_PROVEEDOR", "movimientos_proveedor", movimiento.id_movimiento
        )
    except (ValueError, ArithmeticError) as error:
        bd.rollback()
        return plantillas.TemplateResponse(
            request,
            "olb_byte/cartera.html",
            _contexto_cartera(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte/cartera?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


def _pagina_error_pdf(id_venta: str, mensaje: str, codigo: int) -> HTMLResponse:
    """Muestra por qué no se pudo generar el PDF y cómo volver a la factura.

    Args:
        id_venta: Orden cuya factura se intentó imprimir.
        mensaje: Motivo del fallo, en texto.
        codigo: Código HTTP de la respuesta.

    Returns:
        Página HTML sencilla con el motivo y un enlace de regreso.
    """
    cuerpo = (
        "<!DOCTYPE html><html lang=\"es\"><meta charset=\"UTF-8\">"
        "<title>No se pudo generar el PDF</title>"
        "<body style=\"font-family:Arial,sans-serif;max-width:560px;margin:40px auto\">"
        "<h1>No se pudo generar el PDF</h1>"
        f"<p>{escape(mensaje)}</p>"
        f"<p><a href=\"/olb-byte/factura/{escape(id_venta)}\">Volver a la factura</a></p>"
        "</body></html>"
    )
    return HTMLResponse(cuerpo, status_code=codigo)


@router.get("/olb-byte/factura/{id_venta}/pdf", name="ver_factura_pdf", response_model=None)
def ver_factura_pdf(
    id_venta: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    descargar: int = 1,
) -> Response:
    """Genera la factura en PDF tamaño Carta (RF-18 y RF-19).

    Args:
        id_venta: Orden facturada.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        descargar: `1` para descargar el archivo; `0` para mostrarlo en la vista previa.

    Returns:
        Archivo PDF, o una página con el motivo si no se pudo generar.

    Raises:
        HTTPException: 403 si el usuario no es administrador; 404 si la orden no existe.
    """
    exigir_administrador(usuario)
    venta = comercial.obtener_venta(bd, id_venta)
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")
    try:
        contexto = factura_pdf.datos_factura(bd, venta)
    except ValueError as error:
        return _pagina_error_pdf(id_venta, str(error), 422)

    html = plantillas.get_template("olb_byte/factura_pdf.html").render(contexto)
    try:
        pdf = factura_pdf.generar_pdf(html)
    except factura_pdf.ChromiumNoDisponible as error:
        return _pagina_error_pdf(id_venta, str(error), 503)

    disposicion = "attachment" if descargar else "inline"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposicion}; filename="{contexto["nombre_archivo"]}"'},
    )


@router.get("/olb-byte/analitica", response_class=HTMLResponse, name="ver_analitica")
def ver_analitica(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    anio: int = 0,
) -> HTMLResponse:
    """Muestra los reportes mensuales y anuales, los clientes VIP y las alertas de costo.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        anio: Año del reporte mensual; cero usa el año actual.

    Returns:
        HTML de la vista de analítica.
    """
    exigir_administrador(usuario)
    anio_actual = datetime.now(comercial.ZONA_TIENDA).year
    anio_consultado = anio or anio_actual
    anios = sorted(set(analitica.anios_con_ventas(bd)) | {anio_actual, anio_consultado}, reverse=True)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Analítica · OLB_BYTE",
            "anio": anio_consultado,
            "anios": anios,
            "mensual": analitica.reporte_mensual(bd, anio_consultado),
            "anual": analitica.reporte_anual(bd),
            "vip": analitica.ranking_vip(bd),
            "alertas": analitica.alertas_costos(bd),
        }
    )
    return plantillas.TemplateResponse(request, "olb_byte/analitica.html", contexto)


def _contexto_garantias(usuario: UsuarioSesion, bd: Session, *, error: str | None = None) -> dict[str, object]:
    """Prepara la vista de garantías en trámite y el ranking de fallas (RF-05).

    Args:
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error opcional.

    Returns:
        Diccionario para la plantilla.
    """
    reclamos = []
    for garantia in comercial.listar_garantias(bd):
        venta = comercial.obtener_venta(bd, garantia.id_venta)
        reclamos.append(
            {
                "garantia": garantia,
                "venta": venta,
                "vigente": comercial.garantia_vigente_al_reclamo(venta, garantia.fecha_reclamo)
                if venta is not None
                else False,
                "cerrado": garantia.estado_tramite in comercial.ESTADOS_FINALES_GARANTIA,
            }
        )
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "Garantías · OLB_BYTE",
            "reclamos": reclamos,
            "opciones": comercial.opciones_garantia(bd),
            "ranking": comercial.ranking_fallas(bd),
            "estados": comercial.ESTADOS_GARANTIA,
            "error": error,
        }
    )
    return contexto


@router.get("/olb-byte/garantias", response_class=HTMLResponse, name="ver_garantias")
def ver_garantias(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    guardado: int = 0,
) -> HTMLResponse:
    """Muestra los reclamos en trámite y el ranking de productos con más fallas.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        guardado: Bandera de éxito.

    Returns:
        HTML de la vista de garantías.
    """
    exigir_administrador(usuario)
    contexto = _contexto_garantias(usuario, bd)
    contexto["guardado"] = bool(guardado)
    return plantillas.TemplateResponse(request, "olb_byte/garantias.html", contexto)


@router.post("/olb-byte/garantias", name="registrar_garantia", response_model=None)
def registrar_garantia(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    id_detalle: Annotated[str, Form()] = "",
    observacion: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Abre un reclamo de garantía sobre una línea vendida.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        id_detalle: Línea con la falla.
        observacion: Descripción de la falla.

    Returns:
        Redirección a la vista de garantías o la misma vista con el error.
    """
    exigir_administrador(usuario)
    try:
        if not id_detalle.strip():
            raise ValueError("Elige el producto con la falla.")
        garantia = comercial.registrar_garantia(bd, id_detalle, observacion)
        auditoria.registrar(bd, usuario.id_usuario, "GARANTIA_REGISTRADA", "garantias_proveedor", garantia.id_garantia)
    except (ValueError, ArithmeticError) as error:
        bd.rollback()
        return plantillas.TemplateResponse(
            request,
            "olb_byte/garantias.html",
            _contexto_garantias(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte/garantias?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/olb-byte/garantias/{id_garantia}/estado", name="actualizar_garantia", response_model=None)
def actualizar_garantia(
    request: Request,
    id_garantia: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    estado: Annotated[str, Form()] = "",
    observacion: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Avanza el trámite de un reclamo con el proveedor.

    Args:
        request: Petición HTTP.
        id_garantia: Reclamo a actualizar.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        estado: Nuevo estado del trámite.
        observacion: Nota del trámite.

    Returns:
        Redirección a la vista de garantías o la misma vista con el error.
    """
    exigir_administrador(usuario)
    try:
        comercial.actualizar_estado_garantia(bd, id_garantia, estado, observacion)
        auditoria.registrar(bd, usuario.id_usuario, "GARANTIA_ACTUALIZADA", "garantias_proveedor", id_garantia)
    except (ValueError, ArithmeticError) as error:
        bd.rollback()
        return plantillas.TemplateResponse(
            request,
            "olb_byte/garantias.html",
            _contexto_garantias(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte/garantias?guardado=1", status_code=status.HTTP_303_SEE_OTHER)
