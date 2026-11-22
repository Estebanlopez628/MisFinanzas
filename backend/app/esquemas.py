"""Esquemas Pydantic de las entradas de gastos, deducciones y deudas.

Responsabilidad
---------------
- Aportar una capa declarativa de validación a los formularios FastAPI, que
  hoy se validan a mano en los servicios.
- Garantizar que la categoría capturada pertenezca al catálogo cerrado de ocho
  opciones, usando la misma fuente de verdad que la dona. Si se elige
  «Créditos y Obligaciones», se exige una deuda vinculada (sección 3.2).
- Validar el plan de pagos de una deuda con una tasa implícita **simulada**: se
  admite que `cuota × cuotas` supere el capital y se rechaza solo lo que no lo
  cubre, con el mensaje único de la sección 2.2. La tasa nunca se guarda ni se
  muestra: los pagos reales siguen abonando capital.

Los formularios siguen enviándose como `Form`; los routers construyen estos
esquemas con `validar_formulario` y traducen los errores al mensaje que ya
esperan las plantillas. Así no se rompe el respaldo sin JavaScript.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.core import categorias as catalogo
from app.servicios import deudas as servicio_deudas
from app.servicios import feedback as servicio_feedback

Modelo = TypeVar("Modelo", bound=BaseModel)


def _categoria_cerrada(valor: str) -> str:
    """Valida una categoría del catálogo cerrado, incluida la número 8.

    SRS v1.9, sección 3.2: el usuario puede elegir «Créditos y Obligaciones»;
    al hacerlo debe vincular una deuda registrada. Esa coherencia se comprueba
    en cada esquema con `model_validator`.

    Args:
        valor: Categoría recibida del formulario.

    Returns:
        Nombre canónico del catálogo.

    Raises:
        ValueError: Si la categoría no pertenece al catálogo cerrado.
    """
    return catalogo.normalizar_categoria(valor, estricto=True)


def _exigir_deuda_si_es_credito(categoria: str | None, id_deuda: str | None) -> None:
    """Exige un vínculo cuando la categoría es «Créditos y Obligaciones».

    Args:
        categoria: Categoría ya normalizada.
        id_deuda: Deuda elegida en el formulario.

    Raises:
        ValueError: Si se eligió crédito sin seleccionar una deuda.
    """
    if categoria == catalogo.CATEGORIA_CREDITOS and not (id_deuda or "").strip():
        raise ValueError(
            "Debes registrar tu deuda en el módulo Registro y Detalles de deudas "
            "para poder guardar este registro"
        )


class _FormularioBase(BaseModel):
    """Opciones comunes a todos los formularios validados.

    Attributes:
        model_config: Recorta espacios e ignora campos que no pertenezcan al
            esquema, para no rechazar formularios con campos heredados.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class GastoNuevo(_FormularioBase):
    """Datos válidos para crear un gasto fijo o variable.

    Attributes:
        categoria: Una de las siete categorías capturables del catálogo.
        descripcion: Detalle legible del gasto.
        valor: Monto en pesos, con o sin separadores de miles.
        fecha: Fecha ISO; vacía significa hoy.
        es_fijo: ``1`` si el gasto se repite cada mes.
        quincena: ``1``, ``2`` o vacío para mes completo.
        id_deuda: Deuda registrada que este gasto paga; vacío si no aplica.
        origen: Panel que envió el formulario, para la redirección.
    """

    categoria: str
    descripcion: str
    valor: str = ""
    fecha: str = ""
    es_fijo: str = ""
    quincena: str = ""
    id_deuda: str = ""
    origen: str = ""

    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, valor: str) -> str:
        """Aplica el catálogo cerrado a la categoría del gasto.

        Args:
            valor: Categoría recibida del formulario.

        Returns:
            Nombre canónico permitido.
        """
        return _categoria_cerrada(valor)

    @field_validator("descripcion")
    @classmethod
    def _descripcion_requerida(cls, valor: str) -> str:
        """Exige una descripción no vacía.

        Args:
            valor: Texto recibido.

        Returns:
            Descripción recortada.

        Raises:
            ValueError: Si el usuario dejó el campo vacío.
        """
        if not valor:
            raise ValueError("La descripción del gasto es obligatoria.")
        return valor

    @model_validator(mode="after")
    def _credito_requiere_deuda(self) -> "GastoNuevo":
        """Exige una deuda vinculada si la categoría es crédito.

        Returns:
            El esquema validado.

        Raises:
            ValueError: Si se eligió «Créditos y Obligaciones» sin deuda.
        """
        _exigir_deuda_si_es_credito(self.categoria, self.id_deuda)
        return self


