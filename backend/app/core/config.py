"""Parámetros de negocio y configuración de la plataforma.

Responsabilidad
---------------
Centralizar todos los valores que provienen de la normativa laboral colombiana
y de la configuración de la aplicación, de modo que el motor de nómina, las
vistas y las pruebas consuman la **misma fuente de verdad**.

Los parámetros pueden sobreescribirse por variables de entorno (útil para
despliegues y pruebas), pero sus valores por defecto corresponden a la
parametrización vigente documentada en `MEMORY.md`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache

# ---------------------------------------------------------------------------
# Factores de recargos y horas extras (normativa colombiana)
# Las claves coinciden con los valores del enum `tipo_hora` del diccionario de
# datos, lo que permite persistir el registro sin traducciones adicionales.
# ---------------------------------------------------------------------------
# SRS v4.8: tabla oficial vigente en Colombia para 2026 (7 conceptos).
# El recargo dominical/festivo diurno deja de duplicar la hora base (antes 1.90)
# y se separa del nocturno dominical/festivo, que es un concepto nuevo.
FACTORES_RECARGO: dict[str, Decimal] = {
    "EXTRA_DIURNA_NORMAL": Decimal("1.25"),
    "EXTRA_NOCTURNA": Decimal("1.75"),
    "EXTRA_DIURNA_DOMINICAL_FESTIVA": Decimal("2.15"),
    "EXTRA_NOCTURNA_DOMINICAL_FESTIVA": Decimal("2.65"),
    "RECARGO_NOCTURNO": Decimal("0.35"),
    "RECARGO_DOMINICAL_FESTIVO": Decimal("0.90"),
    "RECARGO_NOCTURNO_DOMINICAL_FESTIVO": Decimal("1.25"),
}

# Etiquetas legibles para la interfaz. Se mantienen separadas de los factores
# para que un cambio de copy no afecte el cálculo financiero.
ETIQUETAS_TIPO_HORA: dict[str, str] = {
    "EXTRA_DIURNA_NORMAL": "Hora extra diurna normal",
    "EXTRA_NOCTURNA": "Hora extra nocturna",
    "EXTRA_DIURNA_DOMINICAL_FESTIVA": "Hora extra diurna dominical/festiva",
    "EXTRA_NOCTURNA_DOMINICAL_FESTIVA": "Hora extra nocturna dominical/festiva",
    "RECARGO_NOCTURNO": "Recargo nocturno ordinario",
    "RECARGO_DOMINICAL_FESTIVO": "Recargo ordinario dominical/festivo",
    "RECARGO_NOCTURNO_DOMINICAL_FESTIVO": "Recargo nocturno dominical/festivo",
}


def _decimal_desde_entorno(nombre: str, predeterminado: Decimal) -> Decimal:
    """Lee una variable de entorno numérica y la convierte a `Decimal`.

    Se usa `Decimal` (y no `float`) porque el proyecto maneja dinero: evita
    errores de redondeo binario en los cálculos salariales.

    Args:
        nombre: Nombre de la variable de entorno, por ejemplo ``SMMLV``.
        predeterminado: Valor a usar si la variable no existe o está vacía.

    Returns:
        El valor configurado o el predeterminado, siempre como `Decimal`.
    """
    crudo = os.getenv(nombre, "").strip()
    if not crudo:
        return predeterminado
    return Decimal(crudo)


@dataclass(frozen=True)
class ParametrosNomina:
    """Parámetros legales y de cálculo del motor de nómina.

    Es inmutable (`frozen=True`) para evitar mutaciones accidentales a mitad de
    una liquidación; cualquier cambio debe hacerse por configuración.

    Attributes:
        horas_mensuales: Base legal mensual de 220 horas para 2026 (Ley 2101),
            sobreescribible con `HORAS_MENSUALES`.
        porcentaje_salud: Aporte obligatorio de salud del empleado (4%).
        porcentaje_pension: Aporte obligatorio de pensión del empleado (4%).
        smmlv: Salario Mínimo Legal Mensual Vigente usado para el tope del auxilio.
        valor_auxilio_transporte: Valor del auxilio cuando el trabajador tiene derecho.
        dias_incapacidad_empleador: Días iniciales pagados al 100% por el empleador.
        porcentaje_pago_desde_dia_tres: Porcentaje reconocido por la EPS del día 3 en adelante.
    """

    horas_mensuales: Decimal = Decimal("220")
    porcentaje_salud: Decimal = Decimal("0.04")
    porcentaje_pension: Decimal = Decimal("0.04")
    smmlv: Decimal = Decimal("1750905.00")
    valor_auxilio_transporte: Decimal = Decimal("249095.00")
    dias_incapacidad_empleador: int = 2
    porcentaje_pago_desde_dia_tres: Decimal = Decimal("66.67")

    @property
    def tope_auxilio_transporte(self) -> Decimal:
        """Calcula el tope legal de 2 SMMLV para conservar el auxilio.

        Regla de negocio: si `sueldo básico + recargos` supera este tope, el
        auxilio de transporte se anula ($0) automáticamente.

        Returns:
            El valor de 2 SMMLV en pesos colombianos.
        """
        return self.smmlv * Decimal("2")

    @property
    def porcentaje_descuento_incapacidad(self) -> Decimal:
        """Descuento aplicable al trabajador desde el día 3 de incapacidad.

        Se deriva del porcentaje de pago de la EPS (66.67%), por lo que el
        descuento es del 33.33%.

        Returns:
            Porcentaje (0–100) que asume el trabajador.
        """
        return Decimal("100") - self.porcentaje_pago_desde_dia_tres


# Correos autorizados a OLB_BYTE (SRS v1.8). Se pueden cambiar con la variable
# CORREOS_OLB_BYTE, separados por coma.
CORREOS_OLB_BYTE_PREDETERMINADOS = (
    "oscar.esteban.lopez.bedoya@gmail.com",
    "oscaresteban.lopez93@gmail.com",
)


def _lista_desde_entorno(nombre: str, predeterminada: tuple[str, ...]) -> list[str]:
    """Lee una lista separada por comas desde el entorno.

    Args:
        nombre: Variable de entorno.
        predeterminada: Valores si la variable no existe o está vacía.

    Returns:
        Lista de textos sin espacios ni mayúsculas.
    """
    valor = os.getenv(nombre, "").strip()
    elementos = valor.split(",") if valor else list(predeterminada)
    return [elemento.strip().lower() for elemento in elementos if elemento.strip()]


@dataclass(frozen=True)
class ConfiguracionApp:
    """Metadatos generales de la aplicación web.

    Attributes:
        nombre: Nombre visible en documentación OpenAPI.
        version: Versión funcional (coincide con el hito del plan).
        entorno: Entorno de ejecución (`desarrollo`, `pruebas`, `produccion`).
        clave_secreta: Clave para firmar sesiones (Fase 1); en producción debe
            venir siempre de una variable de entorno.
    """

    nombre: str = "Finanzas y OLB_BYTE"
    version: str = "1.0.0"
    # Se leen al construir la instancia (y no al importar el módulo) para que un
    # proceso que define el entorno antes de arrancar obtenga los valores
    # correctos, y para que las pruebas puedan aislarlos con `monkeypatch`.
    entorno: str = field(default_factory=lambda: os.getenv("ENTORNO", "desarrollo"))
    clave_secreta: str = field(
        default_factory=lambda: os.getenv("CLAVE_SECRETA", "cambiar-en-produccion")
    )

    correos_olb_byte: frozenset[str] = field(
        default_factory=lambda: frozenset(
            _lista_desde_entorno("CORREOS_OLB_BYTE", CORREOS_OLB_BYTE_PREDETERMINADOS)
        )
    )
    # Cuentas que pasan a ADMIN_OLB al entrar con Google (correo verificado).
    correos_admin_olb: frozenset[str] = field(
        default_factory=lambda: frozenset(
            _lista_desde_entorno("CORREOS_ADMIN_OLB", CORREOS_OLB_BYTE_PREDETERMINADOS)
        )
    )
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "").strip())
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587") or "587"))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", "").strip())
    # Se aceptan los alias `SMTP_PASSWORD` y `FROM_EMAIL` de algunos proveedores;
    # las variables canónicas del proyecto siguen mandando.
    smtp_pass: str = field(
        default_factory=lambda: os.getenv("SMTP_PASS") or os.getenv("SMTP_PASSWORD", "")
    )
    smtp_from: str = field(
        default_factory=lambda: (os.getenv("SMTP_FROM") or os.getenv("FROM_EMAIL", "")).strip()
    )
    # SRS v3.1, punto 3: APIs transaccionales por HTTPS (puerto 443, sin bloqueo
    # de firewall en Render). Se prueban en este orden antes que SMTP.
    resend_api_key: str = field(default_factory=lambda: os.getenv("RESEND_API_KEY", "").strip())
    brevo_api_key: str = field(default_factory=lambda: os.getenv("BREVO_API_KEY", "").strip())
    sendgrid_api_key: str = field(default_factory=lambda: os.getenv("SENDGRID_API_KEY", "").strip())
    app_url: str = field(default_factory=lambda: os.getenv("APP_URL", "").strip())
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", "").strip())
    google_client_secret: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    )
    google_redirect_uri: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/login/google/callback"
        ).strip()
    )

    @property
    def es_produccion(self) -> bool:
        """Indica si la aplicación corre en entorno productivo.

        Returns:
            `True` cuando ``ENTORNO=produccion``.
        """
        return self.entorno.strip().lower() == "produccion"

    @property
    def cookie_segura(self) -> bool:
        """Indica si la cookie de sesión debe marcarse como `Secure`.

        En producción se fuerza HTTPS; en desarrollo puede activarse con
        ``COOKIE_SEGURA=1`` para probar el despliegue.

        Returns:
            `True` si la cookie solo debe viajar por HTTPS.
        """
        valor = os.getenv("COOKIE_SEGURA", "").strip().lower()
        return self.es_produccion or valor in {"1", "true", "si", "sí"}

    @property
    def publicidad_activa(self) -> bool:
        """Indica si se muestra el espacio publicitario al rol público.

        Returns:
            `True` salvo que ``PUBLICIDAD_ACTIVA=0``.
        """
        return os.getenv("PUBLICIDAD_ACTIVA", "1").strip().lower() not in {"0", "false", "no"}

    @property
    def publicidad_texto(self) -> str:
        """Texto o llamada a la acción del espacio publicitario.

        Returns:
            El texto configurado en ``PUBLICIDAD_TEXTO`` o el mensaje por
            defecto que recuerda que la herramienta seguirá siendo gratuita.
        """
        return os.getenv(
            "PUBLICIDAD_TEXTO",
            "Espacio reservado para anuncios no invasivos. La herramienta seguirá siendo gratuita.",
        )

    @property
    def publicidad_url(self) -> str | None:
        """Enlace opcional del anuncio.

        Returns:
            La URL configurada en ``PUBLICIDAD_URL`` o `None` si no existe.
        """
        valor = os.getenv("PUBLICIDAD_URL", "").strip()
        return valor or None

    @property
    def limite_intentos_login(self) -> int:
        """Número de intentos fallidos permitidos antes de bloquear el login.

        Returns:
            El valor de ``LIMITE_INTENTOS_LOGIN`` (5 por defecto).
        """
        try:
            return max(1, int(os.getenv("LIMITE_INTENTOS_LOGIN", "5")))
        except ValueError:
            return 5

    @property
    def documentacion_habilitada(self) -> bool:
        """Indica si `/docs` debe exponerse.

        Returns:
            `False` en producción, para no publicar el esquema de la API.
        """
        return not self.es_produccion

    def validar_para_produccion(self) -> None:
        """Comprueba que la configuración sea segura antes de arrancar.

        Raises:
            RuntimeError: Si el entorno es producción y la clave secreta sigue
                siendo la de ejemplo, es demasiado corta o no se definió.
        """
        if not self.es_produccion:
            return
        clave = self.clave_secreta.strip()
        if clave in {"", "cambiar-en-produccion"} or len(clave) < 32:
            raise RuntimeError(
                "En producción debes definir CLAVE_SECRETA con al menos 32 caracteres."
            )


@lru_cache(maxsize=1)
def obtener_parametros() -> ParametrosNomina:
    """Devuelve los parámetros de nómina cacheados.

    Se cachea la instancia porque es inmutable y se consulta en cada petición
    que renderiza el tablero o (en la siguiente tarea) liquida un periodo.

    Returns:
        Instancia única de `ParametrosNomina`, ajustada por variables de entorno
        (`SMMLV`, `AUXILIO_TRANSPORTE`, `HORAS_MENSUALES`).
    """
    base = ParametrosNomina()
    return ParametrosNomina(
        horas_mensuales=_decimal_desde_entorno("HORAS_MENSUALES", base.horas_mensuales),
        porcentaje_salud=_decimal_desde_entorno("PORCENTAJE_SALUD", base.porcentaje_salud),
        porcentaje_pension=_decimal_desde_entorno("PORCENTAJE_PENSION", base.porcentaje_pension),
        smmlv=_decimal_desde_entorno("SMMLV", base.smmlv),
        valor_auxilio_transporte=_decimal_desde_entorno(
            "AUXILIO_TRANSPORTE", base.valor_auxilio_transporte
        ),
        dias_incapacidad_empleador=base.dias_incapacidad_empleador,
        porcentaje_pago_desde_dia_tres=_decimal_desde_entorno(
            "PORCENTAJE_PAGO_INCAPACIDAD", base.porcentaje_pago_desde_dia_tres
        ),
    )


@lru_cache(maxsize=1)
def obtener_configuracion() -> ConfiguracionApp:
    """Devuelve la configuración general de la aplicación.

    Returns:
        Instancia única de `ConfiguracionApp` construida desde el entorno.
    """
    return ConfiguracionApp()
