"""Conexión a PostgreSQL (Neon) y salud de la base: las pruebas nunca tocan Neon."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.base_datos import URL_BASE_DATOS, _url_con_driver, obtener_bd
from app.main import crear_aplicacion


def test_url_de_neon_usa_el_driver_psycopg() -> None:
    """La cadena `postgresql://` de Neon se convierte al driver psycopg 3."""
    entrada = "postgresql://dueno:clave@host.neon.tech/finanzasdb?sslmode=require"

    assert _url_con_driver(entrada) == "postgresql+psycopg://dueno:clave@host.neon.tech/finanzasdb?sslmode=require"
    assert _url_con_driver("sqlite:///x.db") == "sqlite:///x.db"


def test_las_pruebas_usan_sqlite_temporal() -> None:
    """Las pruebas corren sobre SQLite temporal, aunque `backend/.env` apunte a Neon."""
    assert URL_BASE_DATOS.startswith("sqlite")


def test_salud_responde_200_consultando_la_base() -> None:
    """`/salud` confirma que la base contesta."""
    respuesta = TestClient(crear_aplicacion()).get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.json()["base_datos"] == "ok"


def test_salud_responde_503_si_la_base_no_contesta() -> None:
    """Si la base falla, `/salud` responde 503 para que el proveedor no envíe tráfico."""
    aplicacion = crear_aplicacion()

    class SesionRota:
        """Sustituto de sesión que simula una base caída."""

        def execute(self, *_args, **_kwargs):
            """Lanza el error de conexión de SQLAlchemy.

            Raises:
                OperationalError: Siempre, para simular la caída.
            """
            raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

    def sesion_rota() -> Iterator[SesionRota]:
        """Entrega la sesión rota a la ruta de salud.

        Yields:
            Sesión que falla al consultar.
        """
        yield SesionRota()

    aplicacion.dependency_overrides[obtener_bd] = sesion_rota
    respuesta = TestClient(aplicacion).get("/salud")

    assert respuesta.status_code == 503
    assert respuesta.json()["base_datos"] == "no disponible"
