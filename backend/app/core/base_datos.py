"""Conexión a la base de datos y sesión por petición.

Responsabilidad
---------------
- Crear el motor SQLAlchemy y la fábrica de sesiones.
- Declarar la clase base de los modelos.
- Entregar una sesión por petición HTTP (`obtener_bd`) y cerrarla al terminar.
- Inicializar el esquema y las cuentas de demostración al arrancar.

Decisión (ADR-09): **SQLite** para desarrollo y pruebas con `create_all`. La URL
se toma de `DATABASE_URL`, de modo que migrar a PostgreSQL solo requiere cambiar
esa variable y añadir Alembic antes del despliegue.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

RUTA_BACKEND = Path(__file__).resolve().parent.parent.parent
RUTA_DATOS = RUTA_BACKEND / "datos"
RUTA_DATOS.mkdir(exist_ok=True)

# `sqlite:///...` apunta a un archivo local; en pruebas se redefine la variable.
URL_BASE_DATOS = os.getenv(
    "DATABASE_URL", f"sqlite:///{(RUTA_DATOS / 'finanzas.db').as_posix()}"
)

_conexion_sqlite = URL_BASE_DATOS.startswith("sqlite")

motor = create_engine(
    URL_BASE_DATOS,
    # FastAPI atiende peticiones en varios hilos; SQLite necesita este ajuste.
    connect_args={"check_same_thread": False} if _conexion_sqlite else {},
    pool_pre_ping=True,
)


if _conexion_sqlite:

    @event.listens_for(motor, "connect")
    def _activar_claves_foraneas(conexion, _registro) -> None:
        """Activa la verificación de claves foráneas en SQLite.

        SQLite las ignora por defecto; activarlas evita registros huérfanos.

        Args:
            conexion: Conexión DBAPI recién abierta.
            _registro: Metadatos de SQLAlchemy (no se usa).
        """
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


FabricaSesiones = sessionmaker(
    bind=motor,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Clase base declarativa de todos los modelos del proyecto."""


def obtener_bd() -> Iterator[Session]:
    """Dependencia de FastAPI que entrega una sesión y la cierra al terminar.

    Yields:
        Sesión de SQLAlchemy ligada al motor configurado.
    """
    sesion = FabricaSesiones()
    try:
        yield sesion
    finally:
        sesion.close()


def crear_esquema() -> None:
    """Crea las tablas que falten según los modelos declarados.

    Es idempotente: puede llamarse en cada arranque sin borrar datos. En la fase
    de PostgreSQL se sustituirá por migraciones de Alembic.
    """
    from app import modelos  # Importación tardía para registrar los modelos.

    Base.metadata.create_all(motor)
    _migrar_columnas_perfil()
    _migrar_columnas_gastos()


# Columnas agregadas después de la primera versión de `perfiles_financieros`.
# `create_all` no altera tablas existentes, así que en SQLite se añaden aquí de
# forma idempotente. En PostgreSQL/Alembic esta lista se sustituirá por una
# migración versionada.
_COLUMNAS_PERFIL_NUEVAS = {
    "porcentaje_quincena_1": "NUMERIC(5, 2)",
    "porcentaje_quincena_2": "NUMERIC(5, 2)",
    "quincena_deducciones": "SMALLINT",
}


