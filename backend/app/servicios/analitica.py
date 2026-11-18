"""Analítica de OLB_BYTE: reportes mensuales y anuales, clientes VIP y costos.

Responsabilidad
---------------
- Agrupar ventas por mes y por año: cantidad, ingresos, costos, ganancia y
  variación frente al periodo anterior (RF-12).
- Calcular la rentabilidad anual: ganancia ÷ costo × 100 (RF-12).
- Ordenar a los clientes por monto y frecuencia para fidelización (RF-13).
- Detectar subidas de costo del proveedor por producto y el margen que queda con
  el último precio de venta (RF-14).

Reglas comunes (ADR-35):
- Los ingresos, la ganancia y los rankings excluyen las órdenes anuladas.
- El historial de costos incluye todas las compras: la mercancía se compró aunque
  la orden se haya anulado.
- Los meses y años se toman de la fecha de venta guardada en hora de la tienda.

Todo el cálculo usa `Decimal`; los porcentajes se redondean a un decimal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.modelos import Venta, VentaDetalle
from app.servicios.comercial import CERO, ESTADO_ACTIVA, etiqueta_producto

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


@dataclass
class _Acumulado:
    """Totales de un periodo (un mes o un año).

    Attributes:
        ventas: Número de órdenes activas.
        ingresos: Suma de los totales de venta.
        costos: Suma de los costos al proveedor.
        ganancia: Suma de las ganancias netas.
    """

    ventas: int = 0
    ingresos: Decimal = CERO
    costos: Decimal = CERO
    ganancia: Decimal = CERO

    def sumar(self, venta: Venta) -> None:
        """Suma una orden al periodo.

        Args:
            venta: Orden activa del periodo.
        """
        self.ventas += 1
        self.ingresos += venta.total
        self.costos += venta.total_costo
        self.ganancia += venta.ganancia_neta


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


def reporte_mensual(bd: Session, anio: int) -> list[dict[str, object]]:
    """Resume cada mes de un año y compara cada uno con el anterior (RF-12).

    Args:
        bd: Sesión de base de datos.
        anio: Año del reporte.

    Returns:
        Doce filas, de enero a diciembre, con cantidad, ingresos, costos, ganancia,
        variación de la ganancia frente al mes previo y el ancho relativo de la barra
        de ingresos (0 a 100).
    """
    periodos = {mes: _Acumulado() for mes in range(1, 13)}
    for venta in _ordenes_activas(bd):
        if venta.fecha_venta.year == anio:
            periodos[venta.fecha_venta.month].sumar(venta)

    maximo = max((p.ingresos for p in periodos.values()), default=CERO)
    filas: list[dict[str, object]] = []
    previo: _Acumulado | None = None
    for mes in range(1, 13):
        datos = periodos[mes]
        variacion = None if previo is None else _variacion(datos.ganancia, previo.ganancia)
        barra = 0 if maximo == CERO else int((datos.ingresos / maximo * 100).to_integral_value())
        filas.append(
            {
                "mes": MESES[mes - 1],
                "ventas": datos.ventas,
                "ingresos": redondear_dinero(datos.ingresos),
                "costos": redondear_dinero(datos.costos),
                "ganancia": redondear_dinero(datos.ganancia),
                "variacion": variacion,
                "barra": barra,
            }
        )
        previo = datos
    return filas


def reporte_anual(bd: Session) -> list[dict[str, object]]:
    """Resume cada año con ventas y calcula la rentabilidad (RF-12).

    Rentabilidad (%) = ganancia anual ÷ costo anual × 100. Sin costo no hay
    rentabilidad que calcular y se devuelve `None`.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Una fila por año con ventas, ingresos, costos, ganancia, rentabilidad y
        variación de la ganancia frente al año anterior, del más antiguo al más reciente.
    """
    periodos: dict[int, _Acumulado] = {}
    for venta in _ordenes_activas(bd):
        periodos.setdefault(venta.fecha_venta.year, _Acumulado()).sumar(venta)

    filas: list[dict[str, object]] = []
    previo: _Acumulado | None = None
    for anio in sorted(periodos):
        datos = periodos[anio]
        rentabilidad = (
            (datos.ganancia / datos.costos * 100).quantize(UNO) if datos.costos > CERO else None
        )
        variacion = None if previo is None else _variacion(datos.ganancia, previo.ganancia)
        filas.append(
            {
                "anio": anio,
                "ventas": datos.ventas,
                "ingresos": redondear_dinero(datos.ingresos),
                "costos": redondear_dinero(datos.costos),
                "ganancia": redondear_dinero(datos.ganancia),
                "rentabilidad": rentabilidad,
                "variacion": variacion,
            }
        )
        previo = datos
    return filas


def ranking_vip(bd: Session, limite: int = 10) -> list[dict[str, object]]:
    """Ordena a los clientes por lo que han comprado (RF-13).

    Args:
        bd: Sesión de base de datos.
        limite: Número máximo de clientes en el ranking.

    Returns:
        Clientes con nombre, celular, número de compras, monto total y fecha de la
        última compra, del que más compra al que menos.
    """
    por_cliente: dict[str, dict[str, object]] = {}
    for venta in _ordenes_activas(bd):
        fila = por_cliente.setdefault(
            venta.id_cliente,
            {
                "cliente": venta.cliente_nombre,
                "telefono": venta.cliente_telefono,
                "compras": 0,
                "monto": CERO,
                "ultima": venta.fecha_venta,
            },
        )
        fila["compras"] = int(fila["compras"]) + 1
        fila["monto"] = Decimal(fila["monto"]) + venta.total
        if venta.fecha_venta > fila["ultima"]:
            fila["ultima"] = venta.fecha_venta

    filas = sorted(
        por_cliente.values(),
        key=lambda fila: (-Decimal(fila["monto"]), -int(fila["compras"]), str(fila["cliente"])),
    )
    return [
        {**fila, "monto": redondear_dinero(Decimal(fila["monto"]))} for fila in filas[:limite]
    ]


def alertas_costos(bd: Session) -> dict[str, list[dict[str, object]]]:
    """Detecta subidas de costo del proveedor y el margen con el último precio (RF-14).

    Compara el costo unitario de cada compra con la compra anterior del mismo
    producto. Solo se consideran los productos que se han comprado al menos dos
    veces. El margen usa el último precio de venta y el último costo, y se muestra
    para que el vendedor decida si debe ajustar el precio.

    Args:
        bd: Sesión de base de datos.

    Returns:
        `subidas` con los productos cuyo costo subió, de mayor a menor variación, y
        `costos` con el último costo registrado de cada producto.
    """
    consulta = (
        select(VentaDetalle, Venta)
        .join(Venta, Venta.id_venta == VentaDetalle.id_venta)
        .order_by(Venta.fecha_venta, VentaDetalle.id_detalle)
    )
    historial: dict[str, list[tuple[datetime, VentaDetalle]]] = {}
    for detalle, venta in bd.execute(consulta).all():
        etiqueta = etiqueta_producto(detalle.producto_nombre, detalle.categoria)
        historial.setdefault(etiqueta, []).append((venta.fecha_venta, detalle))

    subidas: list[dict[str, object]] = []
    ultimos: list[dict[str, object]] = []
    for etiqueta, compras in historial.items():
        fecha_ultima, ultima = compras[-1]
        margen = (
            ((ultima.precio_unitario - ultima.costo_unitario) / ultima.precio_unitario * 100).quantize(UNO)
            if ultima.precio_unitario > CERO
            else None
        )
        ultimos.append(
            {
                "producto": etiqueta,
                "costo": redondear_dinero(ultima.costo_unitario),
                "precio": redondear_dinero(ultima.precio_unitario),
                "margen": margen,
                "fecha": fecha_ultima,
            }
        )
        if len(compras) < 2:
            continue
        _, anterior = compras[-2]
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
                    "fecha": fecha_ultima,
                }
            )

    subidas.sort(key=lambda fila: -Decimal(fila["variacion"] or CERO))
    ultimos.sort(key=lambda fila: str(fila["producto"]))
    return {"subidas": subidas, "costos": ultimos}
