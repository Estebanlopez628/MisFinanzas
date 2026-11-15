"""Perfil financiero del usuario (onboarding).

Responsabilidad
---------------
Guardar y recuperar la configuración salarial —sueldo básico, modalidad de pago,
porcentajes de cada quincena y quincena donde se aplican las deducciones— y
derivar el sueldo del periodo que se liquida.

El perfil es 1:1 con el usuario (`perfiles_financieros`, §2 del diccionario).
Cuando la modalidad es QUINCENAL, los porcentajes de las dos quincenas deben
sumar 100 %; el usuario puede informarlos directamente o entregar el valor neto
de la quincena sin deducciones para que el sistema los calcule.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import obtener_parametros
from app.core.numeros import a_decimal, redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import PerfilFinanciero
from app.servicios.auxilio import evaluar_auxilio_transporte

MODALIDAD_MENSUAL = "MENSUAL"
MODALIDAD_QUINCENAL = "QUINCENAL"
MODALIDADES_VALIDAS = (MODALIDAD_MENSUAL, MODALIDAD_QUINCENAL)

QUINCENA_PRIMERA = 1
QUINCENA_SEGUNDA = 2
QUINCENAS_VALIDAS = (QUINCENA_PRIMERA, QUINCENA_SEGUNDA)

CIEN = Decimal("100")
CERO = Decimal("0")
UN_CENTAVO = Decimal("0.01")


def obtener_perfil(bd: Session, id_usuario: str) -> PerfilFinanciero | None:
    """Devuelve el perfil financiero del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil.

    Returns:
        El perfil o `None` si aún no ha hecho el onboarding.
    """
    return bd.scalar(
        select(PerfilFinanciero).where(PerfilFinanciero.id_usuario == id_usuario)
    )


def perfil_configurado(bd: Session, id_usuario: str) -> bool:
    """Indica si el usuario ya completó su configuración inicial.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Usuario a verificar.

    Returns:
        `True` si existe un perfil financiero para el usuario.
    """
    return obtener_perfil(bd, id_usuario) is not None


def _validar_porcentaje(valor: Decimal | str, etiqueta: str) -> Decimal:
    """Valida un porcentaje quincenal individual.

    Args:
        valor: Porcentaje a validar.
        etiqueta: Nombre visible del campo, para el mensaje de error.

    Returns:
        El porcentaje redondeado a dos decimales.

    Raises:
        ValueError: Si el valor no es numérico o no está entre 0,01 y 99,99.
    """
    numero = a_decimal(valor, etiqueta).quantize(UN_CENTAVO, rounding=ROUND_HALF_UP)
    if not (UN_CENTAVO <= numero < CIEN):
        raise ValueError(f"{etiqueta} debe estar entre 0,01 y 99,99.")
    return numero


def validar_quincenas(
    porcentaje_quincena_1: Decimal | str,
    porcentaje_quincena_2: Decimal | str,
    quincena_deducciones: int | str,
) -> tuple[Decimal, Decimal, int]:
    """Valida los porcentajes y la quincena donde se descuentan las deducciones.

    Args:
        porcentaje_quincena_1: Porcentaje del sueldo pagado en la quincena 1.
        porcentaje_quincena_2: Porcentaje del sueldo pagado en la quincena 2.
        quincena_deducciones: `1` o `2`, quincena que soporta salud y pensión.

    Returns:
        Tupla `(porcentaje_1, porcentaje_2, quincena_deducciones)` normalizada.

    Raises:
        ValueError: Si los porcentajes no suman 100 % o la quincena no es válida.
    """
    primero = _validar_porcentaje(porcentaje_quincena_1, "El porcentaje de la quincena 1")
    segundo = _validar_porcentaje(porcentaje_quincena_2, "El porcentaje de la quincena 2")

    if abs((primero + segundo) - CIEN) > UN_CENTAVO:
        raise ValueError("Los porcentajes de las dos quincenas deben sumar 100 %.")

    try:
        deducciones = int(quincena_deducciones)
    except (TypeError, ValueError) as error:
        raise ValueError("Debes indicar en qué quincena se aplican las deducciones.") from error

    if deducciones not in QUINCENAS_VALIDAS:
        raise ValueError("La quincena de deducciones debe ser 1 o 2.")

    return primero, segundo, deducciones


def calcular_quincenas_desde_neto(
    sueldo_basico: Decimal | str,
    neto_sin_deducciones: Decimal | str,
    quincena_sin_deducciones: int | str,
) -> tuple[Decimal, Decimal, int]:
    """Calcula los porcentajes a partir del neto de la quincena sin descuentos.

    Si el usuario no conoce sus porcentajes, informa cuánto recibe en la
    quincena donde **no** le aplican salud ni pensión. Como esa quincena no tiene
    descuentos, el valor recibido equivale al devengado; el resto del sueldo
    corresponde a la otra quincena, que es la sujeta a deducciones.

    Args:
        sueldo_basico: Salario mensual base.
        neto_sin_deducciones: Valor recibido en la quincena sin deducciones.
        quincena_sin_deducciones: `1` o `2`, quincena a la que corresponde el valor.

    Returns:
        Tupla `(porcentaje_1, porcentaje_2, quincena_deducciones)`.

    Raises:
        ValueError: Si el sueldo no es positivo, el neto está fuera de rango o la
            quincena no es válida.
    """
    sueldo = redondear_dinero(parsear_monto(str(sueldo_basico)))
    if sueldo <= CERO:
        raise ValueError("El sueldo básico debe ser mayor que cero.")

    neto = redondear_dinero(parsear_monto(str(neto_sin_deducciones)))
    if neto <= CERO or neto >= sueldo:
        raise ValueError(
            "El valor neto debe ser mayor que cero y menor que el sueldo básico."
        )

    try:
        quincena = int(quincena_sin_deducciones)
    except (TypeError, ValueError) as error:
        raise ValueError("La quincena sin deducciones debe ser 1 o 2.") from error

    if quincena not in QUINCENAS_VALIDAS:
        raise ValueError("La quincena sin deducciones debe ser 1 o 2.")

    porcentaje_sin = (neto / sueldo * CIEN).quantize(UN_CENTAVO, rounding=ROUND_HALF_UP)
    porcentaje_con = (CIEN - porcentaje_sin).quantize(UN_CENTAVO, rounding=ROUND_HALF_UP)

    if quincena == QUINCENA_PRIMERA:
        return porcentaje_sin, porcentaje_con, QUINCENA_SEGUNDA
    return porcentaje_con, porcentaje_sin, QUINCENA_PRIMERA


def guardar_perfil(
    bd: Session,
    id_usuario: str,
    sueldo_basico: Decimal | str,
    modalidad: str,
    porcentaje_quincena_1: Decimal | str | None = None,
    porcentaje_quincena_2: Decimal | str | None = None,
    quincena_deducciones: int | str | None = None,
) -> PerfilFinanciero:
    """Crea o actualiza el perfil financiero.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil.
        sueldo_basico: Salario mensual base.
        modalidad: `MENSUAL` o `QUINCENAL`.
        porcentaje_quincena_1: Porcentaje pagado en la quincena 1.
        porcentaje_quincena_2: Porcentaje pagado en la quincena 2. Si se omite,
            se calcula como el complemento a 100 % del primero.
        quincena_deducciones: Quincena que soporta salud y pensión (`1` o `2`).
            Por defecto, la primera.

    Returns:
        El perfil persistido.

    Raises:
        ValueError: Si el sueldo es negativo, la modalidad no es válida o los
            porcentajes no suman 100 %.
    """
    sueldo = redondear_dinero(parsear_monto(str(sueldo_basico)))
    if sueldo < CERO:
        raise ValueError("El sueldo básico no puede ser negativo.")

    modalidad_normalizada = modalidad.strip().upper()
    if modalidad_normalizada not in MODALIDADES_VALIDAS:
        raise ValueError("La modalidad de pago debe ser MENSUAL o QUINCENAL.")

    primero: Decimal | None = None
    segundo: Decimal | None = None
    deducciones: int | None = None

    if modalidad_normalizada == MODALIDAD_QUINCENAL:
        if porcentaje_quincena_1 in (None, ""):
            raise ValueError(
                "El porcentaje de la quincena 1 es obligatorio en modalidad QUINCENAL."
            )

        if porcentaje_quincena_2 in (None, ""):
            # Compatibilidad con perfiles antiguos que solo guardaban un 50 %.
            primero = _validar_porcentaje(
                porcentaje_quincena_1, "El porcentaje de la quincena 1"
            )
            segundo = (CIEN - primero).quantize(UN_CENTAVO, rounding=ROUND_HALF_UP)
        else:
            primero = porcentaje_quincena_1
            segundo = porcentaje_quincena_2

        primero, segundo, deducciones = validar_quincenas(
            primero, segundo, quincena_deducciones or QUINCENA_PRIMERA
        )

    # El indicador de auxilio se deriva de la regla de 2 SMMLV; nunca lo edita
    # el usuario (diccionario §2).
    habilitado = evaluar_auxilio_transporte(sueldo, obtener_parametros()).aplica

    perfil = obtener_perfil(bd, id_usuario)
    if perfil is None:
        perfil = PerfilFinanciero(id_usuario=id_usuario, sueldo_basico=sueldo)
        bd.add(perfil)

    perfil.sueldo_basico = sueldo
    perfil.modalidad_pago = modalidad_normalizada
    perfil.porcentaje_quincena_1 = primero
    perfil.porcentaje_quincena_2 = segundo
    perfil.quincena_deducciones = deducciones
    perfil.auxilio_transporte_habilitado = habilitado
    bd.commit()
    bd.refresh(perfil)
    return perfil


def porcentajes_quincena(perfil: PerfilFinanciero) -> tuple[Decimal, Decimal]:
    """Devuelve los porcentajes de ambas quincenas, con 50/50 por defecto.

    Args:
        perfil: Perfil del usuario.

    Returns:
        Tupla `(porcentaje_quincena_1, porcentaje_quincena_2)`.
    """
    primero = perfil.porcentaje_quincena_1 or Decimal("50")
    segundo = perfil.porcentaje_quincena_2 or (CIEN - primero)
    return primero, segundo


def sueldo_del_periodo(perfil: PerfilFinanciero | None, quincena: int = 0) -> Decimal:
    """Calcula el sueldo que corresponde al periodo seleccionado.

    Args:
        perfil: Perfil del usuario; si es `None` no hay sueldo configurado.
        quincena: `0` = mes completo, `1` o `2` = quincena.

    Returns:
        El sueldo proporcional del periodo, redondeado a centavos.
    """
    if perfil is None:
        return CERO

    if perfil.modalidad_pago == MODALIDAD_QUINCENAL and quincena in QUINCENAS_VALIDAS:
        primero, segundo = porcentajes_quincena(perfil)
        porcentaje = primero if quincena == QUINCENA_PRIMERA else segundo
        return redondear_dinero(perfil.sueldo_basico * porcentaje / CIEN)

    return redondear_dinero(perfil.sueldo_basico)
