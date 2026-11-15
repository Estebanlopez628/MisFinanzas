"""Deducciones fijas del salario (SRS v1.4, REQ-08).

Responsabilidad
---------------
Registrar, editar y eliminar los descuentos que la empresa aplica por nómina
antes del pago (cuotas de libranza, fondos, seguros empresariales), y sumar
cuánto se descuenta en cada quincena.

La tabla `deducciones_fijas` está definida en `diccionario_datos.md` §9.3. Estas
deducciones no son las de ley (salud y pensión): esas viven en `nomina.py`.

Regla de negocio: la deducción se resta del pago de la quincena indicada **antes**
de calcular el saldo libre; por eso `quincenas.py` consume los totales de este
servicio.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import DeduccionFija

CERO = Decimal("0")
QUINCENAS_VALIDAS = (1, 2)


def _validar(descripcion: str, valor: Decimal | str | int | float, quincena: int | str) -> tuple[str, Decimal, int]:
    """Valida y normaliza los datos de una deducción fija.

    Args:
        descripcion: Concepto de la deducción.
        valor: Monto por pago en pesos.
        quincena: Pago del que se descuenta (`1` o `2`).

    Returns:
        Tupla `(descripcion, valor, quincena)` normalizada.

    Raises:
        ValueError: Si falta la descripción, el valor es negativo o inválido, o la
            quincena no es 1 ni 2.
    """
    texto = descripcion.strip()
    if not texto:
        raise ValueError("La descripción de la deducción es obligatoria.")

    monto = redondear_dinero(parsear_monto(str(valor)))
    if monto < CERO:
        raise ValueError("El valor de la deducción no puede ser negativo.")

    try:
        numero = int(quincena)
    except (TypeError, ValueError) as error:
        raise ValueError("La quincena de la deducción debe ser 1 o 2.") from error
    if numero not in QUINCENAS_VALIDAS:
        raise ValueError("La quincena de la deducción debe ser 1 o 2.")

    return texto[:150], monto, numero


def crear_deduccion(
    bd: Session,
    id_usuario: str,
    descripcion: str,
    valor: Decimal | str | int | float,
    quincena: int | str,
) -> DeduccionFija:
    """Registra una deducción fija del salario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deducción.
        descripcion: Concepto (por ejemplo, «Libranza banco X»).
        valor: Monto por pago; no puede ser negativo.
        quincena: `1` o `2`, pago del que se descuenta.

    Returns:
        La deducción persistida.

    Raises:
        ValueError: Si la validación falla (ver `_validar`).
    """
    texto, monto, numero = _validar(descripcion, valor, quincena)
    deduccion = DeduccionFija(
        id_usuario=id_usuario,
        descripcion=texto,
        valor=monto,
        quincena=numero,
    )
    bd.add(deduccion)
    bd.commit()
    bd.refresh(deduccion)
    return deduccion


def actualizar_deduccion(
    bd: Session,
    id_usuario: str,
    id_deduccion: str,
    descripcion: str,
    valor: Decimal | str | int | float,
    quincena: int | str,
) -> DeduccionFija | None:
    """Modifica una deducción existente del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deducción (evita editar datos ajenos).
        id_deduccion: Identificador de la deducción.
        descripcion: Nuevo concepto.
        valor: Nuevo monto por pago.
        quincena: Nueva quincena de descuento.

    Returns:
        La deducción actualizada, o `None` si no existe o es de otro usuario.

    Raises:
        ValueError: Si la validación falla.
    """
    deduccion = bd.get(DeduccionFija, id_deduccion)
    if deduccion is None or deduccion.id_usuario != id_usuario:
        return None
    texto, monto, numero = _validar(descripcion, valor, quincena)
    deduccion.descripcion = texto
    deduccion.valor = monto
    deduccion.quincena = numero
    bd.commit()
    bd.refresh(deduccion)
    return deduccion


def eliminar_deduccion(bd: Session, id_usuario: str, id_deduccion: str) -> bool:
    """Elimina una deducción fija del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deducción.
        id_deduccion: Identificador de la deducción.

    Returns:
        `True` si se eliminó; `False` si no existe o es de otro usuario.
    """
    deduccion = bd.get(DeduccionFija, id_deduccion)
    if deduccion is None or deduccion.id_usuario != id_usuario:
        return False
    bd.delete(deduccion)
    bd.commit()
    return True


def listar_deducciones(bd: Session, id_usuario: str) -> list[DeduccionFija]:
    """Lista las deducciones fijas del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deducciones.

    Returns:
        Lista ordenada por quincena y descripción.
    """
    consulta = (
        select(DeduccionFija)
        .where(DeduccionFija.id_usuario == id_usuario)
        .order_by(DeduccionFija.quincena, DeduccionFija.descripcion)
    )
    return list(bd.scalars(consulta))


def total_por_quincena(deducciones: Iterable[DeduccionFija], quincena: int) -> Decimal:
    """Suma las deducciones fijas de una quincena.

    Args:
        deducciones: Deducciones del usuario (ya filtradas o no).
        quincena: `1` o `2`.

    Returns:
        Total redondeado a centavos de las deducciones de esa quincena.
    """
    return redondear_dinero(
        sum((d.valor for d in deducciones if d.quincena == quincena), start=CERO)
    )
