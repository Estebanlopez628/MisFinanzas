"""Analítica de OLB_BYTE: reportes, clientes VIP, costos y tablas exportables.

Responsabilidad
---------------
- Agrupar ventas por mes y por año: cantidad, ingresos, costos, ganancia y
  variación frente al periodo anterior (RF-12).
- Calcular la rentabilidad anual: ganancia ÷ costo × 100 (RF-12).
- Ordenar a los clientes por monto y frecuencia para fidelización (RF-13).
- Detectar subidas de costo del proveedor por producto y el margen que queda con
  el último precio de venta (RF-14).
- Aplicar un `Filtro` común (mes, cliente y producto) a todas las tablas (SRS v1.9).
  Lo que se ve en pantalla es lo mismo que se descarga en CSV, porque ambas cosas
  salen de estas mismas funciones.
- Listar cada producto vendido en una fila, con saldo y abonos repartidos en
  proporción a su total (ADR-55).

Reglas comunes (ADR-35):
- Los ingresos, la ganancia y los rankings excluyen las órdenes anuladas.
- El historial de costos incluye todas las compras, anuladas incluidas, porque la
  mercancía se compró aunque la orden se haya anulado.
- Los meses y años se toman de la fecha de venta guardada en hora de la tienda.
- Un mes filtrado se compara por (año, mes) y no por fecha completa, para no mezclar
  fechas con y sin zona horaria.

Todo el cálculo usa `Decimal`; los porcentajes se redondean a un decimal. Este módulo
no escribe en la base de datos.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.modelos import GastoOperativo, MovimientoProveedor, Venta, VentaDetalle
from app.servicios.comercial import (
    CERO,
    ESTADO_ACTIVA,
    TIPO_ABONO_PROVEEDOR,
    TIPO_COMPRA,
    TIPO_DEUDA_INICIAL,
    etiqueta_producto,
)

# Denominación de la columna en tablas y en el CSV (SRS v4.44, decisión final).
PASIVO_ANTIGUO_LABEL = "PASIVO ANTIGUO"

MESES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
UNO = Decimal("0.1")
# Por debajo de este margen el precio apenas cubre costos operativos y conviene
# revisarlo. El valor es una decisión de negocio, no un dato legal.
UMBRAL_MARGEN_BAJO = Decimal("15")
GARANTIA_ACTIVA = "Activa"
GARANTIA_VENCIDA = "Vencida"
GARANTIA_SIN_FECHA = "Sin garantía"
TABLAS_CSV = ("mensual", "anual", "vip", "alertas", "costos", "ventas")


@dataclass(frozen=True)
class Filtro:
    """Selección que comparten todas las tablas de la analítica (SRS v1.9).

    La regla es la misma para todas: el cliente y el producto filtran cualquier
    tabla que tenga esa dimensión; el mes, si se elige, restringe las tablas que
    muestran datos de un periodo. El año solo define la tabla mensual y el listado
    de ventas del mes.

    Attributes:
        anio: Año de la tabla mensual y de las ventas del mes; `None` = todos.
        mes: Mes elegido (1 a 12). Con mes, las tablas usan solo ese mes del `anio`;
            sin mes, usan todo el histórico.
        id_cliente: Cliente elegido, por identificador.
        producto: Etiqueta del producto elegido, como «Audífonos BT (Audio)».
    """

    anio: int | None = None
    mes: int | None = None
    id_cliente: str | None = None
    producto: str | None = None

    def de_cliente_y_producto(self, linea: Linea) -> bool:
        """Indica si una línea cumple el cliente y el producto elegidos.

        Args:
            linea: Línea de venta.

        Returns:
            `True` si no hay filtro o la línea coincide con los que existan.
        """
        if self.id_cliente and linea.id_cliente != self.id_cliente:
            return False
        if self.producto and linea.producto != self.producto:
            return False
        return True

    def en_mes_global(self, fecha: datetime) -> bool:
        """Indica si una fecha cae en el mes elegido, o si no hay mes elegido.

        Args:
            fecha: Fecha de venta.

        Returns:
            `True` sin mes elegido; con mes, solo si coinciden año y mes.
        """
        if self.mes is None:
            return True
        return fecha.year == (self.anio or fecha.year) and fecha.month == self.mes

    def en_anio(self, fecha: datetime) -> bool:
        """Indica si una fecha cae en el año elegido, o si no hay año elegido.

        Args:
            fecha: Fecha de venta.

        Returns:
            `True` si no hay año o la fecha es de ese año.
        """
        return self.anio is None or fecha.year == self.anio


@dataclass(frozen=True)
class Linea:
    """Un producto vendido dentro de una orden activa o anulada.

    Attributes:
        id_detalle: Identificador de la línea (para ordenar de forma estable).
        id_venta: Orden a la que pertenece.
        numero_orden: Consecutivo visible de la orden.
        fecha: Fecha de venta de la orden.
        id_cliente: Cliente de la orden.
        cliente: Nombre del cliente en la orden.
        telefono: Celular del cliente en la orden.
        categoria: Categoría del producto, o `None`.
        producto: Etiqueta del producto («Nombre (Categoría)»).
        cantidad: Unidades vendidas.
        costo_unitario: Costo de una unidad.
        precio_unitario: Precio de venta de una unidad.
        costo: Costo de la línea (`costo_unitario × cantidad`).
        total: Total de la línea.
        ganancia: Ganancia de la línea.
        saldo: Parte del saldo pendiente de la orden que corresponde a la línea.
        abonado: Parte de los abonos de la orden que corresponde a la línea.
        garantia_fin: Vencimiento de la garantía de la línea, o `None`.
    """

    id_detalle: str
    id_venta: str
    numero_orden: int
    fecha: datetime
    id_cliente: str
    cliente: str
    telefono: str | None
    categoria: str | None
    producto: str
    cantidad: int
    costo_unitario: Decimal
    precio_unitario: Decimal
    costo: Decimal
    total: Decimal
    ganancia: Decimal
    saldo: Decimal
    abonado: Decimal
    garantia_fin: date | None


@dataclass
class _Acumulado:
    """Totales de un periodo (un mes, un año o un cliente).

    Attributes:
        ventas: Número de órdenes distintas del periodo.
        ingresos: Suma de los totales de las líneas.
        costos: Suma de los costos de las líneas.
        ganancia: Suma de las ganancias de las líneas.
    """

    ventas: int = 0
    ingresos: Decimal = CERO
    costos: Decimal = CERO
    ganancia: Decimal = CERO


def _acumular(lineas: list[Linea]) -> _Acumulado:
    """Suma las líneas de un periodo.

    Args:
        lineas: Líneas que pertenecen al periodo.

    Returns:
        Totales del periodo; las órdenes se cuentan una sola vez.
    """
    acumulado = _Acumulado(ventas=len({linea.id_venta for linea in lineas}))
    for linea in lineas:
        acumulado.ingresos += linea.total
        acumulado.costos += linea.costo
        acumulado.ganancia += linea.ganancia
    return acumulado


def _repartir(valor: Decimal, pesos: list[Decimal]) -> list[Decimal]:
    """Reparte un monto entre líneas en proporción a su peso (ADR-55).

    La última línea recibe la diferencia de redondeo, así la suma queda exacta a
    centavos.

    Args:
        valor: Monto total a repartir (saldo o abonos de la orden).
        pesos: Totales de cada línea de la orden.

    Returns:
        Un monto por línea, en el mismo orden que `pesos`.
    """
    total = sum(pesos, CERO)
    if total <= CERO:
        return [CERO for _ in pesos]
    partes: list[Decimal] = []
    asignado = CERO
    ultimo = len(pesos) - 1
    for indice, peso in enumerate(pesos):
        if indice == ultimo:
            parte = redondear_dinero(valor - asignado)
        else:
            parte = redondear_dinero(valor * peso / total)
        partes.append(parte)
        asignado += parte
    return partes


def _lineas(bd: Session, *, incluir_anuladas: bool = False) -> list[Linea]:
    """Construye las líneas de venta con sus saldos y abonos repartidos.

    Args:
        bd: Sesión de base de datos.
        incluir_anuladas: Si es `True`, también devuelve las líneas de órdenes
            anuladas (se usa para el historial de costos).

    Returns:
        Líneas ordenadas por fecha y número de orden.
    """
    consulta = (
        select(VentaDetalle, Venta)
        .join(Venta, Venta.id_venta == VentaDetalle.id_venta)
        .order_by(Venta.fecha_venta, Venta.numero_orden, VentaDetalle.id_detalle)
    )
    if not incluir_anuladas:
        consulta = consulta.where(Venta.estado_orden == ESTADO_ACTIVA)

    grupos: dict[str, list[tuple[VentaDetalle, Venta]]] = {}
    for detalle, venta in bd.execute(consulta).all():
        grupos.setdefault(venta.id_venta, []).append((detalle, venta))

    lineas: list[Linea] = []
    for grupo in grupos.values():
        venta = grupo[0][1]
        pesos = [redondear_dinero(detalle.subtotal_item) for detalle, _ in grupo]
        saldos = _repartir(venta.saldo_pendiente, pesos)
        abonos = _repartir(venta.total_abonado, pesos)
        for (detalle, _), total, saldo, abonado in zip(grupo, pesos, saldos, abonos):
            costo = redondear_dinero(detalle.costo_unitario * detalle.cantidad)
            lineas.append(
                Linea(
                    id_detalle=detalle.id_detalle,
                    id_venta=venta.id_venta,
                    numero_orden=venta.numero_orden,
                    fecha=venta.fecha_venta,
                    id_cliente=venta.id_cliente,
                    cliente=venta.cliente_nombre,
                    telefono=venta.cliente_telefono,
                    categoria=detalle.categoria,
                    producto=etiqueta_producto(detalle.producto_nombre, detalle.categoria),
                    cantidad=detalle.cantidad,
                    costo_unitario=detalle.costo_unitario,
                    precio_unitario=detalle.precio_unitario,
                    costo=costo,
                    total=total,
                    ganancia=redondear_dinero(
                        (detalle.precio_unitario - detalle.costo_unitario) * detalle.cantidad
                    ),
                    saldo=saldo,
                    abonado=abonado,
                    garantia_fin=detalle.garantia_fecha_fin or venta.garantia_fecha_fin,
                )
            )
    lineas.sort(key=lambda linea: (linea.fecha, linea.numero_orden))
    return lineas


def _gastos_operativos_por_mes(bd: Session, anio: int) -> dict[int, Decimal]:
    """Suma los gastos operativos de cada mes de un año (SRS v4.44, §8.3).

    Se recorre la tabla en Python porque es pequeña y así el cálculo es idéntico
    en SQLite y PostgreSQL, sin depender de `EXTRACT`.

    Args:
        bd: Sesión de base de datos.
        anio: Año consultado.

    Returns:
        Diccionario `{mes: total}` con los doce meses; cero donde no hay gastos.
    """
    totales = {mes: CERO for mes in range(1, 13)}
    for fecha, monto in bd.execute(select(GastoOperativo.fecha, GastoOperativo.monto)):
        if fecha.year == anio:
            totales[fecha.month] += monto
    return totales


def _saldos_pasivo_antiguo(bd: Session) -> dict[tuple[int, int], Decimal]:
    """Calcula el saldo del pasivo antiguo al cierre de cada mes (SRS v4.44).

    Regla de imputación: un abono paga primero la deuda corriente de las compras
    a crédito; el remanente reduce el pasivo anterior al sistema, sin bajar de
    cero. El resultado se guarda por (año, mes) y se arrastra a los meses sin
    movimiento al consultarlo.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Diccionario `{(año, mes): saldo}` con el saldo tras el último movimiento
        de cada mes que tuvo movimientos.
    """
    corriente = CERO
    antiguo = CERO
    saldos: dict[tuple[int, int], Decimal] = {}
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
        saldos[(movimiento.fecha.year, movimiento.fecha.month)] = redondear_dinero(antiguo)
    return saldos


def _pasivo_antiguo_en(
    saldos: dict[tuple[int, int], Decimal], anio: int, mes: int
) -> Decimal:
    """Devuelve el saldo vigente en un mes, arrastrando el último conocido.

    Args:
        saldos: Saldos por periodo devueltos por `_saldos_pasivo_antiguo`.
        anio: Año consultado.
        mes: Mes consultado (1 a 12).

    Returns:
        Saldo del pasivo antiguo al cierre de ese mes, o cero si aún no hay.
    """
    objetivo = (anio, mes)
    anteriores = [periodo for periodo in saldos if periodo <= objetivo]
    if not anteriores:
        return CERO
    return saldos[max(anteriores)]


def _gastos_operativos_por_anio(bd: Session, mes: int | None = None) -> dict[int, Decimal]:
    """Suma los gastos operativos de cada año, opcionalmente de un solo mes.

    Args:
        bd: Sesión de base de datos.
        mes: Mes a considerar (1 a 12); `None` suma el año completo.

    Returns:
        Diccionario `{año: total}`; los años sin gastos no aparecen.
    """
    totales: dict[int, Decimal] = {}
    for fecha, monto in bd.execute(select(GastoOperativo.fecha, GastoOperativo.monto)):
        if mes is None or fecha.month == mes:
            totales[fecha.year] = totales.get(fecha.year, CERO) + monto
    return totales


def _variacion(actual: Decimal, anterior: Decimal) -> Decimal | None:
    """Calcula la variación porcentual de un valor frente al anterior.

    Args:
        actual: Valor del periodo consultado.
        anterior: Valor del periodo previo.

    Returns:
        Variación en porcentaje con un decimal; `None` si el periodo previo es cero
        (no hay base para comparar).
    """
    if anterior == CERO:
        return None
    return ((actual - anterior) / abs(anterior) * 100).quantize(UNO)


def _ordenes_activas(bd: Session) -> list[Venta]:
    """Lista las órdenes que cuentan en los reportes.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Órdenes con estado activo.
    """
    return list(bd.scalars(select(Venta).where(Venta.estado_orden == ESTADO_ACTIVA)))


def anios_con_ventas(bd: Session) -> list[int]:
    """Lista los años en los que hay órdenes activas, del más reciente al más antiguo.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Años con al menos una orden activa.
    """
    return sorted({venta.fecha_venta.year for venta in _ordenes_activas(bd)}, reverse=True)


def reporte_mensual(bd: Session, anio: int, filtro: Filtro | None = None) -> list[dict[str, object]]:
    """Resume cada mes de un año y compara cada uno con el anterior (RF-12).

    El cliente y el producto del filtro restringen los montos; el mes del filtro no
    recorta la tabla, porque su propósito es comparar los doce meses.

    Args:
        bd: Sesión de base de datos.
        anio: Año del reporte.
        filtro: Selección compartida; `None` no filtra.

    Returns:
        Doce filas, de enero a diciembre, con cantidad, ingresos, costos, ganancia,
        pasivo antiguo, gastos operativos del mes, ganancia neta, variación de la
        ganancia frente al mes previo y el ancho relativo de la barra de ingresos.
    """
    seleccion = filtro or Filtro()
    lineas = [linea for linea in _lineas(bd) if seleccion.de_cliente_y_producto(linea)]
    periodos = {
        mes: _acumular([l for l in lineas if l.fecha.year == anio and l.fecha.month == mes])
        for mes in range(1, 13)
    }

    maximo = max((p.ingresos for p in periodos.values()), default=CERO)
    gastos_mes = _gastos_operativos_por_mes(bd, anio)
    saldos = _saldos_pasivo_antiguo(bd)
    filas: list[dict[str, object]] = []
    previo: _Acumulado | None = None
    for mes in range(1, 13):
        datos = periodos[mes]
        variacion = None if previo is None else _variacion(datos.ganancia, previo.ganancia)
        barra = 0 if maximo == CERO else int((datos.ingresos / maximo * 100).to_integral_value())
        gastos = redondear_dinero(gastos_mes[mes])
        filas.append(
            {
                "mes": MESES[mes - 1],
                "numero_mes": mes,
                "ventas": datos.ventas,
                "ingresos": redondear_dinero(datos.ingresos),
                # Costos sigue siendo el costo de ventas; el pasivo antiguo va aparte.
                "costos": redondear_dinero(datos.costos),
                "pasivo_antiguo": redondear_dinero(_pasivo_antiguo_en(saldos, anio, mes)),
                "ganancia": redondear_dinero(datos.ganancia),
                # SRS v4.44, §8.3: gasto operativo del mes y ganancia real (neta).
                "gastos_operativos": gastos,
                "ganancia_neta": redondear_dinero(datos.ganancia - gastos),
                "variacion": variacion,
                "barra": barra,
            }
        )
        previo = datos
    return filas


def reporte_anual(bd: Session, filtro: Filtro | None = None) -> list[dict[str, object]]:
    """Resume cada año con ventas y calcula la rentabilidad (RF-12).

    Rentabilidad (%) = ganancia anual ÷ costo anual × 100. Sin costo no hay
    rentabilidad que calcular y se devuelve `None`.

    Args:
        bd: Sesión de base de datos.
        filtro: Selección compartida; `None` no filtra.

    Returns:
        Una fila por año con ventas, ingresos, costos, ganancia, gastos
        operativos, ganancia neta, rentabilidad y variación de la ganancia frente
        al año anterior, del más antiguo al más reciente.
    """
    seleccion = filtro or Filtro()
    lineas = [
        linea
        for linea in _lineas(bd)
        if seleccion.de_cliente_y_producto(linea) and seleccion.en_mes_global(linea.fecha)
    ]
    periodos: dict[int, list[Linea]] = {}
    for linea in lineas:
        periodos.setdefault(linea.fecha.year, []).append(linea)

    filas: list[dict[str, object]] = []
    previo: _Acumulado | None = None
    gastos_anio = _gastos_operativos_por_anio(bd, seleccion.mes)
    saldos = _saldos_pasivo_antiguo(bd)
    for anio in sorted(periodos):
        datos = _acumular(periodos[anio])
        # Saldo al cierre del año; arrastra el de años anteriores si no hubo
        # movimientos en este periodo.
        pasivo = redondear_dinero(_pasivo_antiguo_en(saldos, anio, 12))
        rentabilidad = (
            (datos.ganancia / datos.costos * 100).quantize(UNO) if datos.costos > CERO else None
        )
        variacion = None if previo is None else _variacion(datos.ganancia, previo.ganancia)
        gastos = redondear_dinero(gastos_anio.get(anio, CERO))
        filas.append(
            {
                "anio": anio,
                "ventas": datos.ventas,
                "ingresos": redondear_dinero(datos.ingresos),
                # Costos es solo costo de ventas; el pasivo antiguo va aparte.
                "costos": redondear_dinero(datos.costos),
                "pasivo_antiguo": pasivo,
                "ganancia": redondear_dinero(datos.ganancia),
                # SRS v4.44, §8.3: gasto operativo del año y ganancia real (neta).
                "gastos_operativos": gastos,
                "ganancia_neta": redondear_dinero(datos.ganancia - gastos),
                "rentabilidad": rentabilidad,
                "variacion": variacion,
            }
        )
        previo = datos
    return filas


def ranking_vip(
    bd: Session, limite: int = 10, filtro: Filtro | None = None
) -> list[dict[str, object]]:
    """Ordena a los clientes por lo que han comprado (RF-13).

    Args:
        bd: Sesión de base de datos.
        limite: Número máximo de clientes en el ranking.
        filtro: Selección compartida; `None` no filtra.

    Returns:
        Clientes con nombre, celular, número de compras, monto total y fecha de la
        última compra, del que más compra al que menos.
    """
    seleccion = filtro or Filtro()
    lineas = [
        linea
        for linea in _lineas(bd)
        if seleccion.de_cliente_y_producto(linea) and seleccion.en_mes_global(linea.fecha)
    ]
    por_cliente: dict[str, list[Linea]] = {}
    for linea in lineas:
        por_cliente.setdefault(linea.id_cliente, []).append(linea)

    filas: list[dict[str, object]] = []
    for grupo in por_cliente.values():
        reciente = max(grupo, key=lambda linea: linea.fecha)
        filas.append(
            {
                "id_cliente": reciente.id_cliente,
                "cliente": reciente.cliente,
                "telefono": reciente.telefono,
                "compras": len({linea.id_venta for linea in grupo}),
                "monto": redondear_dinero(sum((linea.total for linea in grupo), start=CERO)),
                "ultima": max(linea.fecha for linea in grupo),
            }
        )
    filas.sort(key=lambda fila: (-fila["monto"], -fila["compras"], str(fila["cliente"])))
    return filas[:limite]


def alertas_costos(bd: Session, filtro: Filtro | None = None) -> dict[str, list[dict[str, object]]]:
    """Detecta subidas de costo del proveedor y el margen con el último precio (RF-14).

    Compara el costo unitario de cada compra con la compra anterior del mismo
    producto. Solo se consideran los productos que se han comprado al menos dos
    veces. El margen usa el último precio de venta y el último costo.

    Con mes elegido, el historial se corta al final de ese mes y solo aparecen los
    productos con una compra en ese mes. El cliente elegido limita a los productos
    que ese cliente ha comprado.

    Args:
        bd: Sesión de base de datos.
        filtro: Selección compartida; `None` no filtra.

    Returns:
        `subidas` con los productos cuyo costo subió, de mayor a menor variación, y
        `costos` con el último costo registrado de cada producto.
    """
    seleccion = filtro or Filtro()
    historial: dict[str, list[Linea]] = {}
    for linea in _lineas(bd, incluir_anuladas=True):
        if seleccion.mes is not None and (linea.fecha.year, linea.fecha.month) > (
            seleccion.anio or linea.fecha.year,
            seleccion.mes,
        ):
            continue
        historial.setdefault(linea.producto, []).append(linea)

    subidas: list[dict[str, object]] = []
    ultimos: list[dict[str, object]] = []
    for etiqueta, compras in historial.items():
        if seleccion.producto and etiqueta != seleccion.producto:
            continue
        if seleccion.id_cliente and not any(
            linea.id_cliente == seleccion.id_cliente for linea in compras
        ):
            continue
        ultima = compras[-1]
        if seleccion.mes is not None and (ultima.fecha.year, ultima.fecha.month) != (
            seleccion.anio or ultima.fecha.year,
            seleccion.mes,
        ):
            continue

        margen = (
            (
                (ultima.precio_unitario - ultima.costo_unitario)
                / ultima.precio_unitario
                * 100
            ).quantize(UNO)
            if ultima.precio_unitario > CERO
            else None
        )
        ultimos.append(
            {
                "producto": etiqueta,
                "costo": redondear_dinero(ultima.costo_unitario),
                "precio": redondear_dinero(ultima.precio_unitario),
                "margen": margen,
                "fecha": ultima.fecha,
            }
        )
        if len(compras) < 2:
            continue
        anterior = compras[-2]
        if ultima.costo_unitario > anterior.costo_unitario and anterior.costo_unitario > CERO:
            variacion = _variacion(ultima.costo_unitario, anterior.costo_unitario)
            subidas.append(
                {
                    "producto": etiqueta,
                    "costo_anterior": redondear_dinero(anterior.costo_unitario),
                    "costo_actual": redondear_dinero(ultima.costo_unitario),
                    "variacion": variacion,
                    "precio": redondear_dinero(ultima.precio_unitario),
                    "margen": margen,
                    "margen_bajo": margen is not None and margen < UMBRAL_MARGEN_BAJO,
                    "fecha": ultima.fecha,
                }
            )

    subidas.sort(key=lambda fila: -Decimal(fila["variacion"] or CERO))
    ultimos.sort(key=lambda fila: str(fila["producto"]))
    return {"subidas": subidas, "costos": ultimos}


def estado_garantia_fila(fecha_fin: date | None, hoy: date) -> str:
    """Indica si la garantía de un producto sigue activa (SRS v1.9).

    Args:
        fecha_fin: Vencimiento de la garantía de la línea, o `None`.
        hoy: Fecha de referencia (hoy en la tienda).

    Returns:
        `Activa` si vence hoy o después, `Vencida` si ya pasó y `Sin garantía` si
        no tiene fecha.
    """
    if fecha_fin is None:
        return GARANTIA_SIN_FECHA
    return GARANTIA_ACTIVA if fecha_fin >= hoy else GARANTIA_VENCIDA


def tabla_ventas(bd: Session, filtro: Filtro | None, hoy: date) -> list[dict[str, object]]:
    """Lista cada producto vendido en el periodo y el cliente elegidos (SRS v1.9).

    Una fila por producto, con su costo, total, saldo, abonos, ganancia y estado
    de garantía. Las órdenes anuladas no aparecen.

    Args:
        bd: Sesión de base de datos.
        filtro: Selección compartida; `None` lista todo.
        hoy: Fecha de referencia para la garantía.

    Returns:
        Filas ordenadas de la orden más reciente a la más antigua.
    """
    seleccion = filtro or Filtro()
    lineas = [
        linea
        for linea in _lineas(bd)
        if seleccion.de_cliente_y_producto(linea)
        and seleccion.en_anio(linea.fecha)
        and seleccion.en_mes_global(linea.fecha)
    ]
    lineas.sort(key=lambda linea: (-linea.numero_orden, linea.id_detalle))
    return [
        {
            "numero_orden": linea.numero_orden,
            "id_cliente": linea.id_cliente,
            "cliente": linea.cliente,
            "categoria": linea.categoria or "",
            "producto": linea.producto,
            "costo": redondear_dinero(linea.costo),
            "total": redondear_dinero(linea.total),
            "saldo": redondear_dinero(linea.saldo),
            "abonado": redondear_dinero(linea.abonado),
            "ganancia": redondear_dinero(linea.ganancia),
            "garantia_fin": linea.garantia_fin,
            "garantia": estado_garantia_fila(linea.garantia_fin, hoy),
        }
        for linea in lineas
    ]


def _csv_dinero(valor: Decimal) -> str:
    """Formatea un monto para Excel en español: dos decimales y coma.

    Args:
        valor: Monto en pesos.

    Returns:
        Texto como `12345,50`.
    """
    return f"{redondear_dinero(valor):.2f}".replace(".", ",")


def _csv_numero(valor: Decimal | None) -> str:
    """Formatea un porcentaje o una variación para CSV; vacío si no hay dato.

    Args:
        valor: Porcentaje con un decimal, o `None`.

    Returns:
        Texto como `12,5`, o cadena vacía.
    """
    return "" if valor is None else str(valor).replace(".", ",")


def _csv_fecha(fecha: date | datetime | None) -> str:
    """Formatea una fecha como dd-mm-aaaa para CSV.

    Args:
        fecha: Fecha o fecha y hora, o `None`.

    Returns:
        Texto `dd-mm-aaaa`, o cadena vacía.
    """
    return "" if fecha is None else fecha.strftime("%d-%m-%Y")


def serializar_csv(encabezados: list[str], filas: list[list[str]]) -> str:
    """Convierte una tabla en CSV compatible con Excel en español.

    Args:
        encabezados: Nombres de las columnas, en orden.
        filas: Filas ya formateadas como texto.

    Returns:
        Contenido CSV con separador `;` y BOM UTF-8.
    """
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
    escritor.writerow(encabezados)
    escritor.writerows(filas)
    return "\ufeff" + salida.getvalue()


def tabla_csv(
    bd: Session, nombre: str, filtro: Filtro, hoy: date
) -> tuple[list[str], list[list[str]]] | None:
    """Arma la tabla que se descarga, con el mismo contenido que la pantalla.

    Args:
        bd: Sesión de base de datos.
        nombre: Una de `TABLAS_CSV`.
        filtro: Selección activa en la pantalla.
        hoy: Fecha de referencia para la garantía.

    Returns:
        Tupla `(encabezados, filas)`, o `None` si el nombre no existe.
    """
    if nombre not in TABLAS_CSV:
        return None

    if nombre == "mensual":
        encabezados = [
            "Mes", "Ventas", "Ingresos", "Costos", "Ganancia",
            PASIVO_ANTIGUO_LABEL,
            "Gastos operativos", "Ganancia neta", "Variación ganancia (%)",
        ]
        filas = [
            [
                str(fila["mes"]),
                str(fila["ventas"]),
                _csv_dinero(fila["ingresos"]),
                _csv_dinero(fila["costos"]),
                _csv_dinero(fila["ganancia"]),
                _csv_dinero(fila["pasivo_antiguo"]),
                _csv_dinero(fila["gastos_operativos"]),
                _csv_dinero(fila["ganancia_neta"]),
                _csv_numero(fila["variacion"]),
            ]
            for fila in reporte_mensual(bd, filtro.anio or hoy.year, filtro)
        ]
    elif nombre == "anual":
        encabezados = [
            "Año", "Ventas", "Ingresos", "Costos", "Ganancia",
            PASIVO_ANTIGUO_LABEL,
            "Gastos operativos", "Ganancia neta", "Rentabilidad (%)",
            "Variación ganancia (%)",
        ]
        filas = [
            [
                str(fila["anio"]),
                str(fila["ventas"]),
                _csv_dinero(fila["ingresos"]),
                _csv_dinero(fila["costos"]),
                _csv_dinero(fila["ganancia"]),
                _csv_dinero(fila["pasivo_antiguo"]),
                _csv_dinero(fila["gastos_operativos"]),
                _csv_dinero(fila["ganancia_neta"]),
                _csv_numero(fila["rentabilidad"]),
                _csv_numero(fila["variacion"]),
            ]
            for fila in reporte_anual(bd, filtro)
        ]
    elif nombre == "vip":
        encabezados = ["Cliente", "Teléfono", "Compras", "Monto", "Última compra"]
        filas = [
            [
                str(fila["cliente"]),
                str(fila["telefono"] or ""),
                str(fila["compras"]),
                _csv_dinero(fila["monto"]),
                _csv_fecha(fila["ultima"]),
            ]
            for fila in ranking_vip(bd, filtro=filtro)
        ]
    elif nombre == "alertas":
        encabezados = [
            "Producto", "Costo anterior", "Costo actual", "Subida (%)", "Precio",
            "Margen (%)", "Margen bajo", "Fecha",
        ]
        filas = [
            [
                str(fila["producto"]),
                _csv_dinero(fila["costo_anterior"]),
                _csv_dinero(fila["costo_actual"]),
                _csv_numero(fila["variacion"]),
                _csv_dinero(fila["precio"]),
                _csv_numero(fila["margen"]),
                "Sí" if fila["margen_bajo"] else "No",
                _csv_fecha(fila["fecha"]),
            ]
            for fila in alertas_costos(bd, filtro)["subidas"]
        ]
    elif nombre == "costos":
        encabezados = ["Producto", "Último costo", "Último precio", "Margen (%)", "Fecha"]
        filas = [
            [
                str(fila["producto"]),
                _csv_dinero(fila["costo"]),
                _csv_dinero(fila["precio"]),
                _csv_numero(fila["margen"]),
                _csv_fecha(fila["fecha"]),
            ]
            for fila in alertas_costos(bd, filtro)["costos"]
        ]
    else:
        encabezados = [
            "No. de orden", "Cliente", "Categoría", "Producto", "Costo", "Total",
            "Saldo pendiente", "Abonos realizados", "Ganancia", "Garantía",
        ]
        filas = [
            [
                str(fila["numero_orden"]),
                str(fila["cliente"]),
                str(fila["categoria"]),
                str(fila["producto"]),
                _csv_dinero(fila["costo"]),
                _csv_dinero(fila["total"]),
                _csv_dinero(fila["saldo"]),
                _csv_dinero(fila["abonado"]),
                _csv_dinero(fila["ganancia"]),
                str(fila["garantia"]),
            ]
            for fila in tabla_ventas(bd, filtro, hoy)
        ]
    return encabezados, filas
