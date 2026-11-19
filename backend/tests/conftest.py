"""Configuración compartida de pytest.

Responsabilidad
---------------
- Aislar la base de datos de pruebas en un archivo temporal **antes** de que se
  importe la aplicación (la URL se lee al construir el motor).
- Entregar clientes HTTP autenticados con los roles `ADMIN_OLB` y
  `USER_FINANZAS`.
- Limpiar los datos transaccionales entre pruebas para que cada caso parta de
  un estado conocido, conservando las cuentas de demostración.

Las pruebas ejercitan el camino real de autenticación: el token se emite con la
misma función que usa la aplicación y la cookie se valida contra la base de
datos.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# La URL de la base de datos debe fijarse antes de importar `app.main`, porque
# `core/base_datos.py` crea el motor al cargarse.
# ---------------------------------------------------------------------------
RUTA_PRUEBAS = Path(tempfile.gettempdir()) / "olb_finanzas_pruebas"
RUTA_PRUEBAS.mkdir(parents=True, exist_ok=True)
ARCHIVO_BD = RUTA_PRUEBAS / f"pruebas_{os.getpid()}.db"
if ARCHIVO_BD.exists():
    ARCHIVO_BD.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{ARCHIVO_BD.as_posix()}"
os.environ["ENTORNO"] = "pruebas"
os.environ["CLAVE_SECRETA"] = "clave-secreta-solo-para-pruebas-0123456789"
os.environ["PUBLICIDAD_ACTIVA"] = "1"
os.environ.setdefault("CORREOS_OLB_BYTE", "admin@olbbyte.co,oscar.esteban.lopez.bedoya@gmail.com,oscaresteban.lopez93@gmail.com")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.base_datos import FabricaSesiones, inicializar_base_datos
from app.core.seguridad import crear_token
from app.dependencias import NOMBRE_COOKIE
from app.main import crear_aplicacion
from app.modelos import (
    Abono,
    AbonoProyeccion,
    Auditoria,
    Chancuco,
    Cliente,
    DeduccionFija,
    Deuda,
    DevolucionCliente,
    Gasto,
    GarantiaProveedor,
    Incapacidad,
    MovimientoProveedor,
    PagoDeuda,
    PerfilFinanciero,
    PeriodoNomina,
    Producto,
    ProyeccionAhorro,
    RegistroHorasExtra,
    SaldoIncapacidad,
    TrabajoExtra,
    Venta,
    VentaDetalle,
)
from app.servicios import perfiles, usuarios

CORREO_ADMIN = "admin@olbbyte.co"
CORREO_USUARIO = "usuario@finanzas.co"

# Se inicializa una vez por sesión de pytest; `crear_aplicacion` también lo hace
# de forma idempotente, pero adelantarlo permite preparar las cuentas demo.
inicializar_base_datos()


# El orden respeta las claves foráneas: primero los detalles y las tablas que
# referencian a periodos o ventas.
MODELOS_TRANSACCIONALES = (
    AbonoProyeccion,
    ProyeccionAhorro,
    DeduccionFija,
    RegistroHorasExtra,
    SaldoIncapacidad,
    Gasto,
    PeriodoNomina,
    Incapacidad,
    GarantiaProveedor,
    DevolucionCliente,
    MovimientoProveedor,
    Abono,
    VentaDetalle,
    Venta,
    Producto,
    Cliente,
    PagoDeuda,
    Deuda,
    Chancuco,
    TrabajoExtra,
    PerfilFinanciero,
    Auditoria,
)


@pytest.fixture(autouse=True)
def limpiar_datos_transaccionales() -> None:
    """Borra los datos de negocio antes de cada prueba.

    Las cuentas de `usuarios` se conservan porque son la base del login; los
    registros creados por una prueba no deben contaminar a la siguiente. Después
    de limpiar se siembra un perfil financiero para las cuentas demo: así las
    pruebas de módulos no chocan con el onboarding obligatorio, que se ejercita
    aparte eliminando el perfil de forma explícita.
    """
    with FabricaSesiones() as bd:
        for modelo in MODELOS_TRANSACCIONALES:
            bd.execute(delete(modelo))
        bd.commit()

        for correo in (CORREO_ADMIN, CORREO_USUARIO):
            cuenta = usuarios.buscar_por_correo(bd, correo)
            if cuenta is not None:
                perfiles.guardar_perfil(
                    bd,
                    cuenta.id_usuario,
                    "2.960.000",
                    perfiles.MODALIDAD_QUINCENAL,
                    "50",
                    "50",
                    perfiles.QUINCENA_PRIMERA,
                )
    yield


def _cliente_con_sesion(correo: str) -> TestClient:
    """Crea un cliente con la cookie de sesión de un usuario sembrado.

    Args:
        correo: Correo de una cuenta existente en la base de datos.

    Returns:
        Cliente HTTP autenticado.

    Raises:
        AssertionError: Si la cuenta no existe (indica un fallo en las semillas).
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, correo)
        assert cuenta is not None, f"No existe la cuenta de prueba {correo}"
        id_usuario, rol, alias = cuenta.id_usuario, cuenta.rol, cuenta.alias

    cliente = TestClient(crear_aplicacion())
    cliente.cookies.set(NOMBRE_COOKIE, crear_token(id_usuario, rol, alias))
    return cliente


@pytest.fixture()
def cliente() -> TestClient:
    """Cliente sin sesión (visitante anónimo).

    Returns:
        Cliente HTTP sin cookie de sesión.
    """
    return TestClient(crear_aplicacion())


@pytest.fixture()
def cliente_admin() -> TestClient:
    """Cliente autenticado con rol `ADMIN_OLB`.

    Returns:
        Cliente HTTP con sesión de administrador.
    """
    return _cliente_con_sesion(CORREO_ADMIN)


@pytest.fixture()
def cliente_usuario() -> TestClient:
    """Cliente autenticado con rol `USER_FINANZAS`.

    Returns:
        Cliente HTTP con sesión de usuario público.
    """
    return _cliente_con_sesion(CORREO_USUARIO)


@pytest.fixture()
def bd():
    """Sesión de base de datos para pruebas de servicios.

    Yields:
        Sesión de SQLAlchemy; se cierra al terminar la prueba.
    """
    with FabricaSesiones() as sesion:
        yield sesion
