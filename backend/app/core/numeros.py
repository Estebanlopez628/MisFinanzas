"""Conversión y redondeo seguro de valores monetarios y de horas.

Utilidades compartidas por el motor de nómina, los formatos de presentación y
las pruebas. Se centralizan aquí para garantizar que **todo el proyecto
redondee igual** y que ningún módulo repita la lógica de conversión.

Regla financiera: los cálculos intermedios conservan precisión completa y solo
se redondea al presentar o persistir el resultado (ver `diccionario_datos.md`,
§11.4).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Unidad mínima de dinero (centavos) y de hora (diezmilésimas).
UNIDAD_DINERO = Decimal("0.01")
UNIDAD_HORA = Decimal("0.0001")


def a_decimal(
    valor: Decimal | int | float | str | None,
    campo: str = "valor",
) -> Decimal:
    """Convierte un valor numérico a `Decimal` de forma segura.

    Se convierte pasando por `str` para evitar la representación binaria de los
    `float` (por ejemplo, ``0.1`` deja de ser ``0.1000000000000000055``).

    Args:
        valor: Número en cualquier representación razonable (Decimal, int,
            float o cadena).
        campo: Nombre del campo, usado únicamente en el mensaje de error para
            facilitar la depuración.

    Returns:
        El valor convertido a `Decimal`.

    Raises:
        ValueError: Si el valor es nulo, booleano, no numérico o no finito
            (NaN / infinito).
    """
    if isinstance(valor, Decimal):
        numero = valor
    else:
        if valor is None or isinstance(valor, bool):
            raise ValueError(
                f"El campo '{campo}' requiere un número válido; se recibió {valor!r}."
            )
        try:
            numero = Decimal(str(valor).strip())
        except (InvalidOperation, ValueError) as error:
            raise ValueError(
                f"El campo '{campo}' requiere un número válido; se recibió {valor!r}."
            ) from error

    if not numero.is_finite():
        raise ValueError(
            f"El campo '{campo}' no admite valores infinitos ni NaN; se recibió {valor!r}."
        )
    return numero


def redondear_dinero(valor: Decimal | int | float | str) -> Decimal:
    """Redondea un monto a dos decimales con redondeo comercial (medio hacia arriba).

    Args:
        valor: Monto a redondear.

    Returns:
        Monto con dos decimales, listo para mostrar o persistir.

    Raises:
        ValueError: Si el valor no es numérico.
    """
    return a_decimal(valor).quantize(UNIDAD_DINERO, rounding=ROUND_HALF_UP)


def redondear_hora(valor: Decimal | int | float | str, decimales: int = 4) -> Decimal:
    """Redondea un valor unitario (por ejemplo, el valor de la hora ordinaria).

    Args:
        valor: Valor a redondear.
        decimales: Cantidad de decimales de precisión (por defecto 4).

    Returns:
        Valor redondeado con la precisión solicitada.

    Raises:
        ValueError: Si el valor no es numérico o si `decimales` es negativo.
    """
    if decimales < 0:
        raise ValueError("La cantidad de decimales no puede ser negativa.")
    unidad = Decimal(1).scaleb(-decimales)
    return a_decimal(valor).quantize(unidad, rounding=ROUND_HALF_UP)


def sumar_dinero(*montos: Decimal | int | float | str) -> Decimal:
    """Suma varios montos y devuelve el total redondeado a dos decimales.

    Args:
        *montos: Montos a sumar (al menos uno).

    Returns:
        La suma redondeada a centavos.

    Raises:
        ValueError: Si algún monto no es numérico.
    """
    total = sum((a_decimal(monto) for monto in montos), start=Decimal("0"))
    return redondear_dinero(total)
