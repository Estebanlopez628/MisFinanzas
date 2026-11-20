"""Resumen de quincenas para el panel izquierdo de "Mis Finanzas".

Responsabilidad
---------------
Calcular, por cada pago del mes, el ingreso proyectado, los gastos fijos
asignados, las deducciones de ley, las deducciones fijas del salario y el saldo
libre restante. La aritmética salarial sigue viviendo en `app.servicios.nomina`.

Reglas:
- Modalidad `QUINCENAL`: dos tarjetas (quincena 1 y 2) con los porcentajes del
  perfil. Las deducciones de ley del mes (8 %) se restan **solo** de la quincena
  marcada en `perfil.quincena_deducciones`.
- Modalidad `MENSUAL`: una sola tarjeta con el sueldo completo y todas las
  deducciones.
- Los gastos sin quincena asignada (datos anteriores al SRS v1.2) se imputan a
  la quincena 1 y se marcan como gastos de todo el mes.
- SRS v1.4, REQ-05: el descuento por incapacidad se resta del sueldo base antes
  de repartirlo por porcentaje entre las quincenas.
- SRS v1.4, REQ-04: los recargos (horas extras) se suman al ingreso de la
  quincena donde se liquidan según el perfil (por defecto, la de deducciones).
- SRS v1.4, REQ-08: las deducciones fijas del salario se restan de la quincena
  indicada antes de calcular el saldo libre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.modelos import DeduccionFija, Gasto, PerfilFinanciero
from app.servicios import deducciones_fijas as servicio_deducciones
from app.servicios import gastos as servicio_gastos
from app.servicios import perfiles
from app.servicios.gastos import valor_computable
from app.servicios.nomina import calcular_deducciones_ley

CERO = Decimal("0")


@dataclass(frozen=True)
class ResumenQuincena:
    """Valores de un pago (mes o quincena) para el panel izquierdo.

    Attributes:
        numero: `0` mes completo, `1` primera quincena, `2` segunda quincena.
        etiqueta: Texto visible («Mes», «Quincena 1 · día 5»), con el día que
            el usuario configuró en su perfil.
        porcentaje: Porcentaje del sueldo que se paga en este bloque.
        ingreso: Sueldo proyectado del bloque, ajustado por incapacidad y con
            recargos cuando corresponde.
        gastos: Suma de gastos fijos asignados.
        deducciones: Salud y pensión que se descuentan en este bloque.
        saldo_libre: `ingreso − gastos − deducciones − deducciones fijas`.
        gastos_detalle: Gastos que componen la suma.
        mes_completo: `True` si el bloque es mensual o si contiene gastos sin
            quincena asignada.
        deducciones_fijas: Descuentos fijos del salario aplicados a este bloque.
        deducciones_fijas_detalle: Deducciones fijas que componen la suma.
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
    deducciones_fijas: Decimal = CERO
    deducciones_fijas_detalle: list[DeduccionFija] = field(default_factory=list)


def _etiqueta(numero: int, perfil: PerfilFinanciero | None) -> str:
    """Devuelve el nombre visible de un bloque de pago.

    SRS v1.9: el día de cada quincena sale del perfil del usuario, no de un valor
    fijo, para que la etiqueta coincida con lo que el usuario configuró.

    Args:
        numero: `0`, `1` o `2`.
        perfil: Perfil del usuario; `None` usa los días predeterminados.

    Returns:
        Texto listo para la interfaz.
    """
    if numero in (1, 2):
        return perfiles.etiquetas_quincena(perfil)[numero]
    return "Mes completo"


