"""Evaluación del derecho al auxilio de transporte (SRS RF-07).

Responsabilidad
---------------
Determinar si el trabajador conserva el auxilio de transporte comparando el
**total devengado** (sueldo básico + recargos) contra el tope legal de 2 SMMLV.

Regla de negocio:
- Si ``Total Devengado <= 2 SMMLV`` → se asigna el valor legal del auxilio y se
  informa la diferencia que falta para alcanzar el tope.
- Si ``Total Devengado > 2 SMMLV`` → el auxilio se anula ($0) y se despliega el
  mensaje exigido por el SRS: *"Supera los 2 salarios mínimos: No aplica
  Auxilio de Transporte"*.

El cálculo es una función pura: no conoce HTTP, base de datos ni plantillas.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.config import ParametrosNomina, obtener_parametros
from app.core.numeros import a_decimal, redondear_dinero
from app.core.texto import formatear_cop

# Mensaje literal exigido por el SRS (RF-07). Se centraliza para que la UI y las
# pruebas usen exactamente el mismo texto.
MENSAJE_SIN_AUXILIO = "Supera los 2 salarios mínimos: No aplica Auxilio de Transporte"


@dataclass(frozen=True)
class EvaluacionAuxilio:
    """Resultado de evaluar el auxilio de transporte.

    Attributes:
        total_devengado: Sueldo básico + total de recargos.
        tope: Valor de 2 SMMLV vigente.
        aplica: `True` si el trabajador conserva el auxilio.
        valor: Dinero del auxilio (0 cuando no aplica).
        diferencia_hasta_tope: Cuánto falta para llegar al tope (0 si no aplica).
        excedente: Cuánto se superó el tope (0 si aplica).
        mensaje: Texto listo para mostrar en la interfaz.
    """

    total_devengado: Decimal
    tope: Decimal
    aplica: bool
    valor: Decimal
    diferencia_hasta_tope: Decimal
    excedente: Decimal
    mensaje: str


def evaluar_auxilio_transporte(
    total_devengado: Decimal | int | float | str,
    parametros: ParametrosNomina | None = None,
) -> EvaluacionAuxilio:
    """Evalúa el auxilio de transporte a partir del total devengado.

    Se usa el total devengado (no el sueldo solo) porque el SRS ordena comparar
    ``Sueldo Básico + Total Recargos`` contra el tope de 2 SMMLV.

    Args:
        total_devengado: Suma de sueldo básico y recargos del periodo.
        parametros: Parámetros de nómina; si es `None` se usan los vigentes
            (SMMLV, valor del auxilio y tope).

    Returns:
        `EvaluacionAuxilio` con el valor a pagar, la diferencia hasta el tope,
        el excedente (si lo hay) y el mensaje para la UI.

    Raises:
        ValueError: Si el total devengado es negativo o no es numérico.
    """
    parametros_efectivos = parametros if parametros is not None else obtener_parametros()
    devengado = a_decimal(total_devengado, "total devengado")
    if devengado < Decimal("0"):
        raise ValueError(
            f"El campo 'total devengado' no puede ser negativo; se recibió {devengado}."
        )

    tope = parametros_efectivos.tope_auxilio_transporte
    # La condición del SRS es estricta: sólo se pierde el auxilio cuando el
    # devengado SUPERA el tope, por lo que igualarlo conserva el beneficio.
    aplica = devengado <= tope

    if aplica:
        diferencia = redondear_dinero(tope - devengado)
        valor = parametros_efectivos.valor_auxilio_transporte
        excedente = Decimal("0.00")
        if diferencia == Decimal("0.00"):
            mensaje = "Aplica Auxilio de Transporte. Estás exactamente en el tope de 2 SMMLV."
        else:
            mensaje = (
                "Aplica Auxilio de Transporte. "
                f"Te faltan {formatear_cop(diferencia)} para alcanzar el tope de 2 SMMLV."
            )
    else:
        diferencia = Decimal("0.00")
        valor = Decimal("0.00")
        excedente = redondear_dinero(devengado - tope)
        mensaje = MENSAJE_SIN_AUXILIO

    return EvaluacionAuxilio(
        total_devengado=redondear_dinero(devengado),
        tope=redondear_dinero(tope),
        aplica=aplica,
        valor=redondear_dinero(valor),
        diferencia_hasta_tope=diferencia,
        excedente=excedente,
        mensaje=mensaje,
    )


def evaluar_auxilio_salarial(
    sueldo_basico: Decimal | int | float | str,
    total_recargos: Decimal | int | float | str = Decimal("0"),
    parametros: ParametrosNomina | None = None,
) -> EvaluacionAuxilio:
    """Evalúa el auxilio a partir del sueldo básico y los recargos.

    Es la variante que usará el formulario de "Mis Finanzas": recibe los dos
    valores que el usuario ya tiene en pantalla y aplica la suma del SRS.

    Args:
        sueldo_basico: Sueldo básico del periodo.
        total_recargos: Dinero total por horas extras y recargos.
        parametros: Parámetros de nómina; si es `None` se usan los vigentes.

    Returns:
        `EvaluacionAuxilio` con el resultado de la validación.

    Raises:
        ValueError: Si algún monto es negativo.

    Note:
        La importación de `calcular_total_devengado` es local para evitar un
        ciclo de importación (`nomina` importa `auxilio` para la liquidación
        automática).
    """
    from app.servicios.nomina import calcular_total_devengado

    devengado = calcular_total_devengado(sueldo_basico, total_recargos)
    return evaluar_auxilio_transporte(devengado, parametros)
