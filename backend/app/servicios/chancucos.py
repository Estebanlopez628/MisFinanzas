"""Referencias de pago rápido ("Chancucos").

Responsabilidad
---------------
Guardar las referencias que el administrador usa para pagar servicios, marcar
favoritos y eliminarlas. El copiado al portapapeles y el botón *Pagar* son
mejoras de interfaz; la validación de la URL vive aquí.

SRS v1.7 (bloque D): cada atajo puede declarar uno o dos días de pago mensuales.
Se guarda solo el número del día (1–31), sin año, porque el atajo se repite todos
los meses; el distintivo «Día 15» se arma en la plantilla.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.numeros import redondear_dinero
from app.core.texto import parsear_monto
from app.modelos import Chancuco

DIAS_DEL_MES = range(1, 32)


def _normalizar_dia(dia: int | str | None, nombre: str) -> int | None:
    """Valida y convierte un día de pago mensual.

    Args:
        dia: Número, texto del formulario o `None` si no se informó.
        nombre: Etiqueta del campo para el mensaje de error.

    Returns:
        Día entre 1 y 31, o `None` cuando el campo viene vacío.

    Raises:
        ValueError: Si el valor no es un número entero entre 1 y 31.
    """
    if dia is None or (isinstance(dia, str) and not dia.strip()):
        return None
    try:
        numero = int(str(dia).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{nombre} debe ser un número entre 1 y 31.") from error
    if numero < 1 or numero > 31:
        raise ValueError(f"{nombre} debe estar entre 1 y 31.")
    return numero


def _normalizar_dias(dia_pago_1, dia_pago_2) -> tuple[int | None, int | None]:
    """Normaliza la pareja de días de pago de un atajo.

    Un segundo día igual al primero se descarta: el atajo es de un único pago.

    Args:
        dia_pago_1: Primer día del mes, si existe.
        dia_pago_2: Segundo día del mes, si existe.

    Returns:
        Tupla `(primer_dia, segundo_dia)`.

    Raises:
        ValueError: Si alguno de los días no está entre 1 y 31.
    """
    primero = _normalizar_dia(dia_pago_1, "El día de pago")
    segundo = _normalizar_dia(dia_pago_2, "El segundo día de pago")
    if segundo is not None and segundo == primero:
        segundo = None
    return primero, segundo


def _validar_url(url: str | None) -> str | None:
    """Valida que una URL de pago use HTTP o HTTPS.

    Args:
        url: Dirección opcional de la pasarela.

    Returns:
        La URL limpia o `None` si viene vacía.

    Raises:
        ValueError: Si la URL no es absoluta o usa otro esquema.
    """
    if url is None or not url.strip():
        return None
    limpia = url.strip()
    partes = urlparse(limpia)
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        raise ValueError("La URL de pago debe empezar por http:// o https://.")
    return limpia[:300]


def crear_chancuco(
    bd: Session,
    id_usuario: str,
    descripcion: str,
    numero_referencia: str,
    url_pago: str | None = None,
    favorito: bool = False,
    dia_pago_1: int | str | None = None,
    dia_pago_2: int | str | None = None,
    valor_pago: Decimal | str | int | float | None = None,
) -> Chancuco:
    """Registra un atajo de pago.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del atajo.
        descripcion: Texto libre que identifica el atajo («EPM energía»).
        numero_referencia: Número que se copia al portapapeles.
        url_pago: Pasarela oficial, si existe; es opcional porque hay recibos
            que solo se pagan en ventanilla.
        favorito: Marca inicial de favorito.
        dia_pago_1: Día del mes del pago (1–31), si se conoce.
        dia_pago_2: Segundo día del mes para un pago doble, si aplica.
        valor_pago: Monto exacto a pagar; vacío si el servicio no tiene monto fijo.

    Returns:
        El atajo persistido.

    Raises:
        ValueError: Si falta la descripción o la referencia, la URL es inválida,
            el valor no es numérico o alguno de los días no está entre 1 y 31.
    """
    descripcion_limpia = descripcion.strip()
    referencia_limpia = numero_referencia.strip()
    if not descripcion_limpia:
        raise ValueError("La descripción del atajo es obligatoria.")
    if not referencia_limpia:
        raise ValueError("El número de referencia es obligatorio.")

    primero, segundo = _normalizar_dias(dia_pago_1, dia_pago_2)
    valor = None
    if valor_pago is not None and str(valor_pago).strip():
        valor = redondear_dinero(parsear_monto(str(valor_pago)))
        if valor < 0:
            raise ValueError("El valor a pagar no puede ser negativo.")

    chancuco = Chancuco(
        id_usuario=id_usuario,
        descripcion=descripcion_limpia[:120],
        numero_referencia=referencia_limpia[:60],
        valor_pago=valor,
        url_pago=_validar_url(url_pago),
        favorito=favorito,
        dia_pago_1=primero,
        dia_pago_2=segundo,
    )
    bd.add(chancuco)
    bd.commit()
    bd.refresh(chancuco)
    return chancuco


def actualizar_chancuco(
    bd: Session,
    id_usuario: str,
    id_chancuco: str,
    descripcion: str,
    numero_referencia: str,
    valor_pago: Decimal | str | int | float | None = None,
    url_pago: str | None = None,
    favorito: bool = False,
    dia_pago_1: int | str | None = None,
    dia_pago_2: int | str | None = None,
) -> Chancuco | None:
    """Actualiza todos los datos editables de un atajo propio.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del atajo.
        id_chancuco: Identificador del atajo a modificar.
        descripcion: Texto que identifica el atajo.
        numero_referencia: Número que se copia al portapapeles.
        valor_pago: Monto exacto a pagar; vacío si no tiene monto fijo.
        url_pago: Pasarela oficial; vacía si no aplica.
        favorito: Estado del favorito.
        dia_pago_1: Día del mes del pago (1–31), si se conoce.
        dia_pago_2: Segundo día del mes para un pago doble, si aplica.

    Returns:
        El atajo actualizado, o `None` si no existe o es de otro usuario.

    Raises:
        ValueError: Si faltan datos obligatorios, la URL es inválida, el valor
            es negativo o alguno de los días no está entre 1 y 31.
    """
    chancuco = bd.get(Chancuco, id_chancuco)
    if chancuco is None or chancuco.id_usuario != id_usuario:
        return None

    descripcion_limpia = descripcion.strip()
    referencia_limpia = numero_referencia.strip()
    if not descripcion_limpia:
        raise ValueError("La descripción del atajo es obligatoria.")
    if not referencia_limpia:
        raise ValueError("El número de referencia es obligatorio.")

    primero, segundo = _normalizar_dias(dia_pago_1, dia_pago_2)
    valor = None
    if valor_pago is not None and str(valor_pago).strip():
        valor = redondear_dinero(parsear_monto(str(valor_pago)))
        if valor < 0:
            raise ValueError("El valor a pagar no puede ser negativo.")

    chancuco.descripcion = descripcion_limpia[:120]
    chancuco.numero_referencia = referencia_limpia[:60]
    chancuco.valor_pago = valor
    chancuco.url_pago = _validar_url(url_pago)
    chancuco.dia_pago_1 = primero
    chancuco.dia_pago_2 = segundo
    chancuco.favorito = favorito
    bd.commit()
    bd.refresh(chancuco)
    return chancuco


def listar_chancucos(bd: Session, id_usuario: str) -> list[Chancuco]:
    """Lista los atajos del usuario, primero los favoritos.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los atajos.

    Returns:
        Lista ordenada por favorito y descripción.
    """
    consulta = (
        select(Chancuco)
        .where(Chancuco.id_usuario == id_usuario)
        .order_by(Chancuco.favorito.desc(), Chancuco.descripcion)
    )
    return list(bd.scalars(consulta))


def alternar_favorito(bd: Session, id_usuario: str, id_chancuco: str) -> Chancuco | None:
    """Cambia el estado de favorito de una referencia.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la referencia.
        id_chancuco: Referencia a modificar.

    Returns:
        La referencia actualizada o `None` si no existe o es de otro usuario.
    """
    chancuco = bd.get(Chancuco, id_chancuco)
    if chancuco is None or chancuco.id_usuario != id_usuario:
        return None
    chancuco.favorito = not chancuco.favorito
    bd.commit()
    bd.refresh(chancuco)
    return chancuco


def eliminar_chancuco(bd: Session, id_usuario: str, id_chancuco: str) -> bool:
    """Elimina una referencia de pago.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la referencia.
        id_chancuco: Referencia a eliminar.

    Returns:
        `True` si se eliminó; `False` si no existía o era de otro usuario.
    """
    chancuco = bd.get(Chancuco, id_chancuco)
    if chancuco is None or chancuco.id_usuario != id_usuario:
        return False
    bd.delete(chancuco)
    bd.commit()
    return True
