"""Limitador de intentos para proteger el inicio de sesión.

Responsabilidad
---------------
Evitar ataques de fuerza bruta manteniendo en memoria una ventana deslizante de
intentos fallidos por combinación de IP y correo. Es deliberadamente simple: al
reiniciar el proceso se limpia, y en un despliegue con varias instancias debe
sustituirse por un almacén compartido (Redis), tal como se anota en
`MEMORY.md`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _RegistroIntentos:
    """Intentos fallidos de una clave dentro de la ventana.

    Attributes:
        marcas: Instantes (segundos) de cada fallo.
    """

    marcas: list[float] = field(default_factory=list)


class LimitadorIntentos:
    """Ventana deslizante de intentos fallidos.

    Attributes:
        maximo: Fallos permitidos dentro de la ventana.
        ventana_segundos: Duración de la ventana.
    """

    def __init__(self, maximo: int = 5, ventana_segundos: int = 600) -> None:
        """Inicializa el limitador.

        Args:
            maximo: Número de fallos permitidos antes de bloquear.
            ventana_segundos: Tiempo durante el cual se cuentan los fallos.
        """
        self.maximo = maximo
        self.ventana_segundos = ventana_segundos
        self._registros: dict[str, _RegistroIntentos] = {}

    def _depurar(self, registro: _RegistroIntentos, ahora: float) -> None:
        """Elimina las marcas que ya salieron de la ventana.

        Args:
            registro: Registro a depurar.
            ahora: Instante actual en segundos.
        """
        limite = ahora - self.ventana_segundos
        registro.marcas = [marca for marca in registro.marcas if marca >= limite]

    def permitir(self, clave: str, ahora: float | None = None) -> bool:
        """Indica si la clave puede intentar autenticarse.

        Args:
            clave: Identificador del intento (IP + correo).
            ahora: Instante de referencia, útil en pruebas.

        Returns:
            `True` si aún no alcanzó el máximo de fallos.
        """
        instante = time.time() if ahora is None else ahora
        registro = self._registros.get(clave)
        if registro is None:
            return True
        self._depurar(registro, instante)
        return len(registro.marcas) < self.maximo

    def registrar_fallo(self, clave: str, ahora: float | None = None) -> None:
        """Anota un fallo de autenticación.

        Args:
            clave: Identificador del intento.
            ahora: Instante de referencia, útil en pruebas.
        """
        instante = time.time() if ahora is None else ahora
        registro = self._registros.setdefault(clave, _RegistroIntentos())
        self._depurar(registro, instante)
        registro.marcas.append(instante)

    def limpiar(self, clave: str) -> None:
        """Reinicia el contador de una clave tras un acceso correcto.

        Args:
            clave: Identificador del intento.
        """
        self._registros.pop(clave, None)

    def reiniciar(self) -> None:
        """Elimina todos los registros de intentos.

        Se usa en pruebas y en tareas de mantenimiento: al reiniciar el proceso
        la ventana se pierde de todos modos, pero aquí se puede forzar sin
        reiniciar el servidor.
        """
        self._registros.clear()

    def segundos_restantes(self, clave: str, ahora: float | None = None) -> int:
        """Calcula cuánto falta para que la clave vuelva a estar disponible.

        Args:
            clave: Identificador del intento.
            ahora: Instante de referencia.

        Returns:
            Segundos restantes de bloqueo; 0 si no está bloqueada.
        """
        instante = time.time() if ahora is None else ahora
        registro = self._registros.get(clave)
        if registro is None:
            return 0
        self._depurar(registro, instante)
        if len(registro.marcas) < self.maximo:
            return 0
        return max(0, int(registro.marcas[0] + self.ventana_segundos - instante) + 1)


# Instancia compartida por la aplicación. Las pruebas pueden crear una propia.
# El máximo se toma de la configuración para que ``LIMITE_INTENTOS_LOGIN`` tenga
# efecto sin tocar el código.
from app.core.config import obtener_configuracion

limitador_login = LimitadorIntentos(maximo=obtener_configuracion().limite_intentos_login)