def _migrar_columnas_perfil() -> None:
    """Agrega las columnas quincenales a una base SQLite ya existente.

    La primera versión guardaba un único `porcentaje_quincenal`. Para no perder
    los perfiles creados, se copia ese valor a la quincena 1 y se calcula la
    quincena 2 como el complemento a 100 %. El servicio valida los rangos; las
    restricciones `CHECK` solo existen en bases creadas desde cero.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql(
            "PRAGMA table_info(perfiles_financieros)"
        ).fetchall()
        existentes = {fila[1] for fila in filas}
        if not existentes:
            return

        for columna, tipo in _COLUMNAS_PERFIL_NUEVAS.items():
            if columna not in existentes:
                conexion.exec_driver_sql(
                    f"ALTER TABLE perfiles_financieros ADD COLUMN {columna} {tipo}"
                )

        if "porcentaje_quincenal" in existentes:
            conexion.exec_driver_sql(
                "UPDATE perfiles_financieros "
                "SET porcentaje_quincena_1 = porcentaje_quincenal, "
                "    porcentaje_quincena_2 = 100 - porcentaje_quincenal, "
                "    quincena_deducciones = 1 "
                "WHERE porcentaje_quincena_1 IS NULL "
                "  AND porcentaje_quincenal IS NOT NULL "
                "  AND modalidad_pago = 'QUINCENAL'"
            )


def _migrar_columnas_gastos() -> None:
    """Agrega `quincena` a una tabla `gastos` ya existente.

    Los gastos creados antes del SRS v1.2 no tienen quincena asignada; se dejan
    en `NULL` (mes completo) para no inventar una imputación. El resumen de
    quincenas los cuenta en la primera quincena y los señala como gastos del mes.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql("PRAGMA table_info(gastos)").fetchall()
        existentes = {fila[1] for fila in filas}
        if existentes and "quincena" not in existentes:
            conexion.exec_driver_sql(
                "ALTER TABLE gastos ADD COLUMN quincena SMALLINT"
            )


def _migrar_chancucos() -> None:
    """Reconstruye `chancucos` al esquema de atajos de pago (SRS v1.3).

    El SRS v1.3 redujo el atajo de pago a tres datos: descripción, número de
    referencia y enlace. La versión anterior guardaba `entidad` y
    `tipo_servicio`, ambas `NOT NULL`, de modo que un simple `RENAME COLUMN`
    dejaría `tipo_servicio` sin valor y rompería cada `INSERT` posterior.

    Por eso se reconstruye la tabla: se crea el esquema nuevo, se copian las
    filas fusionando `entidad · tipo_servicio` en `descripcion` para no perder
    texto, y se reemplaza la tabla original conservando su índice.

    Es idempotente: si la columna `descripcion` ya existe (o la tabla aún no se
    ha creado), no hace nada.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql("PRAGMA table_info(chancucos)").fetchall()
        existentes = {fila[1] for fila in filas}
        if not existentes or "descripcion" in existentes:
            return

        conexion.exec_driver_sql(
            """
            CREATE TABLE chancucos_v13 (
                id_chancuco VARCHAR(32) NOT NULL PRIMARY KEY,
                id_usuario VARCHAR(32) NOT NULL
                    REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
                descripcion VARCHAR(120) NOT NULL,
                numero_referencia VARCHAR(60) NOT NULL,
                url_pago VARCHAR(300),
                favorito BOOLEAN NOT NULL DEFAULT 0,
                fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # `entidad` y `tipo_servicio` se fusionan: «EPM · Energía» es más útil
        # que una descripción vacía, y el usuario puede editarla después.
        conexion.exec_driver_sql(
            """
            INSERT INTO chancucos_v13 (
                id_chancuco, id_usuario, descripcion, numero_referencia,
                url_pago, favorito, fecha_creacion
            )
            SELECT
                id_chancuco,
                id_usuario,
                TRIM(
                    COALESCE(entidad, '') ||
                    CASE WHEN COALESCE(tipo_servicio, '') <> ''
                         THEN ' · ' || tipo_servicio
                         ELSE '' END
                ),
                numero_referencia,
                url_pago,
                COALESCE(favorito, 0),
                COALESCE(fecha_creacion, CURRENT_TIMESTAMP)
            FROM chancucos
            """
        )

        conexion.exec_driver_sql("DROP TABLE chancucos")
        conexion.exec_driver_sql("ALTER TABLE chancucos_v13 RENAME TO chancucos")
        conexion.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chancucos_id_usuario "
            "ON chancucos (id_usuario)"
        )


def inicializar_base_datos() -> None:
    """Prepara el esquema y siembra las cuentas de demostración.

    Se ejecuta al construir la aplicación. La siembra es condicional (solo si no
    hay usuarios), por lo que reiniciar el servidor no duplica cuentas.
    """
    from app.servicios import usuarios

    crear_esquema()
    # La migración de atajos corre después de crear el esquema: si la tabla no
    # existía, ya se creó con la estructura nueva y la función no hace nada.
    _migrar_chancucos()
    with FabricaSesiones() as sesion:
        usuarios.sembrar_demostracion(sesion)
