"""Utilidades de formato para la interfaz (pesos colombianos, porcentajes y fechas).

Se implementan aquí para no depender de librerías externas de internacionalización
y para garantizar que el formato monetario sea **idéntico** en todas las vistas.
La conversión numérica segura proviene de `app.core.numeros` (fuente única).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from app.core.numeros import a_decimal

MESES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def formatear_cop(valor: Decimal | int | float | str, con_simbolo: bool = True) -> str:
    """Formatea un monto como pesos colombianos con separador de miles.

    Ejemplo: ``1234567.5`` → ``"$1.234.568"``.

    SRS v1.6: los montos se muestran sin centavos en todo el programa, por
    lo que se redondean al peso entero. Los cálculos internos conservan los
    centavos; sólo cambia la presentación.

    Args:
        valor: Monto a formatear.
        con_simbolo: Si es `True`, antepone el símbolo ``$``.

    Returns:
        Cadena lista para mostrar en la interfaz.

    Raises:
        ValueError: Si el valor no es numérico.
    """
    numero = a_decimal(valor, "monto").quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    signo = "-" if numero < 0 else ""
    entero_con_puntos = f"{abs(int(numero)):,}".replace(",", ".")
    prefijo = "$" if con_simbolo else ""
    return f"{signo}{prefijo}{entero_con_puntos}"


def formatear_porcentaje(valor: Decimal | int | float | str, decimales: int = 2) -> str:
    """Formatea un porcentaje con coma decimal y símbolo ``%``.

    Args:
        valor: Porcentaje a mostrar (ej. ``4`` o ``66.67``).
        decimales: Cantidad de decimales deseados.

    Returns:
        Cadena como ``"4,00 %"``.

    Raises:
        ValueError: Si el valor no es numérico.
    """
    numero = a_decimal(valor, "porcentaje").quantize(
        Decimal(f"1.{'0' * decimales}"), rounding=ROUND_HALF_UP
    )
    return f"{str(numero).replace('.', ',')} %"


def formatear_fecha(fecha: date) -> str:
    """Devuelve una fecha en formato largo en español.

    Args:
        fecha: Fecha a presentar.

    Returns:
        Cadena como ``"13 de noviembre de 2026"``.
    """
    return f"{fecha.day} de {MESES_ES[fecha.month - 1]} de {fecha.year}"


def parsear_monto(texto: str | None) -> Decimal:
    """Convierte un monto escrito por el usuario a `Decimal`.

    Acepta el formato colombiano habitual: ``"3.000.000"`` (punto de miles),
    ``"$ 3.000.000,50"`` (coma decimal) y también ``"1500.50"`` cuando el punto
    se usa como separador decimal. Los valores vacíos o con letras se rechazan
    para no producir cálculos silenciosamente erróneos.

    Args:
        texto: Cadena capturada en el formulario.

    Returns:
        El monto convertido a `Decimal` (puede ser negativo).

    Raises:
        ValueError: Si el texto está vacío o no representa un número válido.
    """
    if texto is None:
        raise ValueError("El monto es obligatorio.")

    limpio = str(texto).strip().replace("$", "").replace("\u00a0", "").replace(" ", "")
    if not limpio:
        raise ValueError("El monto es obligatorio.")

    negativo = limpio.startswith("-")
    if negativo:
        limpio = limpio[1:]

    if not re.fullmatch(r"[0-9.,]+", limpio):
        raise ValueError(f"El monto '{texto}' no es un número válido.")

    if "," in limpio:
        # Formato colombiano: los puntos son miles y la coma es decimal.
        limpio = limpio.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", limpio):
        # "3.000.000" o "1.500": puntos como separador de miles.
        limpio = limpio.replace(".", "")

    try:
        numero = Decimal(limpio)
    except InvalidOperation as error:
        raise ValueError(f"El monto '{texto}' no es un número válido.") from error

    return -numero if negativo else numero


def formatear_mes_anio(anio: int, mes: int) -> str:
    """Presenta un mes y un año en español.

    Args:
        anio: Año del periodo.
        mes: Mes del periodo (1–12).

    Returns:
        Cadena como ``"Marzo de 2026"``.

    Raises:
        ValueError: Si el mes está fuera del rango 1–12.
    """
    if not 1 <= mes <= 12:
        raise ValueError(f"El mes debe estar entre 1 y 12; se recibió {mes}.")
    return f"{MESES_ES[mes - 1].capitalize()} de {anio}"


def parsear_periodo_mes(texto: str | None) -> tuple[int, int] | None:
    """Convierte un periodo ``"AAAA-MM"`` en una tupla ``(año, mes)``.

    Es el formato que entrega un ``<input type="month">``.

    Args:
        texto: Cadena con el periodo, por ejemplo ``"2026-03"``.

    Returns:
        Tupla ``(anio, mes)`` o `None` si el campo viene vacío.

    Raises:
        ValueError: Si el formato no es ``AAAA-MM`` o el mes está fuera de 1–12.
    """
    if texto is None or not str(texto).strip():
        return None

    coincidencia = re.fullmatch(r"(\d{4})-(\d{2})", str(texto).strip())
    if coincidencia is None:
        raise ValueError("El periodo debe tener el formato AAAA-MM.")

    anio, mes = int(coincidencia.group(1)), int(coincidencia.group(2))
    if not 1 <= mes <= 12:
        raise ValueError("El mes del periodo debe estar entre 01 y 12.")
    return anio, mes
