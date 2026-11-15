"""Respaldo seguro de la base de datos SQLite.

Responsabilidad
---------------
Crear una copia consistente de la base de datos sin detener la aplicación y
rotar los respaldos antiguos.

Se usa la API `sqlite3.Connection.backup`, que copia páginas de forma atómica
aunque el servidor tenga conexiones abiertas (a diferencia de copiar el archivo
con el explorador de Windows, que puede dejar una copia a medio escribir).

Uso:
    cd backend
    .venv\\Scripts\\python scripts\\respaldo.py
    .venv\\Scripts\\python scripts\\respaldo.py --destino D:\\respaldos --conservar 30

La ruta de origen se toma de ``DATABASE_URL`` y, si no existe, del archivo por
defecto ``backend/datos/finanzas.db``.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

RUTA_BACKEND = Path(__file__).resolve().parent.parent
RUTA_DATOS = RUTA_BACKEND / "datos"
PREFIJO = "finanzas_"


def ruta_origen() -> Path:
    """Determina el archivo SQLite que se va a respaldar.

    Returns:
        Ruta absoluta del archivo de base de datos.

    Raises:
        SystemExit: Si ``DATABASE_URL`` apunta a un motor distinto de SQLite.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if url and not url.startswith("sqlite"):
        print(
            "Solo se admite SQLite por ahora. Para PostgreSQL usa pg_dump.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1)).expanduser().resolve()
    return (RUTA_DATOS / "finanzas.db").resolve()


def crear_respaldo(origen: Path, destino: Path) -> Path:
    """Copia la base de datos con la API de respaldo de SQLite.

    Args:
        origen: Archivo SQLite existente.
        destino: Directorio donde se guardará la copia.

    Returns:
        Ruta del archivo de respaldo creado.

    Raises:
        FileNotFoundError: Si el archivo de origen no existe.
    """
    if not origen.is_file():
        raise FileNotFoundError(f"No se encontró la base de datos: {origen}")

    destino.mkdir(parents=True, exist_ok=True)
    # Los microsegundos evitan sobrescribir una copia cuando dos respaldos se
    # ejecutan dentro del mismo segundo (por ejemplo, en una prueba o un cron
    # mal configurado).
    marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    archivo = destino / f"{PREFIJO}{marca}.db"

    # `backup` copia el contenido lógico, no los bytes: es seguro con WAL y con
    # la aplicación en ejecución. `closing` garantiza cerrar ambas conexiones
    # (en Windows un descriptor abierto impide mover o borrar el archivo).
    with closing(sqlite3.connect(origen)) as conexion_origen:
        with closing(sqlite3.connect(archivo)) as conexion_destino:
            conexion_origen.backup(conexion_destino)

    return archivo


def verificar_respaldo(archivo: Path) -> bool:
    """Comprueba la integridad del archivo recién creado.

    Args:
        archivo: Respaldo a validar.

    Returns:
        `True` si ``PRAGMA integrity_check`` devuelve ``ok`` y `False` si el
        archivo no es una base SQLite legible.
    """
    try:
        with closing(sqlite3.connect(archivo)) as conexion:
            resultado = conexion.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError:
        # Un archivo truncado o que no es SQLite hace fallar la consulta; se
        # trata como respaldo inválido en lugar de propagar la excepción para
        # que `main` pueda informar el problema con un código de salida.
        return False
    return bool(resultado) and resultado[0] == "ok"


def rotar_respaldos(destino: Path, conservar: int) -> list[Path]:
    """Elimina los respaldos más antiguos conservando los más recientes.

    Args:
        destino: Directorio de respaldos.
        conservar: Número de archivos que se mantienen.

    Returns:
        Lista de archivos eliminados (puede estar vacía).
    """
    if conservar < 1:
        raise ValueError("Debes conservar al menos un respaldo.")

    archivos = sorted(
        destino.glob(f"{PREFIJO}*.db"),
        # El nombre contiene la marca temporal con microsegundos, por lo que
        # ordenar por nombre equivale a ordenar por antigüedad y evita empates
        # de `mtime` en sistemas de archivos con resolución de un segundo.
        key=lambda ruta: ruta.name,
        reverse=True,
    )
    eliminados = []
    for archivo in archivos[conservar:]:
        archivo.unlink()
        eliminados.append(archivo)
    return eliminados


def main() -> int:
    """Ejecuta el respaldo y reporta el resultado.

    Returns:
        Código de salida del proceso: 0 si el respaldo es válido, 1 si la
        verificación de integridad falla.
    """
    analizador = argparse.ArgumentParser(description="Respalda la base SQLite.")
    analizador.add_argument(
        "--destino",
        type=Path,
        default=RUTA_BACKEND / "respaldos",
        help="Carpeta donde guardar la copia (por defecto backend/respaldos).",
    )
    analizador.add_argument(
        "--conservar",
        type=int,
        default=14,
        help="Cantidad de respaldos a mantener (por defecto 14).",
    )
    argumentos = analizador.parse_args()

    origen = ruta_origen()
    try:
        archivo = crear_respaldo(origen, argumentos.destino)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 2

    if not verificar_respaldo(archivo):
        print(f"El respaldo quedó corrupto: {archivo}", file=sys.stderr)
        return 1

    eliminados = rotar_respaldos(argumentos.destino, argumentos.conservar)
    tamano_mb = archivo.stat().st_size / (1024 * 1024)
    print(f"Respaldo creado: {archivo} ({tamano_mb:.2f} MB)")
    print(f"Copia de origen: {origen}")
    if eliminados:
        print(f"Respaldos rotados: {len(eliminados)} archivo(s) antiguo(s).")
    return 0


if __name__ == "__main__":
    # `raise SystemExit` propaga el código a la tarea programada o al CI.
    raise SystemExit(main())
