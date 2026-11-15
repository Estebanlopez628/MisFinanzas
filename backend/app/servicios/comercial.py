"""Operación comercial de OLB_BYTE: inventario, ventas y cartera.

Responsabilidad
---------------
- Mantener productos y clientes.
- Registrar ventas con una o varias líneas, descontando stock de forma atómica.
- Aplicar abonos y actualizar el saldo pendiente de cada venta.
- Calcular la cartera y generar enlaces de factura por WhatsApp.

Las tablas involucradas están documentadas en `diccionario_datos.md` §10.
Toda la aritmética usa `Decimal` y se redondea al persistir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import Abono, Cliente, Producto, Venta, VentaDetalle

CERO = Decimal("0")
ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_PARCIAL = "PARCIAL"
ESTADO_PAGADA = "PAGADA"
METODOS_PAGO = ("EFECTIVO", "TRANSFERENCIA", "NEQUI", "DAVIPLATA", "TARJETA")


@dataclass(frozen=True)
class LineaVenta:
    """Línea solicitada para registrar una venta.

    Attributes:
        id_producto: Producto vendido.
        cantidad: Unidades; debe ser positiva.
        precio_unitario: Precio pactado; si es `None` se usa el del producto.
    """

    id_producto: str
    cantidad: int
    precio_unitario: Decimal | None = None


def crear_producto(
    bd: Session,
    sku: str,
    nombre: str,
    precio_venta: Decimal | str | int | float,
    costo: Decimal | str | int | float = CERO,
    stock: int = 0,
    garantia_meses: int | None = None,
) -> Producto:
    """Registra un producto del inventario.

    Args:
        bd: Sesión de base de datos.
        sku: Código único del producto.
        nombre: Nombre comercial.
        precio_venta: Precio al público.
        costo: Costo de compra.
        stock: Unidades disponibles.
        garantia_meses: Meses de garantía ofrecidos.

    Returns:
        El producto persistido.

    Raises:
        ValueError: Si el SKU o el nombre faltan, los precios son negativos, el
            stock es negativo o el SKU ya existe.
    """
    sku_limpio = sku.strip().upper()
    nombre_limpio = nombre.strip()
    if not sku_limpio:
        raise ValueError("El SKU es obligatorio.")
    if not nombre_limpio:
        raise ValueError("El nombre del producto es obligatorio.")

    existente = bd.scalar(select(Producto).where(Producto.sku == sku_limpio))
    if existente is not None:
        raise ValueError("Ya existe un producto con ese SKU.")

    precio = redondear_dinero(parsear_monto(str(precio_venta)))
    valor_costo = redondear_dinero(parsear_monto(str(costo)))
    if precio < CERO or valor_costo < CERO:
        raise ValueError("Los precios no pueden ser negativos.")
    if stock < 0:
        raise ValueError("El stock no puede ser negativo.")

    producto = Producto(
        sku=sku_limpio[:40],
        nombre=nombre_limpio[:120],
        costo=valor_costo,
        precio_venta=precio,
        stock=int(stock),
        garantia_meses=garantia_meses,
    )
    bd.add(producto)
    bd.commit()
    bd.refresh(producto)
    return producto


def listar_productos(bd: Session) -> list[Producto]:
    """Lista el inventario ordenado por nombre.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Lista de productos.
    """
    return list(bd.scalars(select(Producto).order_by(Producto.nombre)))


def eliminar_producto(bd: Session, id_producto: str) -> bool:
    """Elimina un producto sin ventas asociadas.

    Args:
        bd: Sesión de base de datos.
        id_producto: Producto a eliminar.

    Returns:
        `True` si se eliminó.

    Raises:
        ValueError: Si el producto tiene ventas registradas o no existe.
    """
    producto = bd.get(Producto, id_producto)
    if producto is None:
        return False

    vendido = bd.scalar(
        select(VentaDetalle).where(VentaDetalle.id_producto == id_producto).limit(1)
    )
    if vendido is not None:
        raise ValueError("No se puede eliminar un producto con ventas registradas.")

    bd.delete(producto)
    bd.commit()
    return True


def crear_cliente(
    bd: Session,
    nombre: str,
    telefono_whatsapp: str | None = None,
    correo: str | None = None,
    direccion: str | None = None,
) -> Cliente:
    """Registra un cliente de la tienda.

    Args:
        bd: Sesión de base de datos.
        nombre: Nombre del cliente.
        telefono_whatsapp: Número con indicativo, sin espacios.
        correo: Correo electrónico.
        direccion: Dirección de entrega.

    Returns:
        El cliente persistido.

    Raises:
        ValueError: Si el nombre está vacío.
    """
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise ValueError("El nombre del cliente es obligatorio.")

    cliente = Cliente(
        nombre=nombre_limpio[:120],
        telefono_whatsapp=(telefono_whatsapp or "").strip()[:20] or None,
        correo=(correo or "").strip()[:150] or None,
        direccion=(direccion or "").strip()[:200] or None,
    )
    bd.add(cliente)
    bd.commit()
    bd.refresh(cliente)
    return cliente


def listar_clientes(bd: Session) -> list[Cliente]:
    """Lista los clientes ordenados por nombre.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Lista de clientes.
    """
    return list(bd.scalars(select(Cliente).order_by(Cliente.nombre)))


def registrar_venta(
    bd: Session,
    id_cliente: str,
    lineas: list[LineaVenta],
    fecha_venta: datetime | None = None,
) -> Venta:
    """Registra una venta y descuenta el stock de cada producto.

    Args:
        bd: Sesión de base de datos.
        id_cliente: Cliente que compra.
        lineas: Líneas de la venta.
        fecha_venta: Fecha del documento; por defecto ahora.

    Returns:
        La venta persistida con su detalle.

    Raises:
        ValueError: Si el cliente no existe, no hay líneas, una cantidad es
            inválida o no hay stock suficiente.
    """
    cliente = bd.get(Cliente, id_cliente)
    if cliente is None:
        raise ValueError("El cliente seleccionado no existe.")
    if not lineas:
        raise ValueError("La venta debe tener al menos un producto.")

    venta = Venta(
        id_cliente=id_cliente,
        fecha_venta=fecha_venta or datetime.now(timezone.utc),
        total=CERO,
        saldo_pendiente=CERO,
        estado=ESTADO_PENDIENTE,
    )
    bd.add(venta)
    bd.flush()

    total = CERO
    for linea in lineas:
        producto = bd.get(Producto, linea.id_producto)
        if producto is None:
            raise ValueError("Uno de los productos seleccionados no existe.")
        if linea.cantidad <= 0:
            raise ValueError("La cantidad de cada producto debe ser mayor que cero.")
        if producto.stock < linea.cantidad:
            raise ValueError(
                f"No hay stock suficiente de {producto.nombre}. Disponible: {producto.stock}."
            )

        precio = (
            redondear_dinero(linea.precio_unitario)
            if linea.precio_unitario is not None
            else redondear_dinero(producto.precio_venta)
        )
        if precio < CERO:
            raise ValueError("El precio unitario no puede ser negativo.")

        producto.stock -= linea.cantidad
        subtotal = redondear_dinero(precio * linea.cantidad)
        total = redondear_dinero(total + subtotal)
        bd.add(
            VentaDetalle(
                id_venta=venta.id_venta,
                id_producto=producto.id_producto,
                cantidad=linea.cantidad,
                precio_unitario=precio,
            )
        )

    venta.total = total
    venta.saldo_pendiente = total
    bd.commit()
    bd.refresh(venta)
    return venta


def registrar_abono(
    bd: Session,
    id_venta: str,
    monto: Decimal | str | int | float,
    metodo_pago: str = "EFECTIVO",
) -> Abono:
    """Aplica un abono a una venta.

    Args:
        bd: Sesión de base de datos.
        id_venta: Venta abonada.
        monto: Dinero entregado; positivo y no mayor al saldo.
        metodo_pago: Medio de pago.

    Returns:
        El abono persistido.

    Raises:
        ValueError: Si la venta no existe, el monto es inválido o supera el
            saldo pendiente, o el método no es válido.
    """
    venta = bd.get(Venta, id_venta)
    if venta is None:
        raise ValueError("La venta no existe.")

    valor = redondear_dinero(parsear_monto(str(monto)))
    if valor <= CERO:
        raise ValueError("El abono debe ser mayor que cero.")
    if valor > venta.saldo_pendiente:
        raise ValueError("El abono no puede superar el saldo pendiente.")

    metodo = metodo_pago.strip().upper()
    if metodo not in METODOS_PAGO:
        raise ValueError("El método de pago no es válido.")

    abono = Abono(id_venta=id_venta, monto=valor, metodo_pago=metodo)
    bd.add(abono)

    venta.saldo_pendiente = redondear_dinero(venta.saldo_pendiente - valor)
    if venta.saldo_pendiente == CERO:
        venta.estado = ESTADO_PAGADA
    else:
        venta.estado = ESTADO_PARCIAL
    bd.commit()
    bd.refresh(abono)
    return abono


def listar_ventas(bd: Session) -> list[Venta]:
    """Lista las ventas de la más reciente a la más antigua.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Lista de ventas.
    """
    return list(bd.scalars(select(Venta).order_by(Venta.fecha_venta.desc())))


def cartera(bd: Session) -> list[Venta]:
    """Devuelve las ventas con saldo pendiente.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Lista de ventas ordenadas por fecha ascendente (las más viejas primero).
    """
    consulta = (
        select(Venta)
        .where(Venta.saldo_pendiente > CERO)
        .order_by(Venta.fecha_venta)
    )
    return list(bd.scalars(consulta))


def resumen_comercial(bd: Session) -> dict[str, Decimal | int]:
    """Calcula los indicadores principales de la tienda.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Diccionario con ventas totales, cartera, productos y stock bajo.
    """
    ventas = listar_ventas(bd)
    productos = listar_productos(bd)
    return {
        "ventas_totales": redondear_dinero(sum((v.total for v in ventas), start=CERO)),
        "cartera": redondear_dinero(
            sum((v.saldo_pendiente for v in ventas), start=CERO)
        ),
        "numero_ventas": len(ventas),
        "productos": len(productos),
        "stock_bajo": sum(1 for p in productos if p.stock <= 3),
    }


def enlace_whatsapp_factura(venta: Venta, cliente: Cliente, lineas: list[dict[str, object]]) -> str:
    """Construye un enlace de WhatsApp con el resumen de la factura.

    Args:
        venta: Venta facturada.
        cliente: Cliente destinatario.
        lineas: Filas con producto, cantidad y subtotal.

    Returns:
        URL de `wa.me` lista para abrir; si el cliente no tiene teléfono se
        devuelve un enlace genérico de WhatsApp sin destinatario.
    """
    detalle = "\n".join(
        f"• {fila['nombre']} x{fila['cantidad']} = ${fila['subtotal']:,.0f}".replace(",", ".")
        for fila in lineas
    )
    texto = (
        f"Hola {cliente.nombre}, gracias por tu compra en OLB_BYTE.\n"
        f"Factura del {venta.fecha_venta:%d/%m/%Y}\n"
        f"{detalle}\n"
        f"Total: ${venta.total:,.0f}\n"
        f"Saldo pendiente: ${venta.saldo_pendiente:,.0f}"
    ).replace(",", ".")
    telefono = (cliente.telefono_whatsapp or "").replace(" ", "").replace("+", "")
    if telefono and not telefono.startswith("57"):
        telefono = "57" + telefono
    base = f"https://wa.me/{telefono}" if telefono else "https://wa.me/"
    return f"{base}?text={quote(texto)}"