class GastoEditar(_FormularioBase):
    """Datos válidos para corregir un gasto existente.

    Attributes:
        descripcion: Nuevo detalle legible.
        valor: Nuevo monto en pesos.
        categoria: Nueva categoría cerrada; vacía conserva la anterior.
        quincena: Nueva quincena; vacía devuelve el gasto al mes completo.
        id_deuda: Deuda vinculada; vacía quita el vínculo.
        origen: Panel que envió el formulario.
    """

    descripcion: str
    valor: str = ""
    categoria: str = ""
    quincena: str = ""
    id_deuda: str = ""
    origen: str = ""

    @field_validator("categoria")
    @classmethod
    def _categoria_opcional(cls, valor: str) -> str:
        """Valida la categoría solo cuando el formulario la envió.

        Args:
            valor: Categoría recibida; cadena vacía significa «sin cambios».

        Returns:
            Categoría canónica, o cadena vacía.
        """
        return _categoria_cerrada(valor) if valor else ""

    @field_validator("descripcion")
    @classmethod
    def _descripcion_requerida(cls, valor: str) -> str:
        """Exige una descripción no vacía.

        Args:
            valor: Texto recibido.

        Returns:
            Descripción recortada.

        Raises:
            ValueError: Si el usuario dejó el campo vacío.
        """
        if not valor:
            raise ValueError("La descripción del gasto es obligatoria.")
        return valor

    @model_validator(mode="after")
    def _credito_requiere_deuda(self) -> "GastoEditar":
        """Exige una deuda vinculada si la categoría editada es crédito.

        Returns:
            El esquema validado.

        Raises:
            ValueError: Si se eligió «Créditos y Obligaciones» sin deuda.
        """
        _exigir_deuda_si_es_credito(self.categoria, self.id_deuda)
        return self


class DeduccionNueva(_FormularioBase):
    """Datos válidos para crear una deducción fija del salario.

    Attributes:
        descripcion: Concepto del descuento.
        valor: Monto por pago; se ignora si hay deuda vinculada.
        quincena: `1` o `2`.
        categoria: Categoría cerrada; por defecto «Otros Gastos Fijos».
        id_deuda: Deuda mensual que paga la deducción; vacío si no aplica.
    """

    descripcion: str
    valor: str = ""
    quincena: str = "1"
    categoria: str | None = catalogo.CATEGORIA_OTROS
    id_deuda: str = ""

    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, valor: str | None) -> str | None:
        """Aplica el catálogo cerrado a la categoría de la deducción.

        Args:
            valor: Categoría recibida del formulario; vacía se infiere del
                concepto en el servicio.

        Returns:
            Nombre canónico permitido, o `None` si no se envió.
        """
        return _categoria_cerrada(valor) if valor else None

    @field_validator("descripcion")
    @classmethod
    def _descripcion_requerida(cls, valor: str) -> str:
        """Exige un concepto no vacío.

        Args:
            valor: Texto recibido.

        Returns:
            Descripción recortada.

        Raises:
            ValueError: Si el usuario dejó el campo vacío.
        """
        if not valor:
            raise ValueError("La descripción de la deducción es obligatoria.")
        return valor

    @model_validator(mode="after")
    def _credito_requiere_deuda(self) -> "DeduccionNueva":
        """Exige una deuda vinculada si la categoría es crédito.

        Returns:
            El esquema validado.

        Raises:
            ValueError: Si se eligió «Créditos y Obligaciones» sin deuda.
        """
        _exigir_deuda_si_es_credito(self.categoria, self.id_deuda)
        return self


class DeduccionEditar(DeduccionNueva):
    """Datos válidos para corregir una deducción fija.

    La estructura es idéntica a `DeduccionNueva`: todos los campos se vuelven
    a enviar en el formulario de edición.
    """


class DeudaNueva(_FormularioBase):
    """Datos válidos para registrar una deuda.

    Attributes:
        acreedor: Entidad o persona acreedora.
        descripcion: Detalle opcional.
        saldo_total: Capital adeudado.
        cuota: Valor de cada pago.
        cuotas_pendientes: Número de pagos restantes.
        periodicidad: `MENSUAL` o `QUINCENAL`.
        tasa_implicita: Tasa mensual simulada por validación, nunca persistida.
    """

    acreedor: str
    descripcion: str = ""
    saldo_total: str = ""
    cuota: str = ""
    cuotas_pendientes: str = ""
    periodicidad: str = servicio_deudas.PERIODICIDAD_MENSUAL
    # Se valida también el valor por defecto para que la tasa se derive siempre
    # que el formulario no la envíe (que es lo habitual).
    tasa_implicita: Decimal | None = Field(default=None, validate_default=True)

    @field_validator("acreedor")
    @classmethod
    def _acreedor_requerido(cls, valor: str) -> str:
        """Exige un acreedor no vacío.

        Args:
            valor: Texto recibido.

        Returns:
            Acreedor recortado.

        Raises:
            ValueError: Si el usuario dejó el campo vacío.
        """
        if not valor:
            raise ValueError("El acreedor es obligatorio.")
        return valor

    @field_validator("periodicidad")
    @classmethod
    def _periodicidad_valida(cls, valor: str) -> str:
        """Acepta solo las dos periodicidades del modelo.

        Args:
            valor: Texto recibido del selector.

        Returns:
            Periodicidad en mayúsculas.

        Raises:
            ValueError: Si la periodicidad no es `MENSUAL` ni `QUINCENAL`.
        """
        normal = valor.strip().upper()
        if normal not in servicio_deudas.PERIODICIDADES:
            raise ValueError("La periodicidad debe ser QUINCENAL o MENSUAL.")
        return normal

    @field_validator("tasa_implicita", mode="before")
    @classmethod
    def _simular_tasa(cls, _valor: object, info) -> Decimal:
        """Deriva la tasa implícita del plan usando los demás campos.

        Es una validación sin efecto contable: admite el excedente como interés
        implícito y solo rechaza el plan que no cubre el capital. La tasa no se
        persiste ni se muestra en ninguna pantalla.

        Args:
            _valor: Valor recibido para el campo; se ignora siempre.
            info: Contexto del validador con los datos ya normalizados.

        Returns:
            Tasa mensual simulada con diez decimales.

        Raises:
            ValueError: Si el plan de pagos no es válido.
        """
        datos = info.data
        return servicio_deudas.tasa_implicita_simulada(
            datos.get("saldo_total", ""),
            datos.get("cuota", ""),
            datos.get("cuotas_pendientes", ""),
        )


