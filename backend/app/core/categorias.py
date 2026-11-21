"""Catálogo cerrado de categorías de egresos y colores de la dona.

Responsabilidad
---------------
- Definir las **ocho** categorías permitidas, con sus nombres exactos y sus
  colores hexadecimales, como única fuente de verdad para backend y frontend.
- Normalizar el texto heredado (categorías de texto libre) a un nombre canónico
  sin romper los registros ya guardados.
- Reconocer las descripciones de crédito/libranza que, por compatibilidad con
  ADR-56, se contabilizan en «Créditos y Obligaciones».

Reglas de negocio
-----------------
- Las categorías 1 a 7 agrupan gastos fijos y deducciones del salario.
- La categoría 8 («Créditos y Obligaciones») se alimenta **automáticamente**
  con la cuota mensual de las deudas activas; el usuario no la elige a mano en
  un gasto o deducción, porque su valor se deriva del módulo de deudas.
- Un texto que no corresponde a ninguna categoría conocida se reclasifica como
  «Otros Gastos Fijos» cuando se normaliza en modo laxo (datos históricos), y
  se rechaza cuando la validación es estricta (formularios nuevos).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

PATRON_CREDITO = re.compile(r"\bcreditos?\b")


@dataclass(frozen=True)
class Categoria:
    """Categoría cerrada con su color para el gráfico de dona.

    Attributes:
        nombre: Nombre exacto que se persiste y se muestra en la interfaz.
        color: Color hexadecimal con el que se dibuja su arco.
    """

    nombre: str
    color: str


# Los ocho nombres y colores son innegociables: los consume la dona y los
# selectores cerrados de Mis Finanzas, Gastos y Presupuesto y Trabajos Extras.
CATEGORIAS: tuple[Categoria, ...] = (
    Categoria("Vivienda y Servicios", "#3B82F6"),
    Categoria("Alimentación y Mercado", "#10B981"),
    Categoria("Transporte y Movilidad", "#F59E0B"),
    Categoria("Salud y Bienestar", "#06B6D4"),
    Categoria("Telefonía y Suscripciones", "#8B5CF6"),
    Categoria("Educación y Familia", "#EC4899"),
    Categoria("Otros Gastos Fijos", "#64748B"),
    Categoria("Créditos y Obligaciones", "#EF4444"),
)

CATEGORIA_CREDITOS = "Créditos y Obligaciones"
CATEGORIA_OTROS = "Otros Gastos Fijos"
CATEGORIA_OTROS_COLOR = "#64748B"
# Categoría técnica de los pagos generados por «Trabajos Extras». No pertenece
# al catálogo cerrado de ocho y la migración de datos históricos debe respetarla:
# si se normalizara a «Otros Gastos Fijos», la idempotencia de los pagos dejaría
# de encontrarlos y crearían duplicados en cada arranque (ADR-60).
CATEGORIA_TRABAJO = "Trabajo extra"
NOMBRES_CATEGORIAS: frozenset[str] = frozenset(c.nombre for c in CATEGORIAS)

# Los textos libres históricos se traducen a su categoría canónica. «Ahorro» y
# «Ocio» caen en «Otros Gastos Fijos»: no son obligaciones de crédito.
_ALIASES: dict[str, str] = {
    "vivienda": CATEGORIAS[0].nombre,
    "hogar": CATEGORIAS[0].nombre,
    "arriendo": CATEGORIAS[0].nombre,
    "servicios": CATEGORIAS[0].nombre,
    "alimentacion": CATEGORIAS[1].nombre,
    "mercado": CATEGORIAS[1].nombre,
    "comida": CATEGORIAS[1].nombre,
    "supermercado": CATEGORIAS[1].nombre,
    "transporte": CATEGORIAS[2].nombre,
    "movilidad": CATEGORIAS[2].nombre,
    "gasolina": CATEGORIAS[2].nombre,
    "salud": CATEGORIAS[3].nombre,
    "bienestar": CATEGORIAS[3].nombre,
    "medicamentos": CATEGORIAS[3].nombre,
    "telefonia": CATEGORIAS[4].nombre,
    "suscripciones": CATEGORIAS[4].nombre,
    "internet": CATEGORIAS[4].nombre,
    "educacion": CATEGORIAS[5].nombre,
    "familia": CATEGORIAS[5].nombre,
    "estudio": CATEGORIAS[5].nombre,
    "otros": CATEGORIA_OTROS,
    "otro": CATEGORIA_OTROS,
    "ocio": CATEGORIA_OTROS,
    "ahorro": CATEGORIA_OTROS,
    "credito": CATEGORIA_CREDITOS,
    "creditos": CATEGORIA_CREDITOS,
    "libranza": CATEGORIA_CREDITOS,
    "deuda": CATEGORIA_CREDITOS,
}


def _clave(texto: str | None) -> str:
    """Normaliza un texto para compararlo sin tildes, mayúsculas ni espacios.

    Args:
        texto: Texto escrito por el usuario; puede ser `None` o estar vacío.

    Returns:
        Cadena en minúsculas, sin tildes ni espacios sobrantes.
    """
    normal = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(normal.lower().split())


def normalizar_categoria(texto: str | None, *, estricto: bool = False) -> str:
    """Convierte una categoría libre a uno de los ocho nombres canónicos.

    Args:
        texto: Categoría escrita en el formulario o guardada en la base.
        estricto: Si es `True`, un texto desconocido se rechaza; si es `False`,
            se reclasifica como «Otros Gastos Fijos».

    Returns:
        El nombre exacto de una de las ocho categorías del catálogo.

    Raises:
        ValueError: Si `estricto` es `True` y el texto no pertenece al catálogo.
    """
    clave = _clave(texto)
    for categoria in CATEGORIAS:
        if clave == _clave(categoria.nombre):
            return categoria.nombre
    if clave in _ALIASES:
        return _ALIASES[clave]
    if estricto:
        opciones = ", ".join(categoria.nombre for categoria in CATEGORIAS)
        raise ValueError(f"Selecciona una categoría válida: {opciones}.")
    return CATEGORIA_OTROS


def es_categoria_valida(texto: str | None) -> bool:
    """Indica si un texto pertenece al catálogo cerrado.

    Args:
        texto: Categoría a comprobar.

    Returns:
        `True` si coincide exactamente (ignorando tildes y mayúsculas) con una
        de las ocho categorías.
    """
    clave = _clave(texto)
    return any(clave == _clave(categoria.nombre) for categoria in CATEGORIAS)


def color_de_categoria(nombre: str) -> str:
    """Devuelve el color hexadecimal asignado a una categoría.

    Args:
        nombre: Nombre canónico de la categoría.

    Returns:
        Color hexadecimal exacto de la categoría; gris pizarra si el nombre no
        pertenece al catálogo.
    """
    canonico = normalizar_categoria(nombre)
    for categoria in CATEGORIAS:
        if categoria.nombre == canonico:
            return categoria.color
    return CATEGORIA_OTROS_COLOR


def es_credito(descripcion: str) -> bool:
    """Indica si una descripción habla de crédito o libranza.

    Se usa para clasificar las deducciones fijas heredadas que no están
    vinculadas a una deuda (ADR-56) dentro de «Créditos y Obligaciones».

    Args:
        descripcion: Concepto escrito por el usuario.

    Returns:
        `True` si contiene «crédito» o «créditos», sin importar tildes o
        mayúsculas.
    """
    return bool(PATRON_CREDITO.search(_clave(descripcion)))


def lista_categorias() -> list[dict[str, str]]:
    """Entrega el catálogo completo listo para la plantilla y el JavaScript.

    Returns:
        Lista de ocho diccionarios con `nombre` y `color`, en el orden oficial.
    """
    return [{"nombre": categoria.nombre, "color": categoria.color} for categoria in CATEGORIAS]
