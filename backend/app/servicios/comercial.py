"""Operación comercial de OLB_BYTE: ventas a crédito, cartera y deuda con proveedor.

Responsabilidad
---------------
- Registrar órdenes de venta con varias líneas, sin inventario (ADR-35): cada
  línea guarda una copia de nombre, categoría, costo y precio.
- Asignar el consecutivo `numero_orden`, que nunca se reutiliza.
- Registrar la compra a crédito al proveedor y sus abonos en un libro de movimientos.
- Aplicar abonos de clientes y actualizar el saldo de cada orden.
- Anular órdenes con motivo y registrar la devolución del dinero abonado.
- Calcular cartera, deuda con proveedor, caja y efectivo libre (RF-08 a RF-10).

Las tablas están documentadas en `diccionario_datos.md` §10. Toda la aritmética usa
`Decimal` y se redondea al persistir. Los totales se suman en Python para evitar
diferencias de tipo entre motores de base de datos.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import (
    Abono,
    Cliente,
    DevolucionCliente,
    GastoOperativo,
    GarantiaProveedor,
    MovimientoProveedor,
    Venta,
    VentaDetalle,
)

# La garantía y los rankings se miden en la hora de Colombia: una venta a las 11 p. m.
# no debe quedar con la fecha del día siguiente en UTC. Colombia no tiene horario de
# verano, así que un desfase fijo de −5 h es exacto y evita depender de tzdata en Windows.
ZONA_TIENDA = timezone(timedelta(hours=-5))
CERO = Decimal("0")

ESTADO_PAGO_PENDIENTE = "PENDIENTE"
ESTADO_PAGO_PARCIAL = "PARCIAL"
ESTADO_PAGO_PAGADA = "PAGADA"
ESTADO_ACTIVA = "ACTIVA"
ESTADO_ANULADA = "ANULADA"
ESTADO_GARANTIA_SIN = "SIN_GARANTIA"

# ADR-35: solo estos dos medios para los abonos nuevos.
METODOS_PAGO = ("EFECTIVO", "TRANSFERENCIA")

GARANTIA_MESES_DEFECTO = 3
TIPO_COMPRA = "COMPRA_CREDITO"
TIPO_ABONO_PROVEEDOR = "ABONO"
# SRS v4.44, §8.1: deuda que existía antes de usar el sistema. Suma al saldo con
# el proveedor y se registra en el libro como «Deuda inicial».
TIPO_DEUDA_INICIAL = "DEUDA_INICIAL"

# SRS Migración de Cartera: las ventas de la app nacen como `VENTA_NORMAL`; las
# que se cargan como saldo histórico llevan `MIGRACION_CARTERA` y no generan
# factura ni envío automático por WhatsApp.
ORIGEN_VENTA_NORMAL = "VENTA_NORMAL"
ORIGEN_MIGRACION_CARTERA = "MIGRACION_CARTERA"
# Fila que representa el saldo global cuando el usuario no sabe el detalle.
NOMBRE_SALDO_MIGRADO = "Saldo pendiente migrado"

ETIQUETAS_MOVIMIENTO = {
    TIPO_COMPRA: "Compra a crédito",
    TIPO_ABONO_PROVEEDOR: "Pago",
    TIPO_DEUDA_INICIAL: "Deuda inicial",
}


def etiqueta_tipo_movimiento(tipo: str) -> str:
    """Traduce el tipo técnico del movimiento a su etiqueta visible.

    Args:
        tipo: `COMPRA_CREDITO`, `ABONO` o `DEUDA_INICIAL`.

    Returns:
        El texto que ve el usuario; el tipo original si no está en el catálogo.
    """
    return ETIQUETAS_MOVIMIENTO.get(tipo, tipo)


@dataclass(frozen=True)
class LineaVenta:
    """Producto escrito en una venta.

    Attributes:
        nombre: Nombre del producto.
        cantidad: Unidades; debe ser mayor que cero.
        precio_unitario: Valor de venta al cliente.
        costo_unitario: Precio que cobra el proveedor.
        categoria: Categoría opcional del producto.
        garantia_meses: Meses de garantía; `0` significa sin garantía.
    """

    nombre: str
    cantidad: int
    precio_unitario: Decimal | str | int | float
    costo_unitario: Decimal | str | int | float = CERO
    categoria: str | None = None
    garantia_meses: int = GARANTIA_MESES_DEFECTO


def ahora_tienda() -> datetime:
    """Devuelve el momento actual en hora de la tienda.

    Todas las fechas comerciales se generan con esta función para que la base guarde
    la hora de Colombia. Si se usara UTC en unas y `now()` del servidor en otras, el
    recibo de un abono mostraría horas distintas a las de la venta.

    Returns:
        Fecha y hora con la zona de la tienda.
    """
    return datetime.now(ZONA_TIENDA)


def normalizar_telefono(texto: str | None) -> str | None:
    """Deja un celular colombiano de 10 dígitos sin indicativo.

    Acepta espacios, guiones, `+57` o `57` al inicio, porque así llegan los
    contactos del celular. Un número distinto de 10 dígitos no sirve para
    WhatsApp, por eso se rechaza en vez de guardarlo mal.

    Args:
        texto: Número tal como lo escribió el usuario o lo entregó la agenda.

    Returns:
        Los 10 dígitos, o `None` si no se escribió ningún número.

    Raises:
        ValueError: Si quedan dígitos pero no suman 10 tras quitar el indicativo.
    """
    if texto is None:
        return None
    digitos = "".join(caracter for caracter in texto if caracter.isdigit())
    if not digitos:
        return None
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    if len(digitos) != 10:
        raise ValueError("El celular debe tener 10 dígitos (sin el indicativo 57).")
    return digitos


def _dinero(valor: Decimal | str | int | float) -> Decimal:
    """Convierte un valor de formulario o de código a dinero redondeado.

    Args:
        valor: Monto en cualquier formato aceptado por `parsear_monto`.

    Returns:
        Monto con dos decimales.

    Raises:
        ValueError: Si el texto no es un monto válido.
    """
    if isinstance(valor, Decimal):
        return redondear_dinero(valor)
    return redondear_dinero(parsear_monto(str(valor)))


def _sumar_meses(fecha: date, meses: int) -> date:
    """Suma meses calendario a una fecha, ajustando el día al último del mes.

    Args:
        fecha: Fecha de partida.
        meses: Meses a sumar (no negativo).

    Returns:
        Fecha resultante. El 31 de enero más un mes da el 28 o 29 de febrero.
    """
    indice = fecha.month - 1 + meses
    anio = fecha.year + indice // 12
    mes = indice % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def _texto_garantia(meses: int) -> str:
    """Redacta la garantía de una línea según sus meses.

    Args:
        meses: Meses de garantía.

    Returns:
        Texto para la factura, por ejemplo «3 meses por defectos de fábrica».
    """
    if meses <= 0:
        return "Sin garantía"
    etiqueta = "mes" if meses == 1 else "meses"
    return f"{meses} {etiqueta} por defectos de fábrica"


def _validar_linea(linea: LineaVenta) -> None:
    """Valida los datos de una línea antes de persistir la venta.

    Args:
        linea: Línea a revisar.

    Raises:
        ValueError: Si falta el nombre, la cantidad no es positiva, un precio o
            costo es negativo o los meses de garantía no son válidos.
    """
    if not linea.nombre.strip():
        raise ValueError("Cada producto necesita un nombre.")
    if linea.cantidad <= 0:
        raise ValueError("La cantidad de cada producto debe ser mayor que cero.")
    if linea.garantia_meses < 0:
        raise ValueError("La garantía no puede tener meses negativos.")


def _cliente_para_venta(bd: Session, nombre: str, telefono: str | None) -> Cliente:
    """Busca el cliente por celular o por nombre, o lo crea si no existe.

    Con celular se busca por número y nombre: un mismo número puede ser de dos personas.
    Sin celular se busca por nombre entre los clientes que no tienen número.

    Args:
        bd: Sesión de base de datos.
        nombre: Nombre escrito en la venta.
        telefono: Celular normalizado o `None`.

    Returns:
        Cliente existente o recién creado (todavía sin confirmar).
    """
    if telefono:
        # Celular y nombre deben coincidir: un número compartido por dos personas distintas
        # no las une en un solo cliente.
        existente = bd.scalar(
            select(Cliente).where(
                Cliente.telefono_whatsapp == telefono,
                func.lower(Cliente.nombre) == nombre.lower(),
            )
        )
    else:
        existente = bd.scalar(
            select(Cliente).where(
                Cliente.telefono_whatsapp.is_(None),
                func.lower(Cliente.nombre) == nombre.lower(),
            )
        )
    if existente is not None:
        return existente
    cliente = Cliente(nombre=nombre[:120], telefono_whatsapp=telefono)
    bd.add(cliente)
    bd.flush()
    return cliente


def _siguiente_numero_orden(bd: Session) -> int:
    """Calcula el próximo consecutivo sin reutilizar números de órdenes anuladas.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Máximo `numero_orden` registrado más uno, o 1 si no hay órdenes.
    """
    maximo = bd.scalar(select(func.max(Venta.numero_orden)))
    return (maximo or 0) + 1


def deuda_proveedor(bd: Session) -> Decimal:
    """Calcula lo que se le debe al proveedor en este momento.

    Deuda = compras a crédito − abonos hechos al proveedor. Las compras de órdenes
    anuladas siguen contando, porque la mercancía ya se compró (ADR-35).

    Args:
        bd: Sesión de base de datos.

    Returns:
        Saldo adeudado, nunca negativo.
    """
    movimientos = bd.scalars(select(MovimientoProveedor)).all()
    compras = sum(
        (
            m.monto
            for m in movimientos
            if m.tipo in (TIPO_COMPRA, TIPO_DEUDA_INICIAL)
        ),
        start=CERO,
    )
    abonos = sum((m.monto for m in movimientos if m.tipo == TIPO_ABONO_PROVEEDOR), start=CERO)
    return redondear_dinero(max(compras - abonos, CERO))


def desglose_deuda_proveedor(bd: Session) -> dict[str, object]:
    """Separa la deuda del proveedor en pasivo anterior y deuda de ventas del sistema.

    Regla de imputación (SRS v4.44, ADR-115): los abonos pagan primero la deuda
    corriente de las compras a crédito hechas desde que se implementó el sistema;
    solo el remanente reduce las deudas anteriores (`DEUDA_INICIAL`). Las dos
    partes suman la deuda total que muestra `deuda_proveedor()`. El desglose
    alimenta la leyenda de la dona «Cartera frente a deuda».

    Args:
        bd: Sesión de base de datos.

    Returns:
        Diccionario con importes, texto y porcentajes (sobre la deuda total) de
        cada parte, más el total. Los porcentajes se redondean a un decimal.
    """
    corriente = CERO
    antiguo = CERO
    consulta = select(MovimientoProveedor).order_by(MovimientoProveedor.fecha)
    for movimiento in bd.scalars(consulta):
        monto = movimiento.monto
        if movimiento.tipo == TIPO_COMPRA:
            corriente += monto
        elif movimiento.tipo == TIPO_DEUDA_INICIAL:
            antiguo += monto
        elif movimiento.tipo == TIPO_ABONO_PROVEEDOR:
            pago_corriente = min(monto, corriente)
            corriente -= pago_corriente
            antiguo = max(CERO, antiguo - (monto - pago_corriente))
    total = redondear_dinero(antiguo + corriente)
    if total <= CERO:
        porcentaje_antiguo = 0.0
        porcentaje_ventas = 0.0
    else:
        porcentaje_antiguo = round(float(antiguo / total * 100), 1)
        porcentaje_ventas = round(float(corriente / total * 100), 1)
    return {
        "anteriores_valor": redondear_dinero(antiguo),
        "anteriores_texto": formatear_pesos(antiguo),
        "anteriores_porcentaje": porcentaje_antiguo,
        "ventas_valor": redondear_dinero(corriente),
        "ventas_texto": formatear_pesos(corriente),
        "ventas_porcentaje": porcentaje_ventas,
        "total": total,
    }


def _registrar_movimiento_proveedor(
    bd: Session,
    tipo: str,
    monto: Decimal,
    concepto: str,
    id_venta: str | None = None,
    *,
    proveedor_nombre: str | None = None,
    fecha_deuda: date | None = None,
    referencia_factura: str | None = None,
) -> MovimientoProveedor:
    """Agrega un movimiento al libro de la cuenta por pagar al proveedor.

    Args:
        bd: Sesión de base de datos.
        tipo: `COMPRA_CREDITO`, `DEUDA_INICIAL` o `ABONO`.
        monto: Valor positivo del movimiento.
        concepto: Descripción legible para el historial.
        id_venta: Orden asociada, si la hay.
        proveedor_nombre: Proveedor de una deuda anterior al sistema.
        fecha_deuda: Fecha real de la deuda anterior al sistema.
        referencia_factura: Referencia o número de factura del proveedor.

    Returns:
        El movimiento agregado, con el saldo tras aplicarlo.
    """
    saldo_anterior = deuda_proveedor(bd)
    if tipo in (TIPO_COMPRA, TIPO_DEUDA_INICIAL):
        saldo_nuevo = saldo_anterior + monto
    else:
        saldo_nuevo = saldo_anterior - monto
    movimiento = MovimientoProveedor(
        fecha=ahora_tienda(),
        tipo=tipo,
        id_venta=id_venta,
        concepto=concepto[:200],
        monto=monto,
        saldo_resultante=redondear_dinero(saldo_nuevo),
        proveedor_nombre=(proveedor_nombre or "").strip()[:120] or None,
        fecha_deuda=fecha_deuda,
        referencia_factura=(referencia_factura or "").strip()[:120] or None,
    )
    bd.add(movimiento)
    return movimiento


def registrar_cliente(
    bd: Session,
    nombre: str,
    telefono_whatsapp: str | None = None,
    correo: str | None = None,
    direccion: str | None = None,
) -> Cliente:
    """Registra un cliente desde la agenda de administración.

    Args:
        bd: Sesión de base de datos.
        nombre: Nombre del cliente.
        telefono_whatsapp: Celular; se normaliza a 10 dígitos.
        correo: Correo electrónico opcional.
        direccion: Dirección de entrega opcional.

    Returns:
        El cliente persistido.

    Raises:
        ValueError: Si el nombre está vacío o el celular no tiene 10 dígitos.
    """
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise ValueError("El nombre del cliente es obligatorio.")

    cliente = Cliente(
        nombre=nombre_limpio[:120],
        telefono_whatsapp=normalizar_telefono(telefono_whatsapp),
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


def buscar_clientes(bd: Session, texto: str, limite: int = 8) -> list[Cliente]:
    """Busca clientes por nombre o celular para el autocompletado de la venta.

    Args:
        bd: Sesión de base de datos.
        texto: Fragmento escrito por el usuario.
        limite: Máximo de resultados.

    Returns:
        Clientes que coinciden, ordenados por nombre. Vacío si el texto está en blanco.
    """
    buscado = texto.strip()
    if not buscado:
        return []
    patron = f"%{buscado}%"
    consulta = (
        select(Cliente)
        .where((Cliente.nombre.ilike(patron)) | (Cliente.telefono_whatsapp.like(patron)))
        .order_by(Cliente.nombre)
        .limit(limite)
    )
    return list(bd.scalars(consulta))


@dataclass(frozen=True)
class PagoInicial:
    """Pago recibido al registrar la venta: pago de contado o anticipo.

    Attributes:
        monto: Dinero recibido; `None` significa el total de la orden (pago de contado).
        metodo_pago: `EFECTIVO` o `TRANSFERENCIA`.
    """

    monto: Decimal | str | int | float | None
    metodo_pago: str


def registrar_venta(
    bd: Session,
    cliente_nombre: str,
    cliente_telefono: str | None,
    lineas: list[LineaVenta],
    fecha_venta: datetime | None = None,
    pago_inicial: PagoInicial | None = None,
    origen: str = ORIGEN_VENTA_NORMAL,
    fecha_compra: date | None = None,
) -> Venta:
    """Registra una orden de venta a crédito y la compra al proveedor.

    La venta no descuenta inventario: la mercancía se compra al proveedor al
    mismo tiempo. Se suma la deuda con el proveedor, y la ganancia se calcula como
    `Σ (precio − costo) × cantidad`. La garantía vence según la línea que antes
    expire, para que el semáforo sea conservador.

    Args:
        bd: Sesión de base de datos.
        cliente_nombre: Nombre del comprador tal como se escribe en el formulario.
        cliente_telefono: Celular opcional; se normaliza a 10 dígitos.
        lineas: Productos de la orden; debe haber al menos uno.
        fecha_venta: Momento de la venta; por defecto ahora.
        pago_inicial: Pago de contado o anticipo, si lo hay.
        origen: `VENTA_NORMAL` o `MIGRACION_CARTERA`.
        fecha_compra: Día real de la compra cuando la orden se migra.

    Returns:
        La orden persistida con su consecutivo.

    Raises:
        ValueError: Si falta el nombre del cliente, no hay líneas o alguna línea
            es inválida.
    """
    nombre = cliente_nombre.strip()
    if not nombre:
        raise ValueError("El nombre del cliente es obligatorio.")
    telefono = normalizar_telefono(cliente_telefono)
    if not lineas:
        raise ValueError("La venta debe tener al menos un producto.")
    # Todo se valida antes de tocar la sesión: un error a mitad de camino dejaría
    # una orden a medio crear visible en el panel.
    valores: list[tuple[LineaVenta, Decimal, Decimal]] = []
    for linea in lineas:
        _validar_linea(linea)
        precio = _dinero(linea.precio_unitario)
        costo = _dinero(linea.costo_unitario)
        if precio < CERO or costo < CERO:
            raise ValueError("Los precios y costos no pueden ser negativos.")
        valores.append((linea, precio, costo))

    total_previsto = sum(
        (redondear_dinero(precio * linea.cantidad) for linea, precio, _ in valores), start=CERO
    )
    monto_inicial: Decimal | None = None
    metodo_inicial = ""
    if pago_inicial is not None:
        monto_inicial = (
            total_previsto if pago_inicial.monto is None else _dinero(pago_inicial.monto)
        )
        if monto_inicial <= CERO:
            raise ValueError("El pago inicial debe ser mayor que cero.")
        if monto_inicial > total_previsto:
            raise ValueError("El anticipo no puede superar el total de la venta.")
        metodo_inicial = _validar_metodo(pago_inicial.metodo_pago)

    ahora = fecha_venta or ahora_tienda()
    fecha_local = ahora.astimezone(ZONA_TIENDA).date()

    cliente = _cliente_para_venta(bd, nombre, telefono)
    venta = Venta(
        numero_orden=_siguiente_numero_orden(bd),
        id_cliente=cliente.id_cliente,
        cliente_nombre=nombre[:120],
        cliente_telefono=telefono,
        fecha_venta=ahora,
        origen=origen,
        fecha_compra=fecha_compra,
    )
    bd.add(venta)
    bd.flush()

    subtotal = CERO
    total_costo = CERO
    ganancia = CERO
    vencimientos: list[tuple[date, str]] = []
    for linea, precio, costo in valores:
        subtotal_item = redondear_dinero(precio * linea.cantidad)
        subtotal += subtotal_item
        total_costo += redondear_dinero(costo * linea.cantidad)
        ganancia += redondear_dinero((precio - costo) * linea.cantidad)
        texto_garantia = _texto_garantia(linea.garantia_meses)
        vencimiento = (
            fecha_local
            if linea.garantia_meses <= 0
            else _sumar_meses(fecha_local, linea.garantia_meses)
        )
        vencimientos.append((vencimiento, texto_garantia))
        bd.add(
            VentaDetalle(
                id_venta=venta.id_venta,
                producto_nombre=linea.nombre.strip()[:120],
                categoria=(linea.categoria or "").strip()[:60] or None,
                cantidad=linea.cantidad,
                costo_unitario=costo,
                precio_unitario=precio,
                subtotal_item=subtotal_item,
                garantia_texto=texto_garantia,
                garantia_fecha_fin=vencimiento,
            )
        )

    vencimiento_orden, texto_orden = min(vencimientos, key=lambda par: par[0])
    total = redondear_dinero(subtotal)
    venta.subtotal = total
    venta.total = total
    venta.total_costo = redondear_dinero(total_costo)
    venta.ganancia_neta = redondear_dinero(ganancia)
    venta.total_abonado = CERO
    venta.saldo_pendiente = total
    venta.estado_pago = ESTADO_PAGO_PAGADA if total == CERO else ESTADO_PAGO_PENDIENTE
    venta.garantia_texto = texto_orden
    venta.garantia_fecha_fin = vencimiento_orden

    if monto_inicial is not None:
        # El pago inicial entra en la misma transacción que la venta: si algo falla,
        # no queda una orden sin su pago ni un pago sin orden.
        bd.add(
            Abono(
                id_venta=venta.id_venta,
                monto=monto_inicial,
                metodo_pago=metodo_inicial,
                fecha_abono=ahora,
            )
        )
        venta.total_abonado = monto_inicial
        venta.saldo_pendiente = redondear_dinero(total - monto_inicial)
        _recalcular_estado_pago(venta)

    if venta.total_costo > CERO:
        _registrar_movimiento_proveedor(
            bd,
            TIPO_COMPRA,
            venta.total_costo,
            f"Compra a crédito orden {venta.numero_orden}",
            venta.id_venta,
        )
    bd.commit()
    bd.refresh(venta)
    return venta


def registrar_venta_migrada(
    bd: Session,
    cliente_nombre: str,
    cliente_telefono: str | None,
    total_adeudado: Decimal | str | int | float,
    fecha_compra: str | date | None = None,
    lineas: list[LineaVenta] | None = None,
) -> Venta:
    """Carga una venta realizada antes del sistema como cartera pendiente.

    SRS Migración de Cartera, bloque 1: la orden nace con `origen` igual a
    `MIGRACION_CARTERA`, sin factura ni envío automático. El total adeudado es el
    dato obligatorio; los productos son opcionales y solo detallan la composición.
    Si la suma de los productos es menor que el total, la diferencia se registra
    como «Saldo pendiente sin detallar» para que la analítica cuadre.

    El costo es opcional: en cero, todo abono que se cobre se reconoce como
    utilidad; con costo, la utilidad se reconoce en proporción a lo cobrado.

    Args:
        bd: Sesión de base de datos.
        cliente_nombre: Nombre del comprador.
        cliente_telefono: Celular opcional; se normaliza a 10 dígitos.
        total_adeudado: Saldo histórico pendiente; debe ser mayor que cero.
        fecha_compra: Día real de la compra; vacío usa hoy en hora de la tienda.
        lineas: Productos opcionales con cantidad, precio y costo.

    Returns:
        La orden persistida con su consecutivo.

    Raises:
        ValueError: Si falta el cliente, el total no es positivo, la fecha no es
            válida o los productos superan el total adeudado.
    """
    nombre = (cliente_nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del cliente es obligatorio.")
    telefono = normalizar_telefono(cliente_telefono)
    total = _dinero(total_adeudado)
    if total <= CERO:
        raise ValueError("El total adeudado debe ser mayor que cero.")
    fecha = _fecha_compra(fecha_compra)

    valores: list[tuple[LineaVenta, Decimal, Decimal]] = []
    lineas_utiles = [
        linea
        for linea in (lineas or [])
        if linea.nombre.strip() != NOMBRE_SALDO_MIGRADO
    ]
    for linea in lineas_utiles:
        _validar_linea(linea)
        precio = _dinero(linea.precio_unitario)
        costo = _dinero(linea.costo_unitario)
        if precio < CERO or costo < CERO:
            raise ValueError("Los precios y costos no pueden ser negativos.")
        valores.append((linea, precio, costo))

    suma_productos = sum(
        (redondear_dinero(precio * linea.cantidad) for linea, precio, _ in valores),
        start=CERO,
    )
    if suma_productos > total:
        raise ValueError(
            "El total adeudado no puede ser menor que la suma de los productos."
        )
    sin_detalle = not valores
    if sin_detalle:
        # Sin detalle conocido no se inventa un precio unitario: la línea existe
        # solo para cuadrar el total; `subtotal_item` conserva la deuda completa.
        valores.append(
            (LineaVenta(NOMBRE_SALDO_MIGRADO, 1, CERO, CERO, garantia_meses=0), CERO, CERO)
        )

    cliente = _cliente_para_venta(bd, nombre, telefono)
    ahora = datetime.combine(fecha, time(12, 0), tzinfo=ZONA_TIENDA)
    venta = Venta(
        numero_orden=_siguiente_numero_orden(bd),
        id_cliente=cliente.id_cliente,
        cliente_nombre=nombre[:120],
        cliente_telefono=telefono,
        fecha_venta=ahora,
        origen=ORIGEN_MIGRACION_CARTERA,
        fecha_compra=fecha,
    )
    bd.add(venta)
    bd.flush()

    total_costo = CERO
    vencimientos: list[tuple[date, str]] = []
    for linea, precio, costo in valores:
        subtotal_item = (
            total
            if sin_detalle and linea.nombre == NOMBRE_SALDO_MIGRADO
            else redondear_dinero(precio * linea.cantidad)
        )
        total_costo += redondear_dinero(costo * linea.cantidad)
        texto_garantia = _texto_garantia(linea.garantia_meses)
        vencimiento = (
            fecha
            if linea.garantia_meses <= 0
            else _sumar_meses(fecha, linea.garantia_meses)
        )
        vencimientos.append((vencimiento, texto_garantia))
        bd.add(
            VentaDetalle(
                id_venta=venta.id_venta,
                producto_nombre=linea.nombre.strip()[:120],
                categoria=(linea.categoria or "").strip()[:60] or None,
                cantidad=linea.cantidad,
                costo_unitario=costo,
                precio_unitario=precio,
                subtotal_item=subtotal_item,
                garantia_texto=None if sin_detalle else texto_garantia,
                garantia_fecha_fin=None if sin_detalle else vencimiento,
            )
        )

    if suma_productos < total and not sin_detalle:
        diferencia = redondear_dinero(total - suma_productos)
        bd.add(
            VentaDetalle(
                id_venta=venta.id_venta,
                producto_nombre="Saldo pendiente sin detallar",
                categoria=None,
                cantidad=1,
                costo_unitario=CERO,
                precio_unitario=diferencia,
                subtotal_item=diferencia,
                garantia_texto=None,
                garantia_fecha_fin=None,
            )
        )

    venta.subtotal = total
    venta.total = total
    venta.total_costo = redondear_dinero(total_costo)
    venta.ganancia_neta = redondear_dinero(total - total_costo)
    venta.total_abonado = CERO
    venta.saldo_pendiente = total
    venta.estado_pago = ESTADO_PAGO_PENDIENTE
    venta.garantia_texto = ""
    venta.garantia_fecha_fin = None
    if vencimientos and not sin_detalle:
        vencimiento_orden, texto_orden = min(vencimientos, key=lambda par: par[0])
        venta.garantia_texto = texto_orden
        venta.garantia_fecha_fin = vencimiento_orden

    # El costo queda registrado solo como dato para el reparto proporcional de
    # cada abono. No se crea deuda con el proveedor al migrar: el saldo global ya
    # incluye ese costo en la deuda inicial del proveedor (SRS Migración §2.3).
    bd.commit()
    bd.refresh(venta)
    return venta


def _fecha_compra(texto: str | date | None) -> date:
    """Normaliza la fecha de compra de una venta migrada.

    Args:
        texto: Fecha ISO, un `date` o vacío.

    Returns:
        La fecha indicada o el día de hoy en hora de la tienda.

    Raises:
        ValueError: Si el texto no es una fecha válida.
    """
    if isinstance(texto, date):
        return texto
    limpio = (texto or "").strip()
    if not limpio:
        return datetime.now(ZONA_TIENDA).date()
    try:
        return date.fromisoformat(limpio)
    except ValueError as error:
        raise ValueError("La fecha de compra no es válida.") from error


def ventas_migradas(bd: Session) -> list[Venta]:
    """Lista las ventas cargadas como saldo histórico, de la más antigua a la nueva.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Órdenes con `origen` igual a `MIGRACION_CARTERA`.
    """
    consulta = (
        select(Venta)
        .where(Venta.origen == ORIGEN_MIGRACION_CARTERA)
        .order_by(Venta.fecha_compra, Venta.numero_orden)
    )
    return list(bd.scalars(consulta))


def _ultimo_recaudo(bd: Session) -> dict[str, datetime]:
    """Obtiene la fecha del último abono de cada orden.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Diccionario `{id_venta: fecha del último abono}`.
    """
    ultimos: dict[str, datetime] = {}
    for abono in bd.scalars(select(Abono).order_by(Abono.fecha_abono)):
        ultimos[abono.id_venta] = abono.fecha_abono
    return ultimos


def _utilidad_reconocida(venta: Venta) -> tuple[Decimal, Decimal]:
    """Reparte lo cobrado entre utilidad y pago al proveedor (SRS Migración).

    Con costo cero, el 100 % del abono es utilidad y no hay pago al proveedor.
    Con costo, el abono se reparte en proporción al costo sobre el total.

    Args:
        venta: Orden migrada.

    Returns:
        Tupla `(utilidad, pago_proveedor)` reconocidos sobre lo abonado.
    """
    abonado = redondear_dinero(venta.total_abonado)
    if abonado <= CERO:
        return CERO, CERO
    if venta.total <= CERO or venta.total_costo <= CERO:
        return abonado, CERO
    proporcion = min(venta.total_costo / venta.total, Decimal("1"))
    pago = redondear_dinero(abonado * proporcion)
    return redondear_dinero(abonado - pago), pago


def resumen_migracion(bd: Session) -> dict[str, object]:
    """Calcula los indicadores de la Migración de Cartera.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Diccionario con la cantidad de órdenes, total histórico, cobrado, saldo,
        utilidad reconocida y pago al proveedor proporcional.
    """
    ordenes = ventas_migradas(bd)
    total = sum((venta.total for venta in ordenes), start=CERO)
    abonado = sum((venta.total_abonado for venta in ordenes), start=CERO)
    saldo = sum((venta.saldo_pendiente for venta in ordenes), start=CERO)
    utilidad = CERO
    pago_proveedor = CERO
    for venta in ordenes:
        parte_utilidad, parte_pago = _utilidad_reconocida(venta)
        utilidad += parte_utilidad
        pago_proveedor += parte_pago
    return {
        "ordenes": len(ordenes),
        "total": redondear_dinero(total),
        "abonado": redondear_dinero(abonado),
        "saldo": redondear_dinero(saldo),
        "utilidad": redondear_dinero(utilidad),
        "pago_proveedor": redondear_dinero(pago_proveedor),
    }


def filas_migracion(bd: Session) -> list[dict[str, object]]:
    """Prepara las ventas migradas para la tabla y el CSV de la vista.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Filas ordenadas con cliente, fechas, montos, utilidad y recaudo.
    """
    ultimos = _ultimo_recaudo(bd)
    filas: list[dict[str, object]] = []
    for venta in ventas_migradas(bd):
        utilidad, pago = _utilidad_reconocida(venta)
        filas.append(
            {
                "venta": venta,
                "utilidad": utilidad,
                "pago_proveedor": pago,
                "ultimo_recaudo": ultimos.get(venta.id_venta),
            }
        )
    return filas


def obtener_venta(bd: Session, id_venta: str) -> Venta | None:
    """Devuelve una orden por su identificador interno.

    Args:
        bd: Sesión de base de datos.
        id_venta: Identificador de la orden.

    Returns:
        La orden, o `None` si no existe.
    """
    return bd.get(Venta, id_venta)


def _venta_activa(bd: Session, id_venta: str) -> Venta:
    """Obtiene una orden que todavía puede recibir abonos.

    Args:
        bd: Sesión de base de datos.
        id_venta: Identificador de la orden.

    Returns:
        La orden activa.

    Raises:
        ValueError: Si no existe o está anulada.
    """
    venta = bd.get(Venta, id_venta)
    if venta is None:
        raise ValueError("La venta no existe.")
    if venta.estado_orden == ESTADO_ANULADA:
        raise ValueError("La orden está anulada y no admite abonos.")
    return venta


def _recalcular_estado_pago(venta: Venta) -> None:
    """Actualiza `estado_pago` según el saldo y lo abonado.

    Args:
        venta: Orden a actualizar; se modifica en sitio.
    """
    if venta.saldo_pendiente <= CERO:
        venta.estado_pago = ESTADO_PAGO_PAGADA
    elif venta.total_abonado > CERO:
        venta.estado_pago = ESTADO_PAGO_PARCIAL
    else:
        venta.estado_pago = ESTADO_PAGO_PENDIENTE


def _validar_metodo(metodo_pago: str) -> str:
    """Normaliza el medio de pago y verifica que esté permitido.

    Args:
        metodo_pago: Texto escrito o seleccionado.

    Returns:
        Medio en mayúsculas.

    Raises:
        ValueError: Si el medio no es Efectivo ni Transferencia.
    """
    metodo = metodo_pago.strip().upper()
    if metodo not in METODOS_PAGO:
        raise ValueError("El método de pago debe ser Efectivo o Transferencia.")
    return metodo


def registrar_abono(
    bd: Session,
    id_venta: str,
    monto: Decimal | str | int | float,
    metodo_pago: str = "EFECTIVO",
    fecha_abono: datetime | None = None,
) -> Abono:
    """Aplica un abono parcial o total a una orden activa.

    Args:
        bd: Sesión de base de datos.
        id_venta: Orden abonada.
        monto: Dinero recibido; positivo y no mayor al saldo.
        metodo_pago: `EFECTIVO` o `TRANSFERENCIA`.
        fecha_abono: Fecha y hora del pago; por defecto ahora (RF-06).

    Returns:
        El abono persistido.

    Raises:
        ValueError: Si la orden no existe o está anulada, el monto no es positivo
            o supera el saldo, o el medio de pago no es válido.
    """
    venta = _venta_activa(bd, id_venta)
    valor = _dinero(monto)
    if valor <= CERO:
        raise ValueError("El abono debe ser mayor que cero.")
    if valor > venta.saldo_pendiente:
        raise ValueError(
            "El abono no puede superar el saldo pendiente, que es "
            f"{formatear_pesos(venta.saldo_pendiente)}. Revisa el monto e "
            "inténtalo de nuevo."
        )
    metodo = _validar_metodo(metodo_pago)

    abono = Abono(
        id_venta=id_venta,
        monto=valor,
        metodo_pago=metodo,
        fecha_abono=fecha_abono or ahora_tienda(),
    )
    bd.add(abono)
    venta.total_abonado = redondear_dinero(venta.total_abonado + valor)
    venta.saldo_pendiente = redondear_dinero(venta.saldo_pendiente - valor)
    _recalcular_estado_pago(venta)
    bd.commit()
    bd.refresh(abono)
    return abono


def _devuelto(bd: Session, id_venta: str) -> Decimal:
    """Suma lo ya devuelto al cliente en una orden.

    Args:
        bd: Sesión de base de datos.
        id_venta: Orden consultada.

    Returns:
        Total devuelto, en cero si no hay devoluciones.
    """
    devoluciones = bd.scalars(
        select(DevolucionCliente).where(DevolucionCliente.id_venta == id_venta)
    ).all()
    return sum((d.monto for d in devoluciones), start=CERO)


def _registrar_devolucion(
    bd: Session,
    venta: Venta,
    monto: Decimal,
    metodo_pago: str,
) -> DevolucionCliente:
    """Agrega una devolución a una orden anulada sin superar lo abonado.

    Args:
        bd: Sesión de base de datos.
        venta: Orden anulada.
        monto: Valor a devolver; positivo.
        metodo_pago: `EFECTIVO` o `TRANSFERENCIA`.

    Returns:
        La devolución agregada.

    Raises:
        ValueError: Si el monto no es positivo o supera lo pendiente de devolver.
    """
    if monto <= CERO:
        raise ValueError("La devolución debe ser mayor que cero.")
    pendiente = redondear_dinero(venta.total_abonado - _devuelto(bd, venta.id_venta))
    if monto > pendiente:
        raise ValueError("La devolución supera el dinero abonado pendiente de devolver.")
    devolucion = DevolucionCliente(
        id_venta=venta.id_venta,
        fecha_devolucion=ahora_tienda(),
        monto=monto,
        metodo_pago=_validar_metodo(metodo_pago),
    )
    bd.add(devolucion)
    return devolucion


def anular_venta(
    bd: Session,
    id_venta: str,
    motivo: str,
    monto_devuelto: Decimal | str | int | float = CERO,
    metodo_devolucion: str = "EFECTIVO",
) -> Venta:
    """Anula una orden con motivo y registra la devolución si la hubo.

    La orden deja de contar en cartera, ganancia y rankings. El consecutivo se
    conserva. La deuda con el proveedor no se revierte (ADR-35). Si el cliente ya
    había abonado, `monto_devuelto` registra cuánto se le regresó. Lo que quede
    sin devolver puede registrarse después con `registrar_devolucion`.

    Args:
        bd: Sesión de base de datos.
        id_venta: Orden a anular.
        motivo: Razón de la anulación; obligatoria.
        monto_devuelto: Dinero devuelto ahora al cliente; por defecto cero.
        metodo_devolucion: Medio con el que se devuelve.

    Returns:
        La orden anulada.

    Raises:
        ValueError: Si la orden no existe, ya está anulada, el motivo está vacío
            o la devolución supera lo abonado.
    """
    venta = bd.get(Venta, id_venta)
    if venta is None:
        raise ValueError("La venta no existe.")
    if venta.estado_orden == ESTADO_ANULADA:
        raise ValueError("La orden ya está anulada.")
    motivo_limpio = motivo.strip()
    if not motivo_limpio:
        raise ValueError("Escriba el motivo de la anulación.")
    devolver = _dinero(monto_devuelto)
    if devolver < CERO:
        raise ValueError("La devolución no puede ser negativa.")
    if devolver > venta.total_abonado:
        raise ValueError("La devolución no puede superar lo abonado por el cliente.")

    venta.estado_orden = ESTADO_ANULADA
    venta.motivo_anulacion = motivo_limpio[:200]
    venta.fecha_anulacion = ahora_tienda()
    venta.saldo_pendiente = CERO
    venta.ganancia_neta = CERO
    if devolver > CERO:
        _registrar_devolucion(bd, venta, devolver, metodo_devolucion)
    bd.commit()
    bd.refresh(venta)
    return venta


def registrar_devolucion(
    bd: Session,
    id_venta: str,
    monto: Decimal | str | int | float,
    metodo_pago: str = "EFECTIVO",
) -> DevolucionCliente:
    """Registra una devolución pendiente de una orden ya anulada.

    Args:
        bd: Sesión de base de datos.
        id_venta: Orden anulada.
        monto: Dinero entregado al cliente.
        metodo_pago: `EFECTIVO` o `TRANSFERENCIA`.

    Returns:
        La devolución persistida.

    Raises:
        ValueError: Si la orden no existe, no está anulada, el monto no es válido
            o supera lo pendiente de devolver.
    """
    venta = bd.get(Venta, id_venta)
    if venta is None:
        raise ValueError("La venta no existe.")
    if venta.estado_orden != ESTADO_ANULADA:
        raise ValueError("Solo se registra devolución en órdenes anuladas.")
    devolucion = _registrar_devolucion(bd, venta, _dinero(monto), metodo_pago)
    bd.commit()
    bd.refresh(devolucion)
    return devolucion


def pendiente_devolver(bd: Session, venta: Venta) -> Decimal:
    """Calcula el dinero abonado de una orden anulada que aún no se devolvió.

    Args:
        bd: Sesión de base de datos.
        venta: Orden consultada.

    Returns:
        Monto pendiente, nunca negativo.
    """
    return redondear_dinero(max(venta.total_abonado - _devuelto(bd, venta.id_venta), CERO))


def obtener_abono(bd: Session, id_abono: str) -> Abono | None:
    """Devuelve un abono por su identificador.

    Args:
        bd: Sesión de base de datos.
        id_abono: Identificador del abono.

    Returns:
        El abono, o `None` si no existe.
    """
    return bd.get(Abono, id_abono)


def abonos_de_venta(bd: Session, id_venta: str) -> list[Abono]:
    """Lista los abonos de una orden en el orden en que se recibieron.

    Args:
        bd: Sesión de base de datos.
        id_venta: Orden consultada.

    Returns:
        Abonos ordenados por fecha y hora ascendente.
    """
    consulta = (
        select(Abono).where(Abono.id_venta == id_venta).order_by(Abono.fecha_abono, Abono.id_abono)
    )
    return list(bd.scalars(consulta))


def buscar_cartera(bd: Session, texto: str = "") -> list[Venta]:
    """Devuelve la cartera pendiente, opcionalmente filtrada (RF-06).

    El filtro busca en el nombre del cliente, en el celular y en el número de orden.

    Args:
        bd: Sesión de base de datos.
        texto: Fragmento a buscar; vacío devuelve toda la cartera.

    Returns:
        Órdenes activas con saldo, de la más antigua a la más reciente.
    """
    pendientes = cartera(bd)
    buscado = texto.strip().lower()
    if not buscado:
        return pendientes
    return [
        venta
        for venta in pendientes
        if buscado in venta.cliente_nombre.lower()
        or buscado in (venta.cliente_telefono or "")
        or buscado in str(venta.numero_orden)
    ]


def registrar_abono_proveedor(
    bd: Session,
    monto: Decimal | str | int | float,
    concepto: str = "Abono al proveedor",
) -> MovimientoProveedor:
    """Registra un pago al proveedor que reduce la deuda acumulada.

    Args:
        bd: Sesión de base de datos.
        monto: Dinero pagado al proveedor; positivo y no mayor a la deuda.
        concepto: Descripción del pago.

    Returns:
        El movimiento persistido.

    Raises:
        ValueError: Si el monto no es positivo o supera la deuda con el proveedor.
    """
    valor = _dinero(monto)
    if valor <= CERO:
        raise ValueError("El abono al proveedor debe ser mayor que cero.")
    if valor > deuda_proveedor(bd):
        raise ValueError("El abono supera la deuda con el proveedor.")
    movimiento = _registrar_movimiento_proveedor(bd, TIPO_ABONO_PROVEEDOR, valor, concepto)
    bd.commit()
    bd.refresh(movimiento)
    return movimiento


def registrar_deuda_inicial(
    bd: Session,
    monto: Decimal | str | int | float,
    concepto: str,
    proveedor_nombre: str | None = None,
    fecha_deuda: str | date | None = None,
    referencia_factura: str | None = None,
) -> MovimientoProveedor:
    """Registra una deuda con el proveedor anterior al sistema (SRS v4.44, §8.1).

    Suma de inmediato al saldo adeudado y queda en el libro como `DEUDA_INICIAL`,
    sin orden asociada. Es la única forma de crear un movimiento sin venta que
    aumenta la deuda. La SRS de Migración de Cartera añade tres datos opcionales
    de trazabilidad: proveedor, fecha real y referencia de factura.

    Args:
        bd: Sesión de base de datos.
        monto: Valor adeudado; debe ser mayor que cero.
        concepto: Descripción escrita por el administrador.
        proveedor_nombre: Nombre del proveedor; opcional.
        fecha_deuda: Fecha real de la deuda; vacía usa hoy.
        referencia_factura: Número o referencia de la factura; opcional.

    Returns:
        El movimiento persistido.

    Raises:
        ValueError: Si el monto no es positivo, el concepto está vacío o la fecha
            no es válida.
    """
    descripcion = (concepto or "").strip()
    if not descripcion:
        raise ValueError("Escribe el concepto de la deuda anterior al sistema.")
    valor = _dinero(monto)
    if valor <= CERO:
        raise ValueError("El valor adeudado debe ser mayor que cero.")
    fecha = _fecha_compra(fecha_deuda) if fecha_deuda else None
    movimiento = _registrar_movimiento_proveedor(
        bd,
        TIPO_DEUDA_INICIAL,
        valor,
        descripcion,
        proveedor_nombre=proveedor_nombre,
        fecha_deuda=fecha,
        referencia_factura=referencia_factura,
    )
    bd.commit()
    bd.refresh(movimiento)
    return movimiento


def listar_movimientos_proveedor(bd: Session) -> list[MovimientoProveedor]:
    """Lista el libro de la cuenta por pagar, del más reciente al más antiguo.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Movimientos ordenados por fecha descendente.
    """
    consulta = select(MovimientoProveedor).order_by(MovimientoProveedor.fecha.desc())
    return list(bd.scalars(consulta))


def listar_movimientos_con_orden(bd: Session) -> list[dict[str, object]]:
    """Movimientos del proveedor con cliente y producto de su orden (SRS v4.44, §7.3).

    Un movimiento sin orden vinculada (abono o deuda inicial) muestra «—» en
    cliente y producto. Para una compra a crédito se toma el cliente de la orden y
    los nombres de sus líneas de detalle, separados por coma.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Lista de diccionarios ordenada del más reciente al más antiguo, con las
        claves `id_movimiento`, `fecha`, `tipo`, `cliente`, `producto`,
        `concepto`, `monto`, `saldo_resultante`, `proveedor_nombre`,
        `fecha_deuda` y `referencia_factura`.
    """
    movimientos = listar_movimientos_proveedor(bd)
    ids_venta = {movimiento.id_venta for movimiento in movimientos if movimiento.id_venta}
    clientes: dict[str, str] = {}
    productos: dict[str, list[str]] = {}
    if ids_venta:
        for venta in bd.scalars(select(Venta).where(Venta.id_venta.in_(ids_venta))):
            clientes[venta.id_venta] = venta.cliente_nombre
        detalles = bd.scalars(
            select(VentaDetalle)
            .where(VentaDetalle.id_venta.in_(ids_venta))
            .order_by(VentaDetalle.id_venta)
        )
        for detalle in detalles:
            productos.setdefault(detalle.id_venta, []).append(detalle.producto_nombre)

    filas: list[dict[str, object]] = []
    for movimiento in movimientos:
        orden = movimiento.id_venta
        filas.append(
            {
                "id_movimiento": movimiento.id_movimiento,
                "fecha": movimiento.fecha,
                "tipo": movimiento.tipo,
                "etiqueta": etiqueta_tipo_movimiento(movimiento.tipo),
                "cliente": clientes.get(orden, "—") if orden else "—",
                "producto": (", ".join(productos.get(orden, [])) or "—") if orden else "—",
                "concepto": movimiento.concepto,
                "monto": movimiento.monto,
                "saldo_resultante": movimiento.saldo_resultante,
                "proveedor_nombre": movimiento.proveedor_nombre,
                "fecha_deuda": movimiento.fecha_deuda,
                "referencia_factura": movimiento.referencia_factura,
            }
        )
    return filas


def _fecha_gasto(texto: str | date | None) -> date:
    """Convierte la fecha de un gasto operativo; vacía usa el día de la tienda.

    Args:
        texto: Fecha en formato `AAAA-MM-DD`, un `date`, o vacío.

    Returns:
        La fecha normalizada.

    Raises:
        ValueError: Si el texto no es una fecha válida.
    """
    if isinstance(texto, date):
        return texto
    limpio = (texto or "").strip()
    if not limpio:
        return datetime.now(ZONA_TIENDA).date()
    try:
        return date.fromisoformat(limpio)
    except ValueError as error:
        raise ValueError("La fecha del gasto operativo no es válida.") from error


def registrar_gasto_operativo(
    bd: Session,
    monto: Decimal | str | int | float,
    fecha: str | date | None = None,
) -> GastoOperativo:
    """Registra un gasto operativo de la tienda (SRS v4.44, §8.2).

    No toca la deuda con el proveedor: solo se descuenta de la ganancia.

    Args:
        bd: Sesión de base de datos.
        monto: Valor del gasto; debe ser mayor que cero.
        fecha: Fecha del gasto; vacía usa hoy en hora de la tienda.

    Returns:
        El gasto persistido.

    Raises:
        ValueError: Si el monto no es positivo o la fecha no es válida.
    """
    valor = _dinero(monto)
    if valor <= CERO:
        raise ValueError("El valor del gasto operativo debe ser mayor que cero.")
    gasto = GastoOperativo(fecha=_fecha_gasto(fecha), monto=valor)
    bd.add(gasto)
    bd.commit()
    bd.refresh(gasto)
    return gasto


def actualizar_gasto_operativo(
    bd: Session,
    id_gasto: str,
    monto: Decimal | str | int | float,
    fecha: str | date | None = None,
) -> GastoOperativo:
    """Corrige la fecha y el valor de un gasto operativo.

    Args:
        bd: Sesión de base de datos.
        id_gasto: Gasto a modificar.
        monto: Nuevo valor; debe ser mayor que cero.
        fecha: Nueva fecha; vacía conserva la actual.

    Returns:
        El gasto actualizado.

    Raises:
        ValueError: Si el gasto no existe, el monto no es positivo o la fecha
            no es válida.
    """
    gasto = bd.get(GastoOperativo, id_gasto)
    if gasto is None:
        raise ValueError("El gasto operativo ya no existe.")
    valor = _dinero(monto)
    if valor <= CERO:
        raise ValueError("El valor del gasto operativo debe ser mayor que cero.")
    gasto.monto = valor
    if fecha not in (None, ""):
        gasto.fecha = _fecha_gasto(fecha)
    bd.commit()
    bd.refresh(gasto)
    return gasto


def eliminar_gasto_operativo(bd: Session, id_gasto: str) -> None:
    """Borra un gasto operativo y deja que las estadísticas se recalculen.

    Args:
        bd: Sesión de base de datos.
        id_gasto: Gasto a eliminar.

    Raises:
        ValueError: Si el gasto no existe.
    """
    gasto = bd.get(GastoOperativo, id_gasto)
    if gasto is None:
        raise ValueError("El gasto operativo ya no existe.")
    bd.delete(gasto)
    bd.commit()


def listar_gastos_operativos(bd: Session) -> list[GastoOperativo]:
    """Lista los gastos operativos del más reciente al más antiguo.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Gastos ordenados por fecha y luego por creación, ambos descendentes.
    """
    consulta = select(GastoOperativo).order_by(
        GastoOperativo.fecha.desc(), GastoOperativo.creado_en.desc()
    )
    return list(bd.scalars(consulta))


def total_gastos_operativos(
    bd: Session, anio: int | None = None, mes: int | None = None
) -> Decimal:
    """Suma los gastos operativos de un periodo.

    Args:
        bd: Sesión de base de datos.
        anio: Año a sumar; `None` suma todo el histórico.
        mes: Mes a sumar (1 a 12); `None` suma el año completo.

    Returns:
        Total redondeado; cero si no hay gastos.
    """
    consulta = select(GastoOperativo)
    if anio is not None:
        inicio = date(anio, mes or 1, 1)
        if mes is None or mes == 12:
            fin = date(anio + 1, 1, 1)
        else:
            fin = date(anio, mes + 1, 1)
        consulta = consulta.where(GastoOperativo.fecha >= inicio, GastoOperativo.fecha < fin)
    total = sum((gasto.monto for gasto in bd.scalars(consulta)), start=CERO)
    return redondear_dinero(total)


def _texto_busqueda(texto: str) -> str:
    """Normaliza un texto para comparar búsquedas: sin tildes y en minúsculas.

    Args:
        texto: Texto original.

    Returns:
        Texto normalizado.
    """
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return sin_tildes.lower().strip()


def filtrar_ventas(ventas: list[Venta], consulta: str | None) -> list[Venta]:
    """Filtra órdenes por número, cliente o fecha de venta (SRS v1.8, bloque 6).

    La fecha se acepta como dd-mm-aaaa, dd/mm/aaaa o aaaa-mm-dd, completa o parcial.
    Una consulta vacía devuelve todas las órdenes.

    Args:
        ventas: Órdenes ya ordenadas.
        consulta: Texto que escribe la persona.

    Returns:
        Órdenes que coinciden, en el mismo orden.
    """
    buscado = _texto_busqueda(consulta or "")
    if not buscado:
        return list(ventas)
    compacto = re.sub(r"[\s/.]+", "-", buscado)
    resultado: list[Venta] = []
    for venta in ventas:
        fecha = venta.fecha_venta
        fechas = [
            fecha.strftime("%d-%m-%Y"),
            fecha.strftime("%Y-%m-%d"),
            fecha.strftime("%d/%m/%Y"),
        ]
        candidatos = [
            str(venta.numero_orden),
            _texto_busqueda(venta.cliente_nombre),
            *[_texto_busqueda(f) for f in fechas],
        ]
        if any(buscado in candidato or compacto in candidato for candidato in candidatos):
            resultado.append(venta)
    return resultado


def listar_ventas(bd: Session) -> list[Venta]:
    """Lista las órdenes de la más reciente a la más antigua por consecutivo.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Órdenes activas y anuladas.
    """
    return list(bd.scalars(select(Venta).order_by(Venta.numero_orden.desc())))


def cartera(bd: Session) -> list[Venta]:
    """Devuelve las órdenes activas con saldo pendiente.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Órdenes ordenadas por fecha ascendente (las más viejas primero).
    """
    consulta = (
        select(Venta)
        .where(Venta.saldo_pendiente > CERO, Venta.estado_orden == ESTADO_ACTIVA)
        .order_by(Venta.fecha_venta)
    )
    return list(bd.scalars(consulta))


def resumen_cartera(bd: Session) -> dict[str, Decimal]:
    """Consolida cartera, deuda, caja y efectivo libre (RF-09 y RF-10).

    Definiciones:
    - Cartera: saldo pendiente de las órdenes activas.
    - Caja recaudada: abonos de clientes − devoluciones − abonos al proveedor.
    - Balance: cartera − deuda con el proveedor.
    - Efectivo libre: caja recaudada − deuda con el proveedor.

    Un valor negativo indica déficit y se muestra en rojo en la vista.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Diccionario con los indicadores en `Decimal`.
    """
    ventas = list(bd.scalars(select(Venta)))
    cartera_clientes = sum(
        (v.saldo_pendiente for v in ventas if v.estado_orden == ESTADO_ACTIVA), start=CERO
    )
    abonos_clientes = sum(
        (abono.monto for abono in bd.scalars(select(Abono))), start=CERO
    )
    devoluciones = sum(
        (d.monto for d in bd.scalars(select(DevolucionCliente))), start=CERO
    )
    abonos_proveedor = sum(
        (
            m.monto
            for m in bd.scalars(select(MovimientoProveedor))
            if m.tipo == TIPO_ABONO_PROVEEDOR
        ),
        start=CERO,
    )
    deuda = deuda_proveedor(bd)
    caja = abonos_clientes - devoluciones - abonos_proveedor
    return {
        "cartera_clientes": redondear_dinero(cartera_clientes),
        "deuda_proveedor": deuda,
        "balance": redondear_dinero(cartera_clientes - deuda),
        "caja_recaudada": redondear_dinero(caja),
        "efectivo_libre": redondear_dinero(caja - deuda),
        # SRS v2.0, sección 4: se exponen las dos piernas del efectivo para
        # calcular «dinero neto en caja» sin contar las devoluciones, que son un
        # indicador distinto. Los cinco indicadores anteriores no se tocan.
        "abonos_clientes": redondear_dinero(abonos_clientes),
        "abonos_proveedor": redondear_dinero(abonos_proveedor),
    }


def estado_garantia(venta: Venta, hoy: date) -> tuple[str, int]:
    """Calcula el semáforo de garantía de una orden (RF-05).

    Args:
        venta: Orden consultada.
        hoy: Fecha local de referencia.

    Returns:
        Tupla con `VERDE` si la garantía sigue vigente, `ROJO` si venció o
        `SIN_GARANTIA` si la orden no tiene fecha de fin; y los días restantes
        (negativos si ya venció).
    """
    if venta.garantia_fecha_fin is None:
        return ESTADO_GARANTIA_SIN, 0
    dias = (venta.garantia_fecha_fin - hoy).days
    return ("VERDE" if dias >= 0 else "ROJO"), dias


def clasificar_saldo(valor: Decimal) -> tuple[str, str]:
    """Da el texto y la clase de color de un saldo del módulo de cartera (RF-10).

    Un déficit se muestra en rojo con signo menos; un superávit, en verde. El signo
    menos y los colores se usan solo en este módulo: en el resto de la app los
    montos negativos no llevan signo.

    Args:
        valor: Saldo a mostrar.

    Returns:
        Tupla con el texto (por ejemplo `−$20.000`) y la clase CSS (`valor-negativo`,
        `valor-positivo` o vacía si es cero).
    """
    if valor < CERO:
        return f"−{formatear_pesos(-valor)}", "valor-negativo"
    if valor == CERO:
        return formatear_pesos(valor), ""
    return formatear_pesos(valor), "valor-positivo"


def _barra_divergente(
    etiqueta: str,
    valor: Decimal,
    color: str,
    color_negativo: str,
    referencia: Decimal,
    nota: str = "",
) -> dict[str, object]:
    """Prepara una barra horizontal respecto al eje central $0.

    Args:
        etiqueta: Texto visible a la izquierda de la barra.
        valor: Monto con signo; negativo apunta a la izquierda y se pinta en rojo.
        color: Color de la barra cuando el valor es positivo o cero.
        color_negativo: Color obligatorio cuando el valor es negativo.
        referencia: Valor mayor del bloque, para escalar el ancho.
        nota: Texto auxiliar opcional bajo la barra.

    Returns:
        Diccionario con etiqueta, texto, color, ancho y dirección.
    """
    negativo = valor < CERO
    ancho = 0
    if referencia > CERO:
        # El eje está al 50 %: el ancho máximo de cada lado es 50 %.
        ancho = int(min(abs(valor) / referencia * 50, 50))
    texto, clase = clasificar_saldo(valor)
    return {
        "etiqueta": etiqueta,
        "texto": texto,
        "clase": clase,
        "color": color_negativo if negativo else color,
        "ancho": ancho,
        "direccion": "izquierda" if negativo else "derecha",
        "nota": nota,
    }


def balance_tres_bloques(resumen: dict[str, Decimal]) -> dict[str, object]:
    """Construye los datos del panel «Balance de Cartera y Efectivo» (SRS v2.0).

    Bloque A (cuentas): cartera por cobrar, deuda con el proveedor y saldo neto.
    Bloque B (efectivo): entradas menos salidas, y caja menos deudas.
    Bloque C: utilidad proyectada al liquidar las cuentas pendientes.

    Los saldos negativos apuntan a la izquierda y se pintan siempre en rojo; el
    resto apunta a la derecha. El texto del bloque C se elige según el estado de
    la cartera y la caja, con los importes literales de la SRS.

    Args:
        resumen: Indicadores devueltos por `resumen_cartera`.

    Returns:
        Diccionario con los tres bloques y el mensaje explicativo final.
    """
    cartera = redondear_dinero(resumen["cartera_clientes"])
    deuda = redondear_dinero(resumen["deuda_proveedor"])
    saldo_cartera = redondear_dinero(cartera - deuda)
    caja = redondear_dinero(
        resumen["abonos_clientes"] - resumen["abonos_proveedor"]
    )
    disponible = redondear_dinero(caja - deuda)
    ganancia = redondear_dinero(saldo_cartera + caja)

    referencia_a = max(cartera, deuda, abs(saldo_cartera), CERO)
    referencia_b = max(abs(caja), abs(disponible), CERO)
    bloque_a = [
        _barra_divergente("Por cobrar a clientes", cartera, "#3B82F6", "#EF4444", referencia_a),
        _barra_divergente("Por pagar a proveedores", deuda, "#F59E0B", "#EF4444", referencia_a),
        _barra_divergente(
            "Saldo neto de cartera",
            saldo_cartera,
            "#10B981",
            "#EF4444",
            referencia_a,
            "Resultado de lo que te deben menos lo que debes",
        ),
    ]
    bloque_b = [
        _barra_divergente(
            "Dinero neto en caja (Entradas - Salidas)",
            caja,
            "#10B981",
            "#EF4444",
            referencia_b,
        ),
        _barra_divergente(
            "Disponible real (Caja - Deudas)",
            disponible,
            "#10B981",
            "#EF4444",
            referencia_b,
        ),
    ]
    signo = "+" if ganancia >= CERO else "−"
    texto_ganancia = f"{signo}{formatear_pesos(abs(ganancia))}"
    bloque_c = {
        "etiqueta": "Ganancia final proyectada",
        "texto": texto_ganancia,
        "clase": "valor-positivo" if ganancia >= CERO else "valor-negativo",
        "color": "#10B981" if ganancia >= CERO else "#EF4444",
        "direccion": "derecha" if ganancia >= CERO else "izquierda",
        "ancho": 50,
    }

    if cartera > CERO and caja < CERO:
        mensaje = (
            f"Al cobrar los {formatear_pesos(cartera)} pendientes, recuperarás "
            f"tu inversión adelantada de {formatear_pesos(abs(caja))} y te "
            f"quedarán {formatear_pesos(ganancia)} de ganancia"
        )
    elif cartera == CERO:
        mensaje = (
            f"Has recaudado el 100% de tus ventas; tu utilidad real obtenida "
            f"es de {formatear_pesos(ganancia)}"
        )
    else:
        mensaje = (
            f"Te faltan {formatear_pesos(cartera)} por cobrar y tienes "
            f"{formatear_pesos(caja)} en caja; tu utilidad proyectada es de "
            f"{formatear_pesos(ganancia)}"
        )

    return {
        "bloque_a": bloque_a,
        "bloque_b": bloque_b,
        "bloque_c": bloque_c,
        "mensaje": mensaje,
    }


def barras_balance(resumen: dict[str, Decimal]) -> list[dict[str, object]]:
    """Calcula las barras horizontales del balance de cartera (RF-09 y RF-10).

    Cada barra es proporcional al mayor valor absoluto. Si hay déficits, el cero se
    dibuja en el centro: los valores positivos crecen a la derecha y los negativos a
    la izquierda. Los saldos de balance y efectivo llevan signo y color (RF-10).

    Args:
        resumen: Indicadores de `resumen_cartera`.

    Returns:
        Filas con etiqueta, texto del valor, clase, color y la posición de la barra
        en porcentaje (`izquierda` y `ancho`).
    """
    definiciones = [
        ("Total adeudado por clientes", resumen["cartera_clientes"], "var(--accent-blue)", False),
        ("Total adeudado al proveedor", resumen["deuda_proveedor"], "var(--accent-amber)", False),
        ("Balance de cartera", resumen["balance"], None, True),
        ("Caja recaudada", resumen["caja_recaudada"], "var(--accent-blue)", False),
        ("Efectivo libre real", resumen["efectivo_libre"], None, True),
    ]
    maximo = max((abs(valor) for _, valor, _, _ in definiciones), default=CERO)
    hay_negativos = any(valor < CERO for _, valor, _, _ in definiciones)

    filas: list[dict[str, object]] = []
    for etiqueta, valor, color, con_signo in definiciones:
        if con_signo:
            texto_valor, clase = clasificar_saldo(valor)
            color = color or ("var(--accent-green)" if valor >= CERO else "var(--accent-red)")
        else:
            texto_valor, clase = formatear_pesos(valor), ""

        if maximo == CERO:
            izquierda, ancho = 0.0, 0.0
        elif hay_negativos:
            mitad = float(abs(valor) / maximo * 50)
            izquierda, ancho = (50.0, mitad) if valor >= CERO else (50.0 - mitad, mitad)
        else:
            izquierda, ancho = 0.0, float(abs(valor) / maximo * 100)

        filas.append(
            {
                "etiqueta": etiqueta,
                "texto": texto_valor,
                "clase": clase,
                "color": color,
                "izquierda": round(izquierda, 2),
                "ancho": round(ancho, 2),
                "hay_negativos": hay_negativos,
            }
        )
    return filas


def segmentos_dona(cartera_clientes: Decimal, deuda: Decimal) -> list[dict[str, object]]:
    """Calcula los arcos de la gráfica tipo dona de cartera y deuda (RF-11).

    Los arcos suman 100 unidades sobre una circunferencia de longitud 100 (radio
    100 / 2π), así que el porcentaje es directamente la longitud del trazo SVG. El
    balance se muestra en el centro, no como arco, porque restar la deuda de la
    cartera no es una proporción del total.

    Args:
        cartera_clientes: Saldo pendiente de clientes.
        deuda: Deuda con el proveedor.

    Returns:
        Lista con un diccionario por arco. Vacía si no hay cartera ni deuda. Cada
        arco incluye `clase`, el color verde o rojo de la cifra en la leyenda.
    """
    cartera_positiva = max(cartera_clientes, CERO)
    deuda_positiva = max(deuda, CERO)
    total = cartera_positiva + deuda_positiva
    if total <= CERO:
        return []

    arcos: list[dict[str, object]] = []
    avance = 0.0
    # SRS v1.8: la leyenda usa la paleta de referencia. La cartera es dinero a
    # favor (verde) y la deuda con el proveedor es dinero en contra (rojo).
    for etiqueta, valor, color, clase in (
        ("Cartera por cobrar", cartera_positiva, "var(--accent-blue)", "valor-positivo"),
        ("Deuda con proveedor", deuda_positiva, "var(--accent-amber)", "valor-negativo"),
    ):
        porcentaje = float(valor / total * 100)
        arcos.append(
            {
                "etiqueta": etiqueta,
                "valor": formatear_pesos(valor),
                "porcentaje": round(porcentaje, 1),
                "longitud": round(porcentaje, 4),
                "desplazamiento": round(-avance, 4),
                "color": color,
                "clase": clase,
            }
        )
        avance += porcentaje
    return arcos


ESTADOS_GARANTIA = ("ABIERTA", "EN_TRAMITE", "RESUELTA", "RECHAZADA")
ESTADOS_FINALES_GARANTIA = ("RESUELTA", "RECHAZADA")


def etiqueta_producto(nombre: str, categoria: str | None) -> str:
    """Forma el nombre con el que un producto aparece en garantías y ranking.

    Args:
        nombre: Nombre del producto tal como se vendió.
        categoria: Categoría opcional del producto.

    Returns:
        Texto como `Audífonos BT (Audio)`, o solo el nombre si no hay categoría.
    """
    return f"{nombre} ({categoria})" if categoria else nombre


def opciones_garantia(bd: Session) -> list[dict[str, str]]:
    """Lista las líneas de órdenes activas sobre las que se puede reclamar garantía.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Opciones con el id de la línea y un texto legible, de la orden más reciente
        a la más antigua.
    """
    consulta = (
        select(VentaDetalle, Venta)
        .join(Venta, Venta.id_venta == VentaDetalle.id_venta)
        .where(Venta.estado_orden == ESTADO_ACTIVA)
        .order_by(Venta.numero_orden.desc())
    )
    return [
        {
            "id_detalle": detalle.id_detalle,
            "texto": (
                f"No. {venta.numero_orden} · {venta.cliente_nombre} · "
                f"{etiqueta_producto(detalle.producto_nombre, detalle.categoria)}"
            ),
        }
        for detalle, venta in bd.execute(consulta).all()
    ]


def registrar_garantia(bd: Session, id_detalle: str, observacion: str = "") -> GarantiaProveedor:
    """Abre un reclamo de garantía sobre una línea vendida (RF-05).

    Args:
        bd: Sesión de base de datos.
        id_detalle: Línea con la falla.
        observacion: Descripción de la falla; opcional.

    Returns:
        El reclamo persistido en estado `ABIERTA`.

    Raises:
        ValueError: Si la línea no existe o la orden está anulada.
    """
    detalle = bd.get(VentaDetalle, id_detalle)
    if detalle is None:
        raise ValueError("La línea de venta no existe.")
    venta = bd.get(Venta, detalle.id_venta)
    if venta is None or venta.estado_orden == ESTADO_ANULADA:
        raise ValueError("La orden está anulada y no admite garantías.")

    garantia = GarantiaProveedor(
        id_venta=venta.id_venta,
        id_detalle=detalle.id_detalle,
        producto_referencia=etiqueta_producto(detalle.producto_nombre, detalle.categoria)[:120],
        estado_tramite="ABIERTA",
        fecha_reclamo=ahora_tienda(),
        observacion=observacion.strip()[:300] or None,
    )
    bd.add(garantia)
    bd.commit()
    bd.refresh(garantia)
    return garantia


def actualizar_estado_garantia(
    bd: Session, id_garantia: str, estado: str, observacion: str = ""
) -> GarantiaProveedor:
    """Avanza un reclamo por su trámite con el proveedor.

    El flujo es ABIERTA → EN_TRAMITE → RESUELTA o RECHAZADA. Un reclamo cerrado no
    se reabre: si la falla vuelve, se registra un reclamo nuevo.

    Args:
        bd: Sesión de base de datos.
        id_garantia: Reclamo a actualizar.
        estado: Nuevo estado.
        observacion: Nota del trámite; si está vacía se conserva la anterior.

    Returns:
        El reclamo actualizado.

    Raises:
        ValueError: Si el reclamo no existe, el estado no es válido, el reclamo ya
            está cerrado o se intenta volver a `ABIERTA`.
    """
    garantia = bd.get(GarantiaProveedor, id_garantia)
    if garantia is None:
        raise ValueError("El reclamo de garantía no existe.")
    nuevo = estado.strip().upper()
    if nuevo not in ESTADOS_GARANTIA:
        raise ValueError("El estado de la garantía no es válido.")
    if garantia.estado_tramite in ESTADOS_FINALES_GARANTIA:
        raise ValueError("Este reclamo ya está cerrado. Si la falla vuelve, registre un reclamo nuevo.")
    if nuevo == "ABIERTA":
        raise ValueError("Un reclamo no vuelve a estado abierto.")

    garantia.estado_tramite = nuevo
    if nuevo in ESTADOS_FINALES_GARANTIA:
        garantia.fecha_resolucion = ahora_tienda()
    if observacion.strip():
        garantia.observacion = observacion.strip()[:300]
    bd.commit()
    bd.refresh(garantia)
    return garantia


def listar_garantias(bd: Session) -> list[GarantiaProveedor]:
    """Lista los reclamos de garantía del más reciente al más antiguo.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Reclamos ordenados por fecha de reclamo descendente.
    """
    consulta = select(GarantiaProveedor).order_by(GarantiaProveedor.fecha_reclamo.desc())
    return list(bd.scalars(consulta))


def garantia_vigente_al_reclamo(venta: Venta, fecha_reclamo: datetime) -> bool:
    """Indica si un reclamo se hizo dentro del plazo de garantía de la orden.

    Args:
        venta: Orden de la línea reclamada.
        fecha_reclamo: Momento del reclamo.

    Returns:
        `True` si el día del reclamo no supera la fecha de fin de garantía.
    """
    if venta.garantia_fecha_fin is None:
        return False
    return fecha_reclamo.date() <= venta.garantia_fecha_fin


def ranking_fallas(bd: Session) -> list[dict[str, object]]:
    """Calcula la tasa de fallas por producto (RF-05).

    Tasa (%) = reclamos / unidades vendidas × 100. Solo cuentan las órdenes activas:
    una orden anulada no vende ni genera garantías en el indicador. Un producto con
    fallas y sin unidades activas aparece con tasa `None` (se muestra como «—»).

    Args:
        bd: Sesión de base de datos.

    Returns:
        Filas con producto, unidades, fallas y tasa, de la tasa más alta a la más baja.
    """
    unidades: dict[str, int] = {}
    consulta_ventas = (
        select(VentaDetalle)
        .join(Venta, Venta.id_venta == VentaDetalle.id_venta)
        .where(Venta.estado_orden == ESTADO_ACTIVA)
    )
    for detalle in bd.scalars(consulta_ventas):
        etiqueta = etiqueta_producto(detalle.producto_nombre, detalle.categoria)
        unidades[etiqueta] = unidades.get(etiqueta, 0) + detalle.cantidad

    fallas: dict[str, int] = {}
    consulta_garantias = (
        select(GarantiaProveedor)
        .join(Venta, Venta.id_venta == GarantiaProveedor.id_venta)
        .where(Venta.estado_orden == ESTADO_ACTIVA)
    )
    for garantia in bd.scalars(consulta_garantias):
        fallas[garantia.producto_referencia] = fallas.get(garantia.producto_referencia, 0) + 1

    filas: list[dict[str, object]] = []
    for producto in set(unidades) | set(fallas):
        vendidas = unidades.get(producto, 0)
        reclamos = fallas.get(producto, 0)
        tasa = (Decimal(reclamos) / Decimal(vendidas) * 100).quantize(Decimal("0.1")) if vendidas else None
        filas.append(
            {"producto": producto, "unidades": vendidas, "fallas": reclamos, "tasa": tasa}
        )
    filas.sort(
        key=lambda fila: (
            fila["tasa"] is None,
            -(fila["tasa"] or CERO),
            -int(fila["fallas"]),
            str(fila["producto"]),
        )
    )
    return filas


def formatear_pesos(valor: Decimal | int | float) -> str:
    """Formatea un monto en pesos colombianos sin centavos (ADR-23).

    Args:
        valor: Monto a mostrar.

    Returns:
        Texto como `$1.250.000`.
    """
    return f"${valor:,.0f}".replace(",", ".")


def texto_compartir_factura(venta: Venta) -> str:
    """Redacta el mensaje que acompaña a la factura enviada por WhatsApp.

    El PDF viaja como archivo adjunto; el texto solo saluda y anuncia el adjunto.

    Args:
        venta: Orden facturada.

    Returns:
        Texto como «Hola Ana Pérez, adjunto tu factura de compra.».
    """
    return f"Hola {venta.cliente_nombre}, adjunto tu factura de compra."


def enlace_whatsapp_factura(venta: Venta) -> str:
    """Construye el enlace de WhatsApp con el mensaje de la factura.

    Es el respaldo cuando el navegador no puede adjuntar el PDF: abre el chat del
    cliente con el texto listo y el PDF se adjunta desde la descarga.

    Args:
        venta: Orden facturada; usa el celular guardado en la orden.

    Returns:
        URL de `wa.me`. Sin celular se devuelve un enlace sin destinatario.
    """
    return _enlace_wa(venta.cliente_telefono, texto_compartir_factura(venta))


def enlace_whatsapp_recibo(venta: Venta, abono: Abono) -> str:
    """Construye el enlace de WhatsApp con el recibo de un abono (RF-07).

    El mensaje reproduce lo que muestra el recibo: monto, medio, fecha y hora, y el
    saldo que queda, o un aviso de saldo total si la orden quedó pagada.

    Args:
        venta: Orden abonada.
        abono: Abono que se comparte.

    Returns:
        URL de `wa.me` con el mensaje prellenado.
    """
    fecha = abono.fecha_abono.strftime("%d/%m/%Y %H:%M")
    if venta.saldo_pendiente <= CERO:
        cierre = "¡Saldo total cancelado! Gracias por tu compra."
    else:
        cierre = f"Saldo pendiente: {formatear_pesos(venta.saldo_pendiente)}"
    texto = (
        f"Recibo de abono OLB_BYTE\n"
        f"Factura No. {venta.numero_orden} · {venta.cliente_nombre}\n"
        f"Abono: {formatear_pesos(abono.monto)} ({abono.metodo_pago.capitalize()})\n"
        f"Fecha: {fecha}\n"
        f"{cierre}"
    )
    return _enlace_wa(venta.cliente_telefono, texto)


def enlace_whatsapp_cobro(venta: Venta) -> str:
    """Construye el enlace de WhatsApp con un recordatorio de cobro (RF-06).

    Args:
        venta: Orden con saldo pendiente.

    Returns:
        URL de `wa.me` con el mensaje prellenado.
    """
    texto = (
        f"Hola {venta.cliente_nombre}, te recordamos el saldo pendiente de la "
        f"factura No. {venta.numero_orden} en OLB_BYTE: "
        f"{formatear_pesos(venta.saldo_pendiente)}. ¡Gracias!"
    )
    return _enlace_wa(venta.cliente_telefono, texto)


def _enlace_wa(telefono: str | None, texto: str) -> str:
    """Arma la URL de `wa.me` anteponiendo el indicativo 57 al celular.

    Args:
        telefono: Celular de 10 dígitos o `None`.
        texto: Mensaje a prellenar.

    Returns:
        URL codificada para abrir WhatsApp.
    """
    base = f"https://wa.me/57{telefono}" if telefono else "https://wa.me/"
    return f"{base}?text={quote(texto)}"
