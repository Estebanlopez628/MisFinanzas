"""Módulo comercial OLB_BYTE: inventario, clientes, ventas y cartera.

Responsabilidad
---------------
Servir el panel operativo de la tienda y traducir los formularios a llamadas de
`servicios.comercial`. Incluye la factura imprimible y el enlace de WhatsApp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_datos import obtener_bd
from app.dependencias import UsuarioSesion, exigir_administrador, obtener_usuario_actual
from app.modelos import Cliente, Producto, Venta, VentaDetalle
from app.routers.vistas import contexto_base, plantillas
from app.servicios import auditoria, comercial

router = APIRouter(tags=["OLB_BYTE"])


@dataclass(frozen=True)
class DetalleVenta:
    """Fila de detalle lista para plantillas y facturas.

    Attributes:
        nombre: Nombre del producto.
        cantidad: Unidades vendidas.
        precio_unitario: Precio aplicado.
        subtotal: Precio por cantidad.
        garantia_meses: Garantía ofrecida.
    """

    nombre: str
    cantidad: int
    precio_unitario: object
    subtotal: object
    garantia_meses: int | None


def _detalle_de_venta(bd: Session, id_venta: str) -> list[DetalleVenta]:
    """Recupera las líneas de una venta con el nombre del producto.

    Args:
        bd: Sesión de base de datos.
        id_venta: Venta consultada.

    Returns:
        Lista de detalles.
    """
    filas = bd.execute(
        select(VentaDetalle, Producto)
        .join(Producto, Producto.id_producto == VentaDetalle.id_producto)
        .where(VentaDetalle.id_venta == id_venta)
    ).all()
    return [
        DetalleVenta(
            nombre=producto.nombre,
            cantidad=detalle.cantidad,
            precio_unitario=detalle.precio_unitario,
            subtotal=detalle.precio_unitario * detalle.cantidad,
            garantia_meses=producto.garantia_meses,
        )
        for detalle, producto in filas
    ]


def _contexto(
    usuario: UsuarioSesion, bd: Session, *, error: str | None = None, guardado: bool = False
) -> dict[str, object]:
    """Prepara el contexto del panel comercial.

    Args:
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        error: Mensaje de error opcional.
        guardado: Bandera de éxito.

    Returns:
        Diccionario para la plantilla.
    """
    ventas = comercial.listar_ventas(bd)
    clientes = comercial.listar_clientes(bd)
    mapa_clientes = {cliente.id_cliente: cliente for cliente in clientes}
    ventas_info = []
    for venta in ventas:
        cliente = mapa_clientes.get(venta.id_cliente)
        lineas = _detalle_de_venta(bd, venta.id_venta)
        ventas_info.append(
            {
                "venta": venta,
                "cliente": cliente,
                "lineas": lineas,
                "enlace_whatsapp": (
                    comercial.enlace_whatsapp_factura(
                        venta,
                        cliente,
                        [
                            {
                                "nombre": linea.nombre,
                                "cantidad": linea.cantidad,
                                "subtotal": linea.subtotal,
                            }
                            for linea in lineas
                        ],
                    )
                    if cliente is not None
                    else "#"
                ),
            }
        )

    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": "OLB_BYTE",
            "productos": comercial.listar_productos(bd),
            "clientes": clientes,
            "ventas": ventas_info,
            "cartera": comercial.cartera(bd),
            "resumen": comercial.resumen_comercial(bd),
            "metodos_pago": comercial.METODOS_PAGO,
            "error": error,
            "guardado": guardado,
        }
    )
    return contexto


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


@router.post("/olb-byte/productos", name="crear_producto", response_model=None)
def crear_producto(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    sku: Annotated[str, Form()] = "",
    nombre: Annotated[str, Form()] = "",
    costo: Annotated[str, Form()] = "",
    precio_venta: Annotated[str, Form()] = "",
    stock: Annotated[str, Form()] = "0",
    garantia_meses: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Registra un producto.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        sku: Código único.
        nombre: Nombre.
        costo: Costo de compra.
        precio_venta: Precio al público.
        stock: Unidades iniciales.
        garantia_meses: Meses de garantía.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    try:
        producto = comercial.crear_producto(
            bd,
            sku,
            nombre,
            precio_venta,
            costo or "0",
            int(stock or "0"),
            int(garantia_meses) if garantia_meses.strip() else None,
        )
        auditoria.registrar(
            bd, usuario.id_usuario, "PRODUCTO_CREADO", "productos", producto.nombre
        )
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "olb_byte/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/olb-byte/productos/{id_producto}/eliminar", name="eliminar_producto", response_model=None)
def eliminar_producto(
    request: Request,
    id_producto: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Elimina un producto sin ventas.

    Args:
        request: Petición HTTP.
        id_producto: Producto a eliminar.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    try:
        comercial.eliminar_producto(bd, id_producto)
    except ValueError as error:
        return plantillas.TemplateResponse(
            request,
            "olb_byte/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte", status_code=status.HTTP_303_SEE_OTHER)


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
    """Registra un cliente.

    Args:
        request: Petición HTTP.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        nombre: Nombre del cliente.
        telefono_whatsapp: Teléfono.
        correo: Correo.
        direccion: Dirección.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    try:
        cliente = comercial.crear_cliente(
            bd, nombre, telefono_whatsapp or None, correo or None, direccion or None
        )
        auditoria.registrar(bd, usuario.id_usuario, "CLIENTE_CREADO", "clientes", cliente.nombre)
    except ValueError as error:
        return plantillas.TemplateResponse(
            request,
            "olb_byte/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/olb-byte/ventas", name="registrar_venta", response_model=None)
