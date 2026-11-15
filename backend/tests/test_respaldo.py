"""Pruebas del script de respaldo de SQLite (bloque D).

Cubren la resolución de la ruta de origen, la copia consistente con la API
`backup`, la verificación de integridad, la rotación por antigüedad y los
códigos de salida de la interfaz de línea de comandos.

El módulo se carga con `importlib` porque `scripts/` no es un paquete de la
aplicación y no se importa desde `app`.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

from app.core.base_datos import FabricaSesiones
from app.servicios import usuarios

RUTA_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "respaldo.py"


def _cargar_script():
    """Carga `scripts/respaldo.py` como módulo aislado.

    Returns:
        El módulo con las funciones de respaldo listas para invocar.
    """
    especificacion = importlib.util.spec_from_file_location(
        "respaldo_pruebas", RUTA_SCRIPT
    )
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


respaldo = _cargar_script()


@pytest.fixture()
def origen(tmp_path: Path) -> Path:
    """Crea una base SQLite con datos reconocibles.

    Args:
        tmp_path: Carpeta temporal entregada por pytest.

    Returns:
        Ruta del archivo de origen.
    """
    archivo = tmp_path / "origen.db"
    with closing(sqlite3.connect(archivo)) as conexion:
        conexion.execute("CREATE TABLE ejemplo (id INTEGER PRIMARY KEY, nombre TEXT)")
        conexion.execute("INSERT INTO ejemplo (nombre) VALUES ('OLB_BYTE')")
        conexion.commit()
    return archivo


def test_crear_respaldo_copia_datos_y_crea_destino(
    origen: Path, tmp_path: Path
) -> None:
    """La copia conserva las filas y crea la carpeta de destino si no existe."""
    destino = tmp_path / "respaldos" / "anidado"

    copia = respaldo.crear_respaldo(origen, destino)

    assert copia.is_file()
    assert copia.parent == destino
    assert copia.name.startswith(respaldo.PREFIJO)
    assert respaldo.verificar_respaldo(copia) is True

    with closing(sqlite3.connect(copia)) as conexion:
        filas = conexion.execute("SELECT nombre FROM ejemplo").fetchall()
    assert filas == [("OLB_BYTE",)]


def test_crear_respaldo_de_la_base_de_la_aplicacion(tmp_path: Path) -> None:
    """El respaldo de la base real de pruebas abre y conserva las cuentas."""
    with FabricaSesiones() as bd:
        # Una consulta ORM obliga a abrir el archivo que usa la aplicación.
        usuarios.listar_usuarios(bd)

    copia = respaldo.crear_respaldo(respaldo.ruta_origen(), tmp_path)

    assert respaldo.verificar_respaldo(copia) is True
    with closing(sqlite3.connect(copia)) as conexion:
        correos = {
            fila[0]
            for fila in conexion.execute("SELECT correo FROM usuarios").fetchall()
        }
    assert "admin@olbbyte.co" in correos


def test_crear_respaldo_sin_origen_falla(tmp_path: Path) -> None:
    """Un origen inexistente se informa con `FileNotFoundError`."""
    with pytest.raises(FileNotFoundError):
        respaldo.crear_respaldo(tmp_path / "no-existe.db", tmp_path / "respaldos")


def test_dos_respaldos_seguidos_no_se_sobrescriben(origen: Path, tmp_path: Path) -> None:
    """La marca temporal incluye microsegundos y genera nombres únicos."""
    primero = respaldo.crear_respaldo(origen, tmp_path)
    segundo = respaldo.crear_respaldo(origen, tmp_path)

    assert primero != segundo
    assert primero.is_file() and segundo.is_file()
    assert len(list(tmp_path.glob(f"{respaldo.PREFIJO}*.db"))) == 2


def test_verificar_respaldo_detecta_archivo_invalido(tmp_path: Path) -> None:
    """Un archivo que no es SQLite se reporta como inválido, sin excepción."""
    falso = tmp_path / "falso.db"
    falso.write_bytes(b"esto no es una base de datos")

    assert respaldo.verificar_respaldo(falso) is False


def test_rotar_respaldos_conserva_los_mas_recientes(tmp_path: Path) -> None:
    """Se eliminan los nombres más antiguos y sobreviven los últimos."""
    nombres = [
        "finanzas_20260101_000000_000000.db",
        "finanzas_20260102_000000_000000.db",
        "finanzas_20260103_000000_000000.db",
        "finanzas_20260104_000000_000000.db",
    ]
    for nombre in nombres:
        (tmp_path / nombre).write_bytes(b"")

    eliminados = respaldo.rotar_respaldos(tmp_path, conservar=2)

    restantes = sorted(ruta.name for ruta in tmp_path.glob(f"{respaldo.PREFIJO}*.db"))
    assert restantes == nombres[-2:]
    assert sorted(ruta.name for ruta in eliminados) == nombres[:2]


def test_rotar_respaldos_exige_conservar_al_menos_uno(tmp_path: Path) -> None:
    """Un valor de rotación inválido se rechaza con `ValueError`."""
    with pytest.raises(ValueError):
        respaldo.rotar_respaldos(tmp_path, conservar=0)


def test_ruta_origen_lee_database_url(monkeypatch, tmp_path: Path) -> None:
    """`DATABASE_URL` de SQLite se traduce a la ruta absoluta del archivo."""
    archivo = tmp_path / "produccion.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{archivo.as_posix()}")

    assert respaldo.ruta_origen() == archivo.resolve()


def test_ruta_origen_rechaza_otros_motores(monkeypatch) -> None:
    """PostgreSQL requiere `pg_dump`, no este script."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/olb")

    with pytest.raises(SystemExit) as salida:
        respaldo.ruta_origen()

    assert salida.value.code == 2


def test_main_crea_respaldo_y_devuelve_cero(
    monkeypatch, origen: Path, tmp_path: Path
) -> None:
    """La CLI respalda la base indicada por entorno y termina con éxito."""
    destino = tmp_path / "salida"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{origen.as_posix()}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["respaldo.py", "--destino", str(destino), "--conservar", "2"],
    )

    assert respaldo.main() == 0
    assert len(list(destino.glob(f"{respaldo.PREFIJO}*.db"))) == 1


def test_main_informa_origen_inexistente(monkeypatch, tmp_path: Path) -> None:
    """Sin archivo de base de datos la CLI devuelve el código 2."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'no.db').as_posix()}")
    monkeypatch.setattr(sys, "argv", ["respaldo.py", "--destino", str(tmp_path)])

    assert respaldo.main() == 2


def test_main_informa_respaldo_corrupto(monkeypatch, origen: Path, tmp_path: Path) -> None:
    """Si la verificación falla, la CLI devuelve el código 1."""
    falso = tmp_path / "corrupto.db"
    falso.write_bytes("contenido inválido".encode("utf-8"))

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{origen.as_posix()}")
    monkeypatch.setattr(
        sys, "argv", ["respaldo.py", "--destino", str(tmp_path / "salida")]
    )
    monkeypatch.setattr(respaldo, "crear_respaldo", lambda *_argumentos: falso)

    assert respaldo.main() == 1
