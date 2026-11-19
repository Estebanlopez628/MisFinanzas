"""Transfiere los datos de la base SQLite local a PostgreSQL (Neon) sin duplicarlos.

Responsabilidad
---------------
- Crear en el destino el esquema completo desde los modelos (`create_all`).
- Copiar tabla por tabla, en orden de claves foráneas, solo las columnas que existen
  en el origen. Las filas que ya estén en el destino se omiten (`ON CONFLICT DO
  NOTHING`), así que correrlo dos veces no duplica registros.
- Ajustar las secuencias de las claves numéricas para que las inserciones futuras
  no choquen con los ids copiados.
- Neutralizar las cuentas demo copiadas: conservan sus filas (y sus datos ligados),
  pero reciben una contraseña aleatoria. Así no quedan accesos con contraseñas
  conocidas en la base de producción.

Todo ocurre en una sola transacción: si algo falla, no queda una copia a medias.

Uso (desde `backend/`, con `DATABASE_URL` apuntando a Neon en `backend/.env`):
    .venv\\Scripts\\python scripts\\migrar_a_neon.py
    .venv\\Scripts\\python scripts\\migrar_a_neon.py --origen datos\\finanzas.db
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

RUTA_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RUTA_BACKEND))

from sqlalchemy import Integer, create_engine, func, inspect, select, text, update  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as insertar_postgres  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402
from sqlalchemy.schema import Table  # noqa: E402

import app.modelos  # noqa: E402,F401  (registra las tablas en Base.metadata)
from app.core.base_datos import Base, URL_BASE_DATOS, motor  # noqa: E402
from app.core.seguridad import hash_contrasena  # noqa: E402
from app.modelos import Usuario  # noqa: E402
from app.servicios.usuarios import CUENTAS_DEMO  # noqa: E402

TAMANO_LOTE = 500


def _lotes(filas: list[dict], tamano: int) -> list[list[dict]]:
    """Divide las filas en lotes para no enviar una sentencia demasiado grande.

    Args:
        filas: Filas a insertar.
        tamano: Número máximo de filas por lote.

    Returns:
        Lista de lotes.
    """
    return [filas[inicio : inicio + tamano] for inicio in range(0, len(filas), tamano)]


def copiar_tabla(origen: Connection, destino: Connection, tabla: Table) -> int:
    """Copia las filas de una tabla que aún no existan en el destino.

    Args:
        origen: Conexión a la base SQLite local.
        destino: Conexión a PostgreSQL.
        tabla: Tabla definida en los modelos.

    Returns:
        Número de filas nuevas insertadas en el destino.
    """
    if not inspect(origen).has_table(tabla.name):
        return 0

    columnas_origen = {columna["name"] for columna in inspect(origen).get_columns(tabla.name)}
    comunes = [columna for columna in tabla.columns if columna.name in columnas_origen]
    if not comunes:
        return 0

    filas = [dict(fila) for fila in origen.execute(select(*comunes)).mappings().all()]
    if not filas:
        return 0

    antes = destino.execute(select(func.count()).select_from(tabla)).scalar_one()
    for lote in _lotes(filas, TAMANO_LOTE):
        destino.execute(insertar_postgres(tabla).on_conflict_do_nothing(), lote)
    despues = destino.execute(select(func.count()).select_from(tabla)).scalar_one()
    return despues - antes


def ajustar_secuencias(destino: Connection, tabla: Table) -> None:
    """Alinea la secuencia de cada clave numérica con el máximo copiado.

    Sin este ajuste, PostgreSQL reutilizaría ids ya ocupados al insertar.

    Args:
        destino: Conexión a PostgreSQL.
        tabla: Tabla cuyas claves numéricas se ajustan.
    """
    for clave in tabla.primary_key.columns:
        if not isinstance(clave.type, Integer):
            continue
        destino.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{tabla.name}', '{clave.name}'), "
                f"COALESCE(MAX({clave.name}), 1), MAX({clave.name}) IS NOT NULL) FROM {tabla.name}"
            )
        )


def neutralizar_cuentas_demo(destino: Connection) -> int:
    """Asigna una contraseña aleatoria a las cuentas demo copiadas.

    Args:
        destino: Conexión a PostgreSQL.

    Returns:
        Número de cuentas demo neutralizadas.
    """
    neutralizadas = 0
    for correo, _contrasena, _alias, _rol in CUENTAS_DEMO:
        resultado = destino.execute(
            update(Usuario)
            .where(Usuario.correo == correo)
            .values(hash_contrasena=hash_contrasena(secrets.token_urlsafe(32)))
        )
        neutralizadas += resultado.rowcount or 0
    return neutralizadas


def main() -> None:
    """Ejecuta la migración desde la línea de comandos.

    Raises:
        SystemExit: Si el origen no existe o el destino no es PostgreSQL.
    """
    analizador = argparse.ArgumentParser(description="Copia la base SQLite local a Neon.")
    analizador.add_argument(
        "--origen",
        type=Path,
        default=RUTA_BACKEND / "datos" / "finanzas.db",
        help="Archivo SQLite de origen.",
    )
    argumentos = analizador.parse_args()

    if not URL_BASE_DATOS.startswith("postgresql"):
        raise SystemExit("El destino debe ser PostgreSQL: revisa DATABASE_URL en backend/.env.")
    if not argumentos.origen.exists():
        raise SystemExit(f"No existe el origen: {argumentos.origen}")

    origen_motor = create_engine(f"sqlite:///{argumentos.origen.resolve().as_posix()}")
    Base.metadata.create_all(motor)

    print(f"Origen: {argumentos.origen}")
    with origen_motor.connect() as origen, motor.begin() as destino:
        for tabla in Base.metadata.sorted_tables:
            nuevas = copiar_tabla(origen, destino, tabla)
            ajustar_secuencias(destino, tabla)
            print(f"  {tabla.name}: {nuevas} filas nuevas")
        neutralizadas = neutralizar_cuentas_demo(destino)
    origen_motor.dispose()

    print(f"Cuentas demo neutralizadas: {neutralizadas}")
    print("Migración terminada. Puedes volver a ejecutarla sin duplicar datos.")


if __name__ == "__main__":
    main()