class DeudaEditar(DeudaNueva):
    """Datos válidos para corregir una deuda existente.

    Hereda la validación de `DeudaNueva` (incluida la tasa simulada) y exige que
    el saldo, la cuota y las cuotas se envíen explícitamente: en una edición no
    hay valores previos que completar en el servidor.
    """

    saldo_total: str = Field(min_length=1)
    cuota: str = Field(min_length=1)
    cuotas_pendientes: str = Field(min_length=1)


class FeedbackNuevo(_FormularioBase):
    """Datos válidos para enviar un reporte desde «Ayuda y comentarios».

    Attributes:
        tipo_reporte: Clave del catálogo cerrado de tipos de reporte.
        modulo: Módulo público implicado; vacío se normaliza a «Otro».
        descripcion: Texto libre del reporte.
        dispositivo: Se acepta pero se ignora: el servidor lo detecta del
            ``User-Agent`` para que no pueda falsearse desde el navegador.
    """

    tipo_reporte: str
    modulo: str = "Otro"
    descripcion: str
    dispositivo: str = "Escritorio"  # Se ignora; se detecta del User-Agent.

    @field_validator("tipo_reporte")
    @classmethod
    def _tipo_valido(cls, valor: str) -> str:
        """Acepta solo los tipos de reporte de la SRS.

        Args:
            valor: Clave recibida del selector.

        Returns:
            Clave normalizada en mayúsculas.

        Raises:
            ValueError: Si la clave no pertenece al catálogo.
        """
        clave = valor.strip().upper()
        if clave not in {tipo for tipo, _ in servicio_feedback.TIPOS_REPORTE}:
            raise ValueError("Selecciona un tipo de reporte válido.")
        return clave

    @field_validator("modulo")
    @classmethod
    def _modulo_valido(cls, valor: str) -> str:
        """Acepta solo módulos públicos, nunca OLB_BYTE ni facturación.

        Args:
            valor: Texto recibido del selector; vacío significa «Otro».

        Returns:
            Módulo canónico del catálogo.

        Raises:
            ValueError: Si el módulo no está permitido para el usuario estándar.
        """
        modulo = valor.strip() or "Otro"
        if modulo not in servicio_feedback.MODULOS:
            raise ValueError("Selecciona un módulo válido.")
        return modulo

    @field_validator("descripcion")
    @classmethod
    def _descripcion_requerida(cls, valor: str) -> str:
        """Exige un texto mínimo y acota el tamaño del reporte.

        Args:
            valor: Texto recibido.

        Returns:
            Descripción recortada.

        Raises:
            ValueError: Si está vacía o supera los 2000 caracteres.
        """
        texto = valor.strip()
        if not texto:
            raise ValueError("Escribe una descripción para enviar el reporte.")
        if len(texto) > 2000:
            raise ValueError("La descripción no puede superar los 2000 caracteres.")
        return texto


def validar_formulario(modelo: type[Modelo], **datos: object) -> Modelo:
    """Construye un esquema a partir de un formulario y unifica sus errores.

    Args:
        modelo: Clase Pydantic que valida los datos.
        **datos: Campos enviados por el formulario.

    Returns:
        Instancia validada del esquema.

    Raises:
        ValueError: Con un mensaje legible cuando la validación falla; los
            routers ya saben convertirlo en HTML 400 o en una redirección.
    """
    try:
        return modelo(**datos)
    except ValidationError as error:
        partes: list[str] = []
        for fallo in error.errors():
            mensaje = re.sub(
                r"^Value error,\s*", "", str(fallo.get("msg", "")), flags=re.IGNORECASE
            ).strip()
            campo = ".".join(str(parte) for parte in fallo.get("loc", ()))
            # SRS v3.9.3: la tasa simulada es un detalle técnico; el usuario
            # solo debe ver el mensaje de negocio, sin nombre de campo ni
            # prefijos de Pydantic.
            partes.append(mensaje if campo == "tasa_implicita" else f"{campo}: {mensaje}")
        raise ValueError("; ".join(partes)) from error
