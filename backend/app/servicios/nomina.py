"""Motor de nómina colombiana — Tarea 2.

Responsabilidad
---------------
Implementar como **funciones puras** las reglas salariales parametrizadas en
`app.core.config`:

1. Valor de la hora ordinaria sobre una jornada mensual de 210 horas.
2. Deducciones de ley del empleado (4% salud + 4% pensión), sólo lectura.
3. Matriz de recargos y horas extras con soporte decimal.
4. Liquidación de un periodo con desglose transparente.

Ninguna función imprime, persiste ni conoce HTTP: reciben `Decimal`, devuelven
dataclasses inmutables. El auxilio de transporte (Tarea 3) y las incapacidades
(Tarea 4) se reciben como parámetros explícitos para no mezclar responsabilidades.

Convenciones de cálculo:
- Todo el dinero se maneja con `Decimal`; nunca `float`.
- El valor de la hora ordinaria se redondea a 4 decimales antes de multiplicar
  por los factores, y el resultado monetario a 2 decimales.
- "Total devengado" sigue la definición del SRS (RF-07): sueldo básico +
  total de recargos, **sin** incluir el auxilio de transporte.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from app.core.config import (
    ETIQUETAS_TIPO_HORA,
    FACTORES_RECARGO,
    ParametrosNomina,
    obtener_parametros,
)
from app.core.numeros import a_decimal, redondear_dinero, redondear_hora, sumar_dinero
from app.servicios.auxilio import EvaluacionAuxilio, evaluar_auxilio_transporte

CERO = Decimal("0")


def _obtener_parametros(parametros: ParametrosNomina | None) -> ParametrosNomina:
    """Resuelve los parámetros de nómina a usar en el cálculo.

    Args:
        parametros: Parámetros explícitos (útil en pruebas). Si es `None` se
            usan los vigentes de la aplicación.

    Returns:
        Los parámetros de nómina efectivos.
    """
    return parametros if parametros is not None else obtener_parametros()


def _validar_no_negativo(valor: Decimal, campo: str) -> None:
    """Verifica que un valor no sea negativo.

    Args:
        valor: Valor ya convertido a `Decimal`.
        campo: Nombre del campo para el mensaje de error.

    Raises:
        ValueError: Si el valor es menor que cero.
    """
    if valor < CERO:
        raise ValueError(f"El campo '{campo}' no puede ser negativo; se recibió {valor}.")


@dataclass(frozen=True)
class DeduccionesLey:
    """Deducciones obligatorias del empleado calculadas sobre el sueldo básico.

    Attributes:
        salud: Aporte de salud (4% por defecto).
        pension: Aporte de pensión (4% por defecto).
        total: Suma de ambos aportes.
    """

    salud: Decimal
    pension: Decimal
    total: Decimal


@dataclass(frozen=True)
class RecargoCalculado:
    """Resultado del cálculo de un tipo de hora extra o recargo.

    Attributes:
        tipo_hora: Clave del enum `tipo_hora` (ej. ``EXTRA_NOCTURNA``).
        etiqueta: Texto legible para la interfaz.
        cantidad_horas: Horas registradas (admite decimales).
        factor: Factor multiplicador aplicado.
        valor_hora: Valor de la hora ordinaria usado como base.
        valor_total: Dinero a pagar por esas horas.
    """

    tipo_hora: str
    etiqueta: str
    cantidad_horas: Decimal
    factor: Decimal
    valor_hora: Decimal
    valor_total: Decimal


@dataclass(frozen=True)
class ResultadoRecargos:
    """Conjunto de recargos liquidados en un periodo.

    Attributes:
        detalle: Registros calculados, en el orden canónico de la matriz.
        total_horas: Horas extras y recargos sumados.
        total_valor: Dinero total por recargos.
    """

    detalle: tuple[RecargoCalculado, ...]
    total_horas: Decimal
    total_valor: Decimal


@dataclass(frozen=True)
class LiquidacionNomina:
    """Resultado completo de liquidar un periodo de nómina.

    Attributes:
        sueldo_basico: Sueldo del periodo (mensual o proporción quincenal).
        valor_hora_ordinaria: Base de cálculo (sueldo / 210).
        total_horas_extra: Horas extras y recargos registrados.
        total_recargos: Dinero por horas extras y recargos.
        deducciones_ley: Salud y pensión.
        auxilio_transporte: Auxilio aplicado (0 si no tiene derecho).
        deduccion_incapacidad: Descuento por los días 3+ de la incapacidad del periodo.
        total_devengado: Sueldo + recargos (definición del SRS, sin auxilio).
        total_ingresos: Total devengado + auxilio de transporte.
        total_deducciones: Salud + pensión + incapacidad.
        saldo_bolsillo: Total de ingresos menos deducciones.
        detalle_recargos: Desglose por tipo de hora.
        evaluacion_auxilio: Evaluación del tope de 2 SMMLV cuando la liquidación
            se ejecutó con `aplicar_auxilio_legal=True`; en caso contrario `None`.
    """

    sueldo_basico: Decimal
    valor_hora_ordinaria: Decimal
    total_horas_extra: Decimal
    total_recargos: Decimal
    deducciones_ley: DeduccionesLey
    auxilio_transporte: Decimal
    deduccion_incapacidad: Decimal
    total_devengado: Decimal
    total_ingresos: Decimal
    total_deducciones: Decimal
    saldo_bolsillo: Decimal
    detalle_recargos: tuple[RecargoCalculado, ...] = ()
    evaluacion_auxilio: EvaluacionAuxilio | None = None

    def como_diccionario(self) -> dict[str, Decimal | str]:
        """Serializa la liquidación para vistas HTMX o respuestas JSON.

        Los `Decimal` se convierten a cadena para conservar exactitud al viajar
        por JSON (JavaScript no distingue decimales exactos).

        Returns:
            Diccionario plano con los totales y las deducciones de ley.
        """
        datos: dict[str, Decimal | str] = {
            "sueldo_basico": str(self.sueldo_basico),
            "valor_hora_ordinaria": str(self.valor_hora_ordinaria),
            "total_horas_extra": str(self.total_horas_extra),
            "total_recargos": str(self.total_recargos),
            "deduccion_salud": str(self.deducciones_ley.salud),
            "deduccion_pension": str(self.deducciones_ley.pension),
            "auxilio_transporte": str(self.auxilio_transporte),
            "deduccion_incapacidad": str(self.deduccion_incapacidad),
            "total_devengado": str(self.total_devengado),
            "total_ingresos": str(self.total_ingresos),
            "total_deducciones": str(self.total_deducciones),
            "saldo_bolsillo": str(self.saldo_bolsillo),
        }

        # La evaluación del tope sólo existe cuando se aplicó la regla legal.
        if self.evaluacion_auxilio is not None:
            datos["aplica_auxilio"] = "si" if self.evaluacion_auxilio.aplica else "no"
            datos["mensaje_auxilio"] = self.evaluacion_auxilio.mensaje

        return datos


def calcular_valor_hora_ordinaria(
    sueldo_basico: Decimal | int | float | str,
    parametros: ParametrosNomina | None = None,
) -> Decimal:
    """Calcula el valor de la hora ordinaria de trabajo.

    Regla de negocio (SRS RF-06): el sueldo básico mensual se divide entre la
    jornada legal de 210 horas mensuales (42 horas semanales).

    Args:
        sueldo_basico: Sueldo básico mensual del periodo.
        parametros: Parámetros de nómina; si es `None` se usan los vigentes.

    Returns:
        Valor de la hora ordinaria redondeado a 4 decimales.

    Raises:
        ValueError: Si el sueldo es negativo o la jornada configurada no es
            positiva.
    """
    parametros_efectivos = _obtener_parametros(parametros)
    sueldo = a_decimal(sueldo_basico, "sueldo básico")
    _validar_no_negativo(sueldo, "sueldo básico")

    horas = parametros_efectivos.horas_mensuales
    if horas <= CERO:
        raise ValueError(f"La jornada mensual debe ser mayor que cero; se configuró {horas}.")

    return redondear_hora(sueldo / horas)


def calcular_deducciones_ley(
    sueldo_basico: Decimal | int | float | str,
    parametros: ParametrosNomina | None = None,
) -> DeduccionesLey:
    """Calcula las deducciones obligatorias de salud y pensión.

    Ambas se aplican sobre la base que se pasa como argumento. En la liquidación
    de Mis Finanzas esa base es el salario devengado (sueldo + horas extras y
    recargos − incapacidad), según SRS v1.4.

    Args:
        sueldo_basico: Base de cotización del periodo (salario devengado).
        parametros: Parámetros de nómina; si es `None` se usan los vigentes.

    Returns:
        Instancia `DeduccionesLey` con salud, pensión y total.

    Raises:
        ValueError: Si el sueldo es negativo.
    """
    parametros_efectivos = _obtener_parametros(parametros)
    sueldo = a_decimal(sueldo_basico, "sueldo básico")
    _validar_no_negativo(sueldo, "sueldo básico")

    salud = redondear_dinero(sueldo * parametros_efectivos.porcentaje_salud)
    pension = redondear_dinero(sueldo * parametros_efectivos.porcentaje_pension)
    return DeduccionesLey(salud=salud, pension=pension, total=sumar_dinero(salud, pension))


def calcular_recargo(
    tipo_hora: str,
    cantidad_horas: Decimal | int | float | str,
    valor_hora: Decimal | int | float | str,
) -> RecargoCalculado:
    """Calcula un único registro de hora extra o recargo.

    Fórmula: ``cantidad_horas × valor_hora × factor``.

    Args:
        tipo_hora: Clave de la matriz de factores (ej. ``RECARGO_NOCTURNO``).
        cantidad_horas: Horas registradas; admite decimales (ej. ``10.4``).
        valor_hora: Valor de la hora ordinaria del periodo.

    Returns:
        Registro `RecargoCalculado` con el desglose completo.

    Raises:
        ValueError: Si el tipo de hora no existe, o si las horas o el valor de
            la hora son negativos.
    """
    if tipo_hora not in FACTORES_RECARGO:
        permitidos = ", ".join(FACTORES_RECARGO)
        raise ValueError(f"Tipo de hora no válido: {tipo_hora!r}. Permitidos: {permitidos}.")

    horas = a_decimal(cantidad_horas, "cantidad de horas")
    base = a_decimal(valor_hora, "valor de la hora")
    _validar_no_negativo(horas, "cantidad de horas")
    _validar_no_negativo(base, "valor de la hora")

    factor = FACTORES_RECARGO[tipo_hora]
    total = redondear_dinero(horas * base * factor)

    return RecargoCalculado(
        tipo_hora=tipo_hora,
        etiqueta=ETIQUETAS_TIPO_HORA[tipo_hora],
        cantidad_horas=horas,
        factor=factor,
        valor_hora=base,
        valor_total=total,
    )


def calcular_recargos(
    horas_por_tipo: Mapping[str, Decimal | int | float | str] | None,
    valor_hora: Decimal | int | float | str,
) -> ResultadoRecargos:
    """Liquida la matriz completa de horas extras y recargos.

    Args:
        horas_por_tipo: Mapa ``tipo_hora → cantidad de horas``. Los tipos con
            cero horas pueden omitirse. Si es `None` no hay recargos.
        valor_hora: Valor de la hora ordinaria del periodo.

    Returns:
        `ResultadoRecargos` con el detalle en el orden canónico de la matriz y
        los totales de horas y dinero.

    Raises:
        ValueError: Si algún tipo no existe o alguna cantidad es negativa.
    """
    base = a_decimal(valor_hora, "valor de la hora")
    _validar_no_negativo(base, "valor de la hora")

    registros = horas_por_tipo or {}
    detalle: list[RecargoCalculado] = []

    # Se recorre el orden canónico (no el del diccionario recibido) para que el
    # desglose mostrado al usuario sea siempre el mismo.
    for tipo in FACTORES_RECARGO:
        if tipo not in registros:
            continue
        calculado = calcular_recargo(tipo, registros[tipo], base)
        if calculado.cantidad_horas == CERO:
            continue
        detalle.append(calculado)

    total_horas = redondear_hora(sum((item.cantidad_horas for item in detalle), CERO), 2)
    total_valor = sumar_dinero(*(item.valor_total for item in detalle))

    return ResultadoRecargos(
        detalle=tuple(detalle),
        total_horas=total_horas,
        total_valor=total_valor,
    )


def calcular_total_devengado(
    sueldo_basico: Decimal | int | float | str,
    total_recargos: Decimal | int | float | str,
) -> Decimal:
    """Calcula el total devengado según la definición del SRS (RF-07).

    ``Total devengado = Sueldo básico + Total recargos``. El auxilio de
    transporte **no** forma parte de esta base, porque es el valor que se compara
    contra el tope de 2 SMMLV en la Tarea 3.

    Args:
        sueldo_basico: Sueldo básico del periodo.
        total_recargos: Dinero total por horas extras y recargos.

    Returns:
        Total devengado redondeado a centavos.

    Raises:
        ValueError: Si algún valor es negativo.
    """
    sueldo = a_decimal(sueldo_basico, "sueldo básico")
    recargos = a_decimal(total_recargos, "total de recargos")
    _validar_no_negativo(sueldo, "sueldo básico")
    _validar_no_negativo(recargos, "total de recargos")
    return sumar_dinero(sueldo, recargos)


def liquidar_periodo(
    sueldo_basico: Decimal | int | float | str,
    horas_por_tipo: Mapping[str, Decimal | int | float | str] | None = None,
    auxilio_transporte: Decimal | int | float | str = CERO,
    deduccion_incapacidad: Decimal | int | float | str = CERO,
    aplicar_auxilio_legal: bool = False,
    parametros: ParametrosNomina | None = None,
) -> LiquidacionNomina:
    """Liquida un periodo de nómina completo con desglose transparente.

    Orquesta las funciones anteriores. Por defecto el auxilio de transporte se
    recibe ya calculado, de modo que el motor salarial no mezcle reglas de otras
    tareas. Con ``aplicar_auxilio_legal=True`` se evalúa automáticamente el tope
    de 2 SMMLV (Tarea 3) usando el total devengado.

    Args:
        sueldo_basico: Sueldo básico del periodo (mensual o quincena prorrateada).
        horas_por_tipo: Horas extras y recargos por tipo.
        auxilio_transporte: Auxilio explícito a sumar (0 si no aplica). No debe
            enviarse junto con `aplicar_auxilio_legal=True`.
        deduccion_incapacidad: Descuento por incapacidad a restar (Tarea 4).
        aplicar_auxilio_legal: Si es `True`, calcula el auxilio según el tope de
            2 SMMLV e incorpora la evaluación al resultado.
        parametros: Parámetros de nómina; si es `None` se usan los vigentes.

    Returns:
        `LiquidacionNomina` con todos los totales, el detalle de recargos y la
        evaluación del auxilio cuando corresponde.

    Raises:
        ValueError: Si algún valor es negativo, si un tipo de hora no existe o si
            se envían simultáneamente un auxilio explícito y la evaluación legal.
    """
    parametros_efectivos = _obtener_parametros(parametros)
    sueldo = a_decimal(sueldo_basico, "sueldo básico")
    auxilio = a_decimal(auxilio_transporte, "auxilio de transporte")
    incapacidad = a_decimal(deduccion_incapacidad, "deducción por incapacidad")
    _validar_no_negativo(sueldo, "sueldo básico")
    _validar_no_negativo(auxilio, "auxilio de transporte")
    _validar_no_negativo(incapacidad, "deducción por incapacidad")

    if aplicar_auxilio_legal and auxilio != CERO:
        raise ValueError(
            "No envíes un auxilio explícito junto con 'aplicar_auxilio_legal=True': "
            "la regla legal ya determina el valor."
        )

    valor_hora = calcular_valor_hora_ordinaria(sueldo, parametros_efectivos)
    recargos = calcular_recargos(horas_por_tipo, valor_hora)
    total_devengado = calcular_total_devengado(sueldo, recargos.total_valor)

    # SRS v1.4: salud y pensión se calculan sobre el salario que realmente se
    # devenga: sueldo + horas extras y recargos − descuento por incapacidad.
    base_cotizacion = redondear_dinero(max(total_devengado - incapacidad, CERO))
    deducciones = calcular_deducciones_ley(base_cotizacion, parametros_efectivos)

    # Evaluación automática del auxilio (Tarea 3). Se hace después de conocer los
    # recargos porque el SRS compara "sueldo + recargos" contra los 2 SMMLV.
    evaluacion: EvaluacionAuxilio | None = None
    if aplicar_auxilio_legal:
        evaluacion = evaluar_auxilio_transporte(total_devengado, parametros_efectivos)
        auxilio = evaluacion.valor

    total_ingresos = sumar_dinero(total_devengado, auxilio)
    total_deducciones = sumar_dinero(deducciones.total, incapacidad)

    return LiquidacionNomina(
        sueldo_basico=redondear_dinero(sueldo),
        valor_hora_ordinaria=valor_hora,
        total_horas_extra=recargos.total_horas,
        total_recargos=recargos.total_valor,
        deducciones_ley=deducciones,
        auxilio_transporte=redondear_dinero(auxilio),
        deduccion_incapacidad=redondear_dinero(incapacidad),
        total_devengado=total_devengado,
        total_ingresos=total_ingresos,
        total_deducciones=total_deducciones,
        saldo_bolsillo=redondear_dinero(total_ingresos - total_deducciones),
        detalle_recargos=recargos.detalle,
        evaluacion_auxilio=evaluacion,
    )
