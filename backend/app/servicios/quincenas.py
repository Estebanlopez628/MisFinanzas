"""Resumen de quincenas para el panel izquierdo de "Mis Finanzas".

Responsabilidad
---------------
Calcular, por cada pago del mes, el ingreso proyectado, los gastos fijos
asignados, las deducciones de ley y el saldo libre restante. El layout de doble
columna del SRS v1.2 consume este resumen; la aritmética salarial sigue viviendo
en `app.servicios.nomina`.

Reglas:
- Modalidad `QUINCENAL`: dos tarjetas (quincena 1 y 2) con los porcentajes del
  perfil. Las deducciones de ley del mes (8 %) se restan **solo** de la quincena
  marcada en `perfil.quincena_deducciones`.
- Modalidad `MENSUAL`: una sola tarjeta con el sueldo completo y todas las
  deducciones.
- Los gastos sin quincena asignada (datos anteriores al SRS v1.2) se imputan a
  la quincena 1 y se marcan como gastos de todo el mes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.modelos import Gasto, PerfilFinanciero
from app.servicios import gastos as servicio_gastos
from app.servicios import perfiles
from app.servicios.nomina import calcular_deducciones_ley

CERO = Decimal("0")


@dataclass(frozen=True)
class ResumenQuincena:
    """Valores de un pago (mes o quincena) para el panel izquierdo.

    Attributes:
        numero: `0` mes completo, `1` primera quincena, `2` segunda quincena.
        etiqueta: Texto visible («Mes», «Quincena 1 (día 15)»).
        porcentaje: Porcentaje del sueldo que se paga en este bloque.
        ingreso: Sueldo proyectado del bloque.
        gastos: Suma de gastos fijos asignados.
        deducciones: Salud y pensión que se descuentan en este bloque.
        saldo_libre: `ingreso − gastos − deducciones`.
        gastos_detalle: Gastos que componen la suma.
        mes_completo: `True` si el bloque es mensual o si contiene gastos sin
            quincena asignada.
    """

    numero: int
    etiqueta: str
    porcentaje: Decimal
    ingreso: Decimal
    gastos: Decimal
    deducciones: Decimal
    saldo_libre: Decimal
    gastos_detalle: list[Gasto] = field(default_factory=list)
    mes_completo: bool = False


def _etiqueta(numero: int) -> str:
    """Devuelve el nombre visible de un bloque de pago.

    Args:
        numero: `0`, `1` o `2`.

    Returns:
        Texto listo para la interfaz.
    """
    if numero == 1:
        return "Quincena 1 · día 15"
    if numero == 2:
        return "Quincena 2 · día 30"
    return "Mes completo"


def resumen_quincenas(
    bd: Session,
    id_usuario: str,
    perfil: PerfilFinanciero | None,
    anio: int,
    mes: int,
) -> list[ResumenQuincena]:
    """Calcula el resumen de pagos y saldos libres del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        perfil: Perfil financiero; si es `None` el ingreso proyectado es cero.
        anio: Año del periodo consultado.
        mes: Mes del periodo (1–12).

    Returns:
        Lista con una tarjeta para modalidad MENSUAL o dos para QUINCENAL.
    """
    del_mes = servicio_gastos.listar_gastos(bd, id_usuario, anio, mes)

    if perfil is None:
        total = redondear_dinero(sum((gasto.valor for gasto in del_mes), start=CERO))
        return [
            ResumenQuincena(
                numero=0,
                etiqueta=_etiqueta(0),
                porcentaje=CERO,
                ingreso=CERO,
                gastos=total,
                deducciones=CERO,
                saldo_libre=redondear_dinero(-total),
                gastos_detalle=del_mes,
                mes_completo=True,
            )
        ]

    deducciones_mes = calcular_deducciones_ley(perfil.sueldo_basico).total

    if perfil.modalidad_pago == perfiles.MODALIDAD_MENSUAL:
        total = redondear_dinero(sum((gasto.valor for gasto in del_mes), start=CERO))
        return [
            ResumenQuincena(
                numero=0,
                etiqueta=_etiqueta(0),
                porcentaje=Decimal("100"),
                ingreso=redondear_dinero(perfil.sueldo_basico),
                gastos=total,
                deducciones=deducciones_mes,
                saldo_libre=redondear_dinero(
                    perfil.sueldo_basico - total - deducciones_mes
                ),
                gastos_detalle=del_mes,
                mes_completo=True,
            )
        ]

    # Modalidad quincenal: los gastos sin quincena se muestran en la primera
    # para que el total del mes no se pierda de vista.
    de_quincena_1 = [gasto for gasto in del_mes if gasto.quincena in (None, 1)]
    de_quincena_2 = [gasto for gasto in del_mes if gasto.quincena == 2]
    porcentaje_1, porcentaje_2 = perfiles.porcentajes_quincena(perfil)

    resumen: list[ResumenQuincena] = []
    for numero, porcentaje, detalle in (
        (1, porcentaje_1, de_quincena_1),
        (2, porcentaje_2, de_quincena_2),
    ):
        ingreso = redondear_dinero(perfil.sueldo_basico * porcentaje / Decimal("100"))
        total_gastos = redondear_dinero(
            sum((gasto.valor for gasto in detalle), start=CERO)
        )
        # Las deducciones de ley del mes se imputan solo a la quincena elegida.
        deducciones = deducciones_mes if perfil.quincena_deducciones == numero else CERO
        resumen.append(
            ResumenQuincena(
                numero=numero,
                etiqueta=_etiqueta(numero),
                porcentaje=porcentaje,
                ingreso=ingreso,
                gastos=total_gastos,
                deducciones=deducciones,
                saldo_libre=redondear_dinero(ingreso - total_gastos - deducciones),
                gastos_detalle=detalle,
                mes_completo=any(gasto.quincena is None for gasto in detalle),
            )
        )
    return resumen