async def registrar_venta(
    request: Request,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse | RedirectResponse:
    """Registra una venta con una o varias líneas.

    Los campos llegan como listas (``id_producto``, ``cantidad`` y
    ``precio_unitario``) para admitir varias filas sin JavaScript.

    Args:
        request: Petición HTTP con el formulario.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    formulario = await request.form()
    id_cliente = str(formulario.get("id_cliente", "")).strip()
    productos = formulario.getlist("id_producto")
    cantidades = formulario.getlist("cantidad")
    precios = formulario.getlist("precio_unitario")

    lineas: list[comercial.LineaVenta] = []
    try:
        for indice, id_producto in enumerate(productos):
            if not str(id_producto).strip():
                continue
            cantidad = int(str(cantidades[indice] or "0"))
            precio_texto = str(precios[indice]).strip() if indice < len(precios) else ""
            precio = None
            if precio_texto:
                from app.core.texto import parsear_monto

                precio = parsear_monto(precio_texto)
            lineas.append(
                comercial.LineaVenta(
                    id_producto=str(id_producto), cantidad=cantidad, precio_unitario=precio
                )
            )

        venta = comercial.registrar_venta(
            bd, id_cliente, lineas, datetime.now(timezone.utc)
        )
        auditoria.registrar(
            bd, usuario.id_usuario, "VENTA_REGISTRADA", "ventas", f"{venta.total}"
        )
    except (ValueError, ArithmeticError, IndexError) as error:
        return plantillas.TemplateResponse(
            request,
            "olb_byte/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte?guardado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/olb-byte/ventas/{id_venta}/abonos", name="registrar_abono", response_model=None)
def registrar_abono(
    request: Request,
    id_venta: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
    monto: Annotated[str, Form()] = "",
    metodo_pago: Annotated[str, Form()] = "EFECTIVO",
) -> HTMLResponse | RedirectResponse:
    """Aplica un abono a una venta.

    Args:
        request: Petición HTTP.
        id_venta: Venta abonada.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.
        monto: Dinero entregado.
        metodo_pago: Medio de pago.

    Returns:
        Redirección o vista con error.
    """
    exigir_administrador(usuario)
    try:
        comercial.registrar_abono(bd, id_venta, monto, metodo_pago)
        auditoria.registrar(bd, usuario.id_usuario, "ABONO_REGISTRADO", "abonos", id_venta)
    except (ValueError, ArithmeticError) as error:
        return plantillas.TemplateResponse(
            request,
            "olb_byte/index.html",
            _contexto(usuario, bd, error=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/olb-byte", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/olb-byte/factura/{id_venta}", response_class=HTMLResponse, name="ver_factura")
def ver_factura(
    request: Request,
    id_venta: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> HTMLResponse:
    """Muestra la factura imprimible de una venta.

    Args:
        request: Petición HTTP.
        id_venta: Venta facturada.
        usuario: Administrador autenticado.
        bd: Sesión de base de datos.

    Returns:
        HTML de la factura.

    Raises:
        HTTPException: 403 si el usuario no es administrador; 404 si la venta
            no existe.
    """
    exigir_administrador(usuario)
    venta = bd.get(Venta, id_venta)
    if venta is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Venta no encontrada.")

    cliente = bd.get(Cliente, venta.id_cliente)
    lineas = _detalle_de_venta(bd, id_venta)
    contexto = contexto_base(usuario)
    contexto.update(
        {
            "titulo_pagina": f"Factura {venta.id_venta[:8]}",
            "venta": venta,
            "cliente": cliente,
            "lineas": lineas,
            "total": venta.total,
            "enlace_whatsapp": (
                comercial.enlace_whatsapp_factura(
                    venta,
                    cliente,
                    [
                        {
                            "nombre": linea.nombre,
                            "cantidad": linea.cantidad,
                            "subtotal": linea.subtotal,
                        }
                        for linea in lineas
                    ],
                )
                if cliente is not None
                else "#"
            ),
        }
    )
    return plantillas.TemplateResponse(request, "olb_byte/factura.html", contexto)
