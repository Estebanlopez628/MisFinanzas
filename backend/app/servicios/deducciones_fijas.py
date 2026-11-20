"""Deducciones fijas del salario (SRS v1.4, REQ-08; vinculación SRS v1.9).

Responsabilidad
---------------
Registrar, editar y eliminar los descuentos que la empresa aplica por nómina
antes del pago (cuotas de libranza, fondos, seguros empresariales), y sumar
cuánto se descuenta en cada quincena.

Vinculación con deudas (SRS v1.9, ADR-56): una libranza es a la vez un descuento de
nómina y un crédito con cuotas. Si la deducción se vincula a una deuda mensual, su
valor es la cuota de esa deuda y la deuda lleva el conteo de cuotas. Así el dinero
se cuenta una sola vez: la deducción en la quincena y la cuota fuera de la dona de
deudas. Cuando la deuda queda pagada, la deducción deja de descontarse.

La tabla `deducciones_fijas` está definida en `diccionario_datos.md` §9.3. Estas
deducciones no son las de ley (salud y pensión): esas viven en `nomina.py`.

Regla de negocio: la deducción se resta del pago de la quincena indicada **antes**
de calcular el saldo libre; por eso `quincenas.py` consume los totales de este
servicio.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import Deuda, DeduccionFija
from app.servicios import deudas as servicio_deudas

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


def _deuda_vinculable(bd: Session, id_usuario: str, id_deuda: str | None) -> Deuda | None:
    """Busca la deuda a la que se quiere vincular la deducción (SRS v1.9).

    Solo se vinculan deudas del propio usuario, activas y mensuales. Una deuda
    quincenal necesitaría dos deducciones por mes, y eso no se modela todavía.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deducción.
        id_deuda: Identificador elegido en el formulario; vacío significa sin vínculo.

    Returns:
        La deuda vinculable, o `None` si la deducción no está vinculada.

    Raises:
        ValueError: Si la deuda no existe, es de otro usuario, ya está pagada o no
            es mensual.
    """
    texto = (id_deuda or "").strip()
    if not texto:
        return None
    deuda = bd.get(Deuda, texto)
    if deuda is None or deuda.id_usuario != id_usuario:
        raise ValueError("La deuda elegida no existe.")
    if deuda.estado != servicio_deudas.ESTADO_ACTIVA:
        raise ValueError("Esa deuda ya está pagada; no se puede vincular a una deducción.")
    if deuda.periodicidad != servicio_deudas.PERIODICIDAD_MENSUAL:
        raise ValueError("Solo se pueden vincular deudas que se pagan cada mes.")
    return deuda


def crear_deduccion(
    bd: Session,
    id_usuario: str,
    descripcion: str,
    valor: Decimal | str | int | float,
    quincena: int | str,
    id_deuda: str | None = None,
) -> DeduccionFija:
    """Registra una deducción fija del salario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deducción.
        descripcion: Concepto (por ejemplo, «Libranza banco X»).
        valor: Monto por pago; no puede ser negativo. Si hay deuda vinculada, se
            ignora y se usa la cuota mensual de la deuda.
        quincena: `1` o `2`, pago del que se descuenta.
        id_deuda: Deuda que esta deducción paga cada mes; vacío si no aplica.

    Returns:
        La deducción persistida.

    Raises:
        ValueError: Si la validación falla (ver `_validar` y `_deuda_vinculable`).
    """
    texto, monto, numero = _validar(descripcion, valor, quincena)
    deuda = _deuda_vinculable(bd, id_usuario, id_deuda)
    if deuda is not None:
        # SRS v1.9: el descuento de nómina y la cuota son el mismo dinero; se toma
        # la cuota de la deuda para que no puedan quedar con montos distintos.
        monto = redondear_dinero(deuda.cuota_mensual or CERO)
    deduccion = DeduccionFija(
        id_usuario=id_usuario,
        descripcion=texto,
        valor=monto,
        quincena=numero,
        id_deuda=deuda.id_deuda if deuda is not None else None,
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
    id_deuda: str | None = None,
) -> DeduccionFija | None:
    """Modifica una deducción existente del usuario.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la deducción (evita editar datos ajenos).
        id_deduccion: Identificador de la deducción.
        descripcion: Nuevo concepto.
        valor: Nuevo monto por pago; con deuda vinculada se usa la cuota de la deuda.
        quincena: Nueva quincena de descuento.
        id_deuda: Deuda vinculada; vacío quita el vínculo.

    Returns:
        La deducción actualizada, o `None` si no existe o es de otro usuario.

    Raises:
        ValueError: Si la validación falla.
    """
    deduccion = bd.get(DeduccionFija, id_deduccion)
    if deduccion is None or deduccion.id_usuario != id_usuario:
        return None
    texto, monto, numero = _validar(descripcion, valor, quincena)
    deuda = _deuda_vinculable(bd, id_usuario, id_deuda)
    if deuda is not None:
        monto = redondear_dinero(deuda.cuota_mensual or CERO)
    deduccion.descripcion = texto
    deduccion.valor = monto
    deduccion.quincena = numero
    deduccion.id_deuda = deuda.id_deuda if deuda is not None else None
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
    """Lista todas las deducciones fijas del usuario, también las de deudas pagadas.

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


def listar_vigentes(bd: Session, id_usuario: str) -> list[DeduccionFija]:
    """Lista las deducciones que hoy se descuentan del salario (SRS v1.9).

    Una deducción vinculada a una deuda pagada deja de descontarse y no aparece aquí.
    Las deducciones sin vínculo siempre están vigentes.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deducciones.

    Returns:
        Deducciones vigentes, ordenadas por quincena y descripción.
    """
    consulta = (
        select(DeduccionFija)
        .outerjoin(Deuda, Deuda.id_deuda == DeduccionFija.id_deuda)
        .where(
            DeduccionFija.id_usuario == id_usuario,
            or_(DeduccionFija.id_deuda.is_(None), Deuda.estado == servicio_deudas.ESTADO_ACTIVA),
        )
        .order_by(DeduccionFija.quincena, DeduccionFija.descripcion)
    )
    return list(bd.scalars(consulta))


def vinculadas_activas(bd: Session, id_usuario: str) -> list[DeduccionFija]:
    """Lista las deducciones vinculadas a deudas que siguen activas.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deducciones.

    Returns:
        Deducciones con `id_deuda` cuya deuda todavía tiene cuotas.
    """
    return [fila for fila in listar_vigentes(bd, id_usuario) if fila.id_deuda is not None]


def cuota_de_vinculadas(bd: Session, id_usuario: str) -> Decimal:
    """Suma la cuota mensual de las deudas vinculadas que siguen activas.

    Esa cuota ya se descuenta como deducción fija; por eso se quita de la cuota de
    deudas de la dona y del diagnóstico para no contarla dos veces.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de las deducciones.

    Returns:
        Total mensual redondeado a centavos.
    """
    return redondear_dinero(
        sum(
            (servicio_deudas.cuota_mensual_equivalente(fila.deuda) for fila in vinculadas_activas(bd, id_usuario)),
            start=CERO,
        )
    )


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