def resumen_quincenas(
    bd: Session,
    id_usuario: str,
    perfil: PerfilFinanciero | None,
    anio: int,
    mes: int,
    recargos: Decimal | int | str = CERO,
    descuento_incapacidad: Decimal | int | str = CERO,
) -> list[ResumenQuincena]:
    """Calcula el resumen de pagos y saldos libres del mes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos y deducciones.
        perfil: Perfil financiero; si es `None` el ingreso proyectado es cero.
        anio: Año del periodo consultado.
        mes: Mes del periodo (1–12).
        recargos: Valor de horas extras y recargos del periodo que se está
            liquidando (SRS v1.4, REQ-04). Se suma a la quincena de deducciones.
        descuento_incapacidad: Descuento por incapacidad del periodo (SRS v1.4,
            REQ-05). Se resta del sueldo base antes de repartirlo.

    Returns:
        Lista con una tarjeta para modalidad MENSUAL o dos para QUINCENAL.
    """
    del_mes = servicio_gastos.listar_gastos(bd, id_usuario, anio, mes)
    fijas = servicio_deducciones.listar_deducciones(bd, id_usuario)
    total_fijas_mes = servicio_deducciones.total_por_quincena(fijas, 1) + (
        servicio_deducciones.total_por_quincena(fijas, 2)
    )

    if perfil is None:
        total = redondear_dinero(sum((valor_computable(gasto) for gasto in del_mes), start=CERO))
        return [
            ResumenQuincena(
                numero=0,
                etiqueta=_etiqueta(0, perfil),
                porcentaje=CERO,
                ingreso=CERO,
                gastos=total,
                deducciones=CERO,
                saldo_libre=redondear_dinero(-total - total_fijas_mes),
                gastos_detalle=del_mes,
                mes_completo=True,
                deducciones_fijas=total_fijas_mes,
                deducciones_fijas_detalle=fijas,
            )
        ]

    # REQ-05: la incapacidad reduce el sueldo base del periodo antes del reparto.
    sueldo_ajustado = redondear_dinero(
        perfil.sueldo_basico - _a_decimal(descuento_incapacidad)
    )
    recargos_periodo = redondear_dinero(_a_decimal(recargos))
    # SRS v1.4: salud y pensión se calculan sobre el salario devengado que queda
    # tras la incapacidad y con horas extras (no sobre el sueldo básico fijo).
    base_cotizacion = redondear_dinero(max(sueldo_ajustado + recargos_periodo, CERO))
    deducciones_mes = calcular_deducciones_ley(base_cotizacion).total

    if perfil.modalidad_pago == perfiles.MODALIDAD_MENSUAL:
        total = redondear_dinero(sum((valor_computable(gasto) for gasto in del_mes), start=CERO))
        return [
            ResumenQuincena(
                numero=0,
                etiqueta=_etiqueta(0, perfil),
                porcentaje=Decimal("100"),
                ingreso=redondear_dinero(sueldo_ajustado + recargos_periodo),
                gastos=total,
                deducciones=deducciones_mes,
                saldo_libre=redondear_dinero(
                    sueldo_ajustado + recargos_periodo - total - deducciones_mes - total_fijas_mes
                ),
                gastos_detalle=del_mes,
                mes_completo=True,
                deducciones_fijas=total_fijas_mes,
                deducciones_fijas_detalle=fijas,
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
        ingreso = redondear_dinero(sueldo_ajustado * porcentaje / Decimal("100"))
        # REQ-04: los recargos se liquidan en la quincena de deducciones del perfil.
        if perfil.quincena_deducciones == numero:
            ingreso = redondear_dinero(ingreso + recargos_periodo)
        total_gastos = redondear_dinero(
            sum((valor_computable(gasto) for gasto in detalle), start=CERO)
        )
        # Las deducciones de ley del mes se imputan solo a la quincena elegida.
        deducciones = deducciones_mes if perfil.quincena_deducciones == numero else CERO
        # REQ-08: cada descuento fijo se resta solo de su propia quincena.
        detalle_fijas = [d for d in fijas if d.quincena == numero]
        total_fijas = servicio_deducciones.total_por_quincena(fijas, numero)
        resumen.append(
            ResumenQuincena(
                numero=numero,
                etiqueta=_etiqueta(numero, perfil),
                porcentaje=porcentaje,
                ingreso=ingreso,
                gastos=total_gastos,
                deducciones=deducciones,
                saldo_libre=redondear_dinero(
                    ingreso - total_gastos - deducciones - total_fijas
                ),
                gastos_detalle=detalle,
                mes_completo=any(gasto.quincena is None for gasto in detalle),
                deducciones_fijas=total_fijas,
                deducciones_fijas_detalle=detalle_fijas,
            )
        )
    return resumen


def _a_decimal(valor: Decimal | int | str) -> Decimal:
    """Convierte un valor monetario a `Decimal` tolerando cadenas vacías.

    Args:
        valor: Número o texto numérico.

    Returns:
        Valor como `Decimal`; cero si el texto está vacío.
    """
    if valor in (None, ""):
        return CERO
    return Decimal(str(valor))
