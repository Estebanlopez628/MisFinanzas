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

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core import categorias as catalogo

RUTA_BACKEND = Path(__file__).resolve().parent.parent.parent
RUTA_DATOS = RUTA_BACKEND / "datos"
RUTA_DATOS.mkdir(exist_ok=True)

RUTA_ENV = RUTA_BACKEND / ".env"


def _cargar_archivo_entorno() -> None:
    """Carga `backend/.env` en el entorno sin sobrescribir variables ya definidas.

    Así Render o las pruebas mandan siempre sobre el archivo local. El
    archivo no se versiona (`.gitignore`). No requiere dependencias externas.
    """
    if not RUTA_ENV.exists():
        return
    for linea in RUTA_ENV.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_archivo_entorno()


def _url_con_driver(url: str) -> str:
    """Indica a SQLAlchemy el driver `psycopg` (v3) para las URL `postgresql://`.

    Neon entrega la cadena sin driver; sin este cambio SQLAlchemy buscaría
    `psycopg2`, que el proyecto no usa.

    Args:
        url: URL de conexión tal como llega de la variable de entorno.

    Returns:
        La misma URL con `postgresql+psycopg://` cuando corresponde.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


# `sqlite:///...` apunta a un archivo local; en pruebas se redefine la variable.
URL_BASE_DATOS = _url_con_driver(
    os.getenv("DATABASE_URL", f"sqlite:///{(RUTA_DATOS / 'finanzas.db').as_posix()}")
)

_conexion_sqlite = URL_BASE_DATOS.startswith("sqlite")
_conexion_postgres = URL_BASE_DATOS.startswith("postgresql")

_opciones_motor: dict[str, object] = {"pool_pre_ping": True}
if _conexion_sqlite:
    # FastAPI atiende peticiones en varios hilos; SQLite necesita este ajuste.
    _opciones_motor["connect_args"] = {"check_same_thread": False}
elif _conexion_postgres:
    # Neon usa PgBouncer en modo transacción, que no admite sentencias preparadas
    # del servidor: se desactivan. `pool_recycle` renueva conexiones antes de que
    # el proveedor las cierre por inactividad.
    _opciones_motor["connect_args"] = {"prepare_threshold": None}
    _opciones_motor["pool_recycle"] = 300

motor = create_engine(URL_BASE_DATOS, **_opciones_motor)


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

    _reconstruir_comercial_sin_stock()
    Base.metadata.create_all(motor)
    _renombrar_referencia_a_categoria()
    _migrar_columnas_perfil()
    _migrar_columnas_trabajos()
    _migrar_columnas_gastos()
    _migrar_columnas_metas()
    _migrar_columnas_chancucos()


def _renombrar_referencia_a_categoria() -> None:
    """Renombra `venta_detalle.referencia` a `categoria` en bases ya creadas.

    La columna pasó a llamarse categoría porque así se captura el producto en el
    formulario de venta. `RENAME COLUMN` conserva los datos. Es idempotente: si la
    columna ya se llama `categoria`, o la tabla todavía no existe, no hace nada.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        existentes = {
            fila[1]
            for fila in conexion.exec_driver_sql("PRAGMA table_info(venta_detalle)").fetchall()
        }
        if "referencia" in existentes and "categoria" not in existentes:
            conexion.exec_driver_sql(
                "ALTER TABLE venta_detalle RENAME COLUMN referencia TO categoria"
            )


def _reconstruir_comercial_sin_stock() -> None:
    """Reconstruye las tablas comerciales al esquema sin inventario (ADR-35).

    El esquema anterior tenía `productos.stock` y líneas de venta ligadas al
    catálogo. SQLite no puede quitar esas restricciones con `ALTER TABLE`, así que
    se eliminan las tablas comerciales y `create_all` las vuelve a crear.

    Solo se hace si se detecta el esquema anterior. Si alguna tabla tiene filas,
    se detiene con un error: el aplicativo es nuevo y no debe perderse dinero
    registrado por accidente. Es idempotente.

    Raises:
        RuntimeError: Si el esquema anterior tiene datos y no puede reconstruirse
            sin pérdida.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        columnas_productos = {
            fila[1] for fila in conexion.exec_driver_sql("PRAGMA table_info(productos)").fetchall()
        }
        columnas_ventas = {
            fila[1] for fila in conexion.exec_driver_sql("PRAGMA table_info(ventas)").fetchall()
        }
        es_anterior = "stock" in columnas_productos or (
            bool(columnas_ventas) and "numero_orden" not in columnas_ventas
        )
        if not es_anterior:
            return

        tablas = ("abonos", "venta_detalle", "ventas", "productos")
        for tabla in tablas:
            filas = conexion.exec_driver_sql(f"SELECT COUNT(*) FROM {tabla}").scalar()
            if filas:
                raise RuntimeError(
                    f"No se puede reconstruir OLB_BYTE: la tabla '{tabla}' tiene datos. "
                    "Respalde la base y migre manualmente antes de iniciar."
                )
        for tabla in tablas:
            conexion.exec_driver_sql(f"DROP TABLE IF EXISTS {tabla}")


def _migrar_columnas_trabajos() -> None:
    """Agrega las columnas de contrato a `trabajos_extras` (SRS v1.7, bloque E).

    Los trabajos anteriores eran ingresos sueltos: quedan como contrato
    `INDEFINIDO` de frecuencia `MENSUAL`, con `fecha_pago = fecha`, de modo que
    siguen visibles sin inventar pagos retroactivos. Es idempotente.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql(
            "PRAGMA table_info(trabajos_extras)"
        ).fetchall()
        existentes = {fila[1] for fila in filas}
        if not existentes:
            return
        nuevas = {
            "tipo_contrato": "VARCHAR(20) NOT NULL DEFAULT 'INDEFINIDO'",
            "frecuencia": "VARCHAR(12) NOT NULL DEFAULT 'MENSUAL'",
            "fecha_fin": "DATE",
            "fecha_pago": "DATE",
            "valor_quincena_1": "NUMERIC(14, 2)",
            "valor_quincena_2": "NUMERIC(14, 2)",
            "fecha_pago_quincena_2": "DATE",
        }
        for columna, tipo in nuevas.items():
            if columna not in existentes:
                conexion.exec_driver_sql(
                    f"ALTER TABLE trabajos_extras ADD COLUMN {columna} {tipo}"
                )
        # Los trabajos heredados eran ingresos sueltos, no contratos: se anclan a
        # su fecha como un contrato de término fijo de un solo mes. Así no se
        # inventa un ingreso recurrente de 12 meses al abrir el módulo.
        conexion.exec_driver_sql(
            "UPDATE trabajos_extras "
            "SET fecha_pago = fecha, tipo_contrato = 'TERMINO_FIJO', fecha_fin = fecha "
            "WHERE fecha_pago IS NULL"
        )


def _migrar_columnas_chancucos() -> None:
    """Agrega los días de pago mensuales a `chancucos` (SRS v1.7, bloque D).

    Los atajos existentes conservan sus datos y quedan sin día (`NULL`): sus
    tarjetas se muestran igual que antes, sin distintivo de fecha. Es
    idempotente: solo añade las columnas que falten.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql("PRAGMA table_info(chancucos)").fetchall()
        existentes = {fila[1] for fila in filas}
        if not existentes:
            return
        for columna in ("dia_pago_1", "dia_pago_2"):
            if columna not in existentes:
                conexion.exec_driver_sql(
                    f"ALTER TABLE chancucos ADD COLUMN {columna} SMALLINT"
                )


def _migrar_columnas_metas() -> None:
    """Agrega el historial de archivado a `proyecciones_ahorro` (SRS v1.6).

    Las metas existentes quedan activas (`activo` ya es verdadero por defecto) y
    sin fecha de archivado. Es idempotente.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql(
            "PRAGMA table_info(proyecciones_ahorro)"
        ).fetchall()
        existentes = {fila[1] for fila in filas}
        if not existentes:
            return
        nuevas = {
            "archivada_en": "DATE",
            "estado_final": "VARCHAR(20)",
            # SRS v1.7: modo de reparto con «Ambas quincenas». Las metas ya
            # creadas conservan el comportamiento histórico (dividir).
            "modo_ambas": "VARCHAR(12) NOT NULL DEFAULT 'DIVIDIR'",
        }
        for columna, tipo in nuevas.items():
            if columna not in existentes:
                conexion.exec_driver_sql(
                    f"ALTER TABLE proyecciones_ahorro ADD COLUMN {columna} {tipo}"
                )


# Columnas agregadas después de la primera versión de `perfiles_financieros`.
# `create_all` no altera tablas existentes, así que en SQLite se añaden aquí de
# forma idempotente. En PostgreSQL/Alembic esta lista se sustituirá por una
# migración versionada.
_COLUMNAS_PERFIL_NUEVAS = {
    "porcentaje_quincena_1": "NUMERIC(5, 2)",
    "porcentaje_quincena_2": "NUMERIC(5, 2)",
    "quincena_deducciones": "SMALLINT",
    "dia_quincena_1": "SMALLINT",
    "dia_quincena_2": "SMALLINT",
}

# SRS v1.9: los perfiles anteriores no tenían día de quincena. Se les asigna el
# 15 y el 30 que la app usaba hasta ahora, para que ninguna cifra cambie de golpe.
_COLUMNAS_DIA_QUINCENA = ("dia_quincena_1", "dia_quincena_2")


def _migrar_dias_quincena_postgres() -> None:
    """Agrega los días de quincena a una base PostgreSQL ya existente (Neon).

    `create_all` no altera tablas que ya existen y las migraciones de SQLite no
    corren en PostgreSQL. Por eso se usa `ADD COLUMN IF NOT EXISTS`, que es
    idempotente, y se rellenan los perfiles previos con 15 y 30.
    """
    with motor.begin() as conexion:
        for columna in _COLUMNAS_DIA_QUINCENA:
            conexion.exec_driver_sql(
                f"ALTER TABLE perfiles_financieros ADD COLUMN IF NOT EXISTS {columna} SMALLINT"
            )
        conexion.exec_driver_sql(
            "UPDATE perfiles_financieros SET dia_quincena_1 = 15 WHERE dia_quincena_1 IS NULL"
        )
        conexion.exec_driver_sql(
            "UPDATE perfiles_financieros SET dia_quincena_2 = 30 WHERE dia_quincena_2 IS NULL"
        )


def _migrar_columnas_perfil() -> None:
    """Agrega las columnas quincenales a una base SQLite ya existente.

    La primera versión guardaba un único `porcentaje_quincenal`. Para no perder
    los perfiles creados, se copia ese valor a la quincena 1 y se calcula la
    quincena 2 como el complemento a 100 %. El servicio valida los rangos; las
    restricciones `CHECK` solo existen en bases creadas desde cero.
    """
    if not _conexion_sqlite:
        _migrar_dias_quincena_postgres()
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

        conexion.exec_driver_sql(
            "UPDATE perfiles_financieros SET dia_quincena_1 = 15 WHERE dia_quincena_1 IS NULL"
        )
        conexion.exec_driver_sql(
            "UPDATE perfiles_financieros SET dia_quincena_2 = 30 WHERE dia_quincena_2 IS NULL"
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
        if not existentes:
            return
        # SRS v1.6: checks de pago y gastos generados por metas. Las columnas
        # booleanas llevan default para que SQLite acepte el `NOT NULL`.
        nuevas = {
            "id_proyeccion": "VARCHAR(32) REFERENCES proyecciones_ahorro (id_proyeccion) ON DELETE CASCADE",
            # SRS v1.7: pagos generados por un trabajo extra.
            "id_trabajo": "VARCHAR(32) REFERENCES trabajos_extras (id_trabajo) ON DELETE CASCADE",
            "pagado": "BOOLEAN NOT NULL DEFAULT 0",
            "pagado_en": "DATE",
            "monto_pagado": "NUMERIC(14,2)",
            "check_visible": "BOOLEAN NOT NULL DEFAULT 1",
            "inhabilitado_hasta": "DATE",
        }
        for columna, tipo in nuevas.items():
            if columna not in existentes:
                conexion.exec_driver_sql(f"ALTER TABLE gastos ADD COLUMN {columna} {tipo}")


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


def _migrar_columnas_deudas() -> None:
    """Agrega el plan de pagos a una tabla `deudas` ya existente (SRS v1.5).

    La versión anterior no tenía `cuotas_pendientes` ni `periodicidad`. SQLite no
    permite añadir columnas `NOT NULL` sin valor por defecto, así que se crean con
    default y se dejan las deudas heredadas sin cuotas pendientes (no se puede
    inferir su calendario). Es idempotente.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql("PRAGMA table_info(deudas)").fetchall()
        existentes = {fila[1] for fila in filas}
        if not existentes:
            return
        if "cuotas_pendientes" not in existentes:
            conexion.exec_driver_sql(
                "ALTER TABLE deudas ADD COLUMN cuotas_pendientes "
                "SMALLINT NOT NULL DEFAULT 0"
            )
        if "periodicidad" not in existentes:
            conexion.exec_driver_sql(
                "ALTER TABLE deudas ADD COLUMN periodicidad "
                "VARCHAR(12) NOT NULL DEFAULT 'MENSUAL'"
            )
        if "fecha_creacion" not in existentes:
            # SQLite no admite `DEFAULT CURRENT_TIMESTAMP` en `ALTER TABLE`, así
            # que se agrega nullable y se rellena con la fecha de la migración.
            conexion.exec_driver_sql(
                "ALTER TABLE deudas ADD COLUMN fecha_creacion DATETIME"
            )
            conexion.exec_driver_sql(
                "UPDATE deudas SET fecha_creacion = CURRENT_TIMESTAMP "
                "WHERE fecha_creacion IS NULL"
            )


def _migrar_proyeccion_quincena() -> None:
    """Permite `quincena = 3` («Ambas quincenas») en las metas de ahorro.

    SRS v1.5 agregó la tercera opción al planificador. La tabla original tenía
    `CHECK (quincena IN (1, 2))` y SQLite no altera restricciones existentes, así
    que hay que reconstruir `proyecciones_ahorro` junto con su tabla hija
    `abonos_proyeccion`: primero se crean las copias nuevas, se trasvasan las
    filas, se eliminan las antiguas (hija antes que padre, por la clave foránea
    en cascada) y se renombran.

    Es idempotente: si el DDL guardado ya admite la opción 3 —o si las tablas
    todavía no existen— no hace nada.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' "
            "AND name = 'proyecciones_ahorro'"
        ).fetchall()
        if not filas or not filas[0][0]:
            return
        ddl = filas[0][0]
        if "IN (1, 2, 3)" in ddl.replace("  ", " ") or "quincena" not in ddl:
            return

        conexion.exec_driver_sql(
            """
            CREATE TABLE proyecciones_ahorro_v15 (
                id_proyeccion VARCHAR(32) NOT NULL PRIMARY KEY,
                id_usuario VARCHAR(32) NOT NULL
                    REFERENCES usuarios (id_usuario) ON DELETE CASCADE,
                categoria VARCHAR(60) NOT NULL,
                descripcion VARCHAR(150) NOT NULL,
                valor_mensual NUMERIC(14, 2) NOT NULL,
                tipo_duracion VARCHAR(20) NOT NULL,
                meses SMALLINT,
                fecha_inicio DATE NOT NULL,
                quincena SMALLINT NOT NULL,
                modo_ambas VARCHAR(12) NOT NULL DEFAULT 'DIVIDIR',
                activo BOOLEAN NOT NULL DEFAULT 1,
                fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_proyeccion_valor CHECK (valor_mensual >= 0),
                CONSTRAINT ck_proyeccion_quincena CHECK (quincena IN (1, 2, 3)),
                CONSTRAINT ck_proyeccion_modo_ambas
                    CHECK (modo_ambas IN ('DIVIDIR', 'DUPLICAR')),
                CONSTRAINT ck_proyeccion_duracion
                    CHECK (tipo_duracion IN ('FIJO', 'LIMITADO'))
            )
            """
        )
        conexion.exec_driver_sql(
            """
            CREATE TABLE abonos_proyeccion_v15 (
                id_abono VARCHAR(32) NOT NULL PRIMARY KEY,
                id_proyeccion VARCHAR(32) NOT NULL
                    REFERENCES proyecciones_ahorro_v15 (id_proyeccion)
                    ON DELETE CASCADE,
                anio SMALLINT NOT NULL,
                mes SMALLINT NOT NULL,
                valor NUMERIC(14, 2) NOT NULL,
                fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_abono_proyeccion_mes
                    UNIQUE (id_proyeccion, anio, mes),
                CONSTRAINT ck_abono_proyeccion_valor CHECK (valor >= 0)
            )
            """
        )
        conexion.exec_driver_sql(
            """
            INSERT INTO proyecciones_ahorro_v15 (
                id_proyeccion, id_usuario, categoria, descripcion,
                valor_mensual, tipo_duracion, meses, fecha_inicio, quincena,
                modo_ambas, activo, fecha_creacion
            )
            SELECT
                id_proyeccion, id_usuario, categoria, descripcion,
                valor_mensual, tipo_duracion, meses, fecha_inicio, quincena,
                COALESCE(modo_ambas, 'DIVIDIR'),
                COALESCE(activo, 1), COALESCE(fecha_creacion, CURRENT_TIMESTAMP)
            FROM proyecciones_ahorro
            """
        )
        conexion.exec_driver_sql(
            """
            INSERT INTO abonos_proyeccion_v15 (
                id_abono, id_proyeccion, anio, mes, valor, fecha_registro
            )
            SELECT
                id_abono, id_proyeccion, anio, mes, valor,
                COALESCE(fecha_registro, CURRENT_TIMESTAMP)
            FROM abonos_proyeccion
            """
        )

        # La tabla hija se elimina primero para no disparar el ON DELETE CASCADE.
        conexion.exec_driver_sql("DROP TABLE abonos_proyeccion")
        conexion.exec_driver_sql("DROP TABLE proyecciones_ahorro")
        conexion.exec_driver_sql(
            "ALTER TABLE proyecciones_ahorro_v15 RENAME TO proyecciones_ahorro"
        )
        conexion.exec_driver_sql(
            "ALTER TABLE abonos_proyeccion_v15 RENAME TO abonos_proyeccion"
        )
        conexion.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_proyecciones_ahorro_id_usuario "
            "ON proyecciones_ahorro (id_usuario)"
        )
        conexion.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_abonos_proyeccion_id_proyeccion "
            "ON abonos_proyeccion (id_proyeccion)"
        )


def _migrar_saldos_incapacidad() -> None:
    """Marca como aplicados los saldos de incapacidad heredados (SRS v1.5).

    El modelo anterior encolaba saldos por mes y los aplicaba al guardar el
    periodo. SRS v1.5 eliminó el rollover: cada mes recalcula su tramo desde las
    fechas registradas. Los saldos pendientes que queden en una base migrada se
    marcan como aplicados para que no parezcan deuda vigente en ninguna consulta.

    Es idempotente: solo toca filas con `aplicado = 0`.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql(
            "PRAGMA table_info(saldos_incapacidad)"
        ).fetchall()
        if not filas:
            return
        conexion.exec_driver_sql(
            "UPDATE saldos_incapacidad SET aplicado = 1, id_periodo_aplicado = NULL "
            "WHERE aplicado = 0"
        )


def _migrar_columnas_usuarios() -> None:
    """Agrega `avatar_url` a `usuarios` (SRS v1.8, avatar híbrido).

    Las cuentas existentes quedan con `NULL` y muestran el círculo de iniciales hasta
    que vuelvan a entrar con Google. Es idempotente: solo añade la columna si falta.
    """
    if not _conexion_sqlite:
        return

    with motor.begin() as conexion:
        filas = conexion.exec_driver_sql("PRAGMA table_info(usuarios)").fetchall()
        existentes = {fila[1] for fila in filas}
        if existentes and "avatar_url" not in existentes:
            conexion.exec_driver_sql("ALTER TABLE usuarios ADD COLUMN avatar_url VARCHAR(500)")


def _migrar_garantia_detalle() -> None:
    """Agrega la fecha de garantía por producto a `venta_detalle` (SRS v1.9).

    Las líneas antiguas reciben la fecha de su orden: es la más cercana de sus
    productos, así que puede quedar antes de lo que corresponde a un producto con
    más meses de garantía. Las ventas nuevas guardan la fecha exacta de cada línea.
    Es idempotente en SQLite (PRAGMA) y en PostgreSQL (`IF NOT EXISTS`).
    """
    if _conexion_sqlite:
        with motor.begin() as conexion:
            filas = conexion.exec_driver_sql("PRAGMA table_info(venta_detalle)").fetchall()
            if not filas:
                return
            if "garantia_fecha_fin" not in {fila[1] for fila in filas}:
                conexion.exec_driver_sql("ALTER TABLE venta_detalle ADD COLUMN garantia_fecha_fin DATE")
    else:
        with motor.begin() as conexion:
            conexion.exec_driver_sql(
                "ALTER TABLE venta_detalle ADD COLUMN IF NOT EXISTS garantia_fecha_fin DATE"
            )

    with motor.begin() as conexion:
        conexion.exec_driver_sql(
            "UPDATE venta_detalle SET garantia_fecha_fin = ("
            "SELECT ventas.garantia_fecha_fin FROM ventas "
            "WHERE ventas.id_venta = venta_detalle.id_venta) "
            "WHERE garantia_fecha_fin IS NULL"
        )


def _migrar_deduccion_vinculada() -> None:
    """Agrega el enlace deducción → deuda a `deducciones_fijas` (SRS v1.9).

    Las deducciones anteriores quedan sin deuda vinculada y se calculan como antes.
    SQLite comprueba las columnas con PRAGMA; PostgreSQL usa `IF NOT EXISTS`.
    """
    if _conexion_sqlite:
        with motor.begin() as conexion:
            filas = conexion.exec_driver_sql("PRAGMA table_info(deducciones_fijas)").fetchall()
            if filas and "id_deuda" not in {fila[1] for fila in filas}:
                conexion.exec_driver_sql(
                    "ALTER TABLE deducciones_fijas ADD COLUMN id_deuda VARCHAR(32) "
                    "REFERENCES deudas (id_deuda) ON DELETE SET NULL"
                )
    else:
        with motor.begin() as conexion:
            conexion.exec_driver_sql(
                "ALTER TABLE deducciones_fijas ADD COLUMN IF NOT EXISTS id_deuda VARCHAR(32) "
                "REFERENCES deudas (id_deuda) ON DELETE SET NULL"
            )


def _migrar_categorias_y_vinculos() -> None:
    """Agrega las categorías cerradas y los vínculos con deudas (SRS v1.9).

    En SQLite se comprueban las columnas con `PRAGMA`; en PostgreSQL se usa
    `ADD COLUMN IF NOT EXISTS`, porque `create_all` no altera tablas ya
    existentes. Después se normalizan los textos heredados a los ocho nombres
    del catálogo, sin borrar ningún registro.

    La categoría 8 se deja intacta en los datos heredados: se deriva de las
    deudas activas en tiempo de cálculo, no se guarda en cada gasto.

    Los pagos de «Trabajos Extras» llevan la categoría técnica «Trabajo extra»
    y se excluyen de la normalización; ver `ADR-60`.
    """
    if _conexion_sqlite:
        with motor.begin() as conexion:
            columnas_gastos = {
                fila[1] for fila in conexion.exec_driver_sql("PRAGMA table_info(gastos)").fetchall()
            }
            if columnas_gastos and "id_deuda" not in columnas_gastos:
                conexion.exec_driver_sql(
                    "ALTER TABLE gastos ADD COLUMN id_deuda VARCHAR(32) "
                    "REFERENCES deudas (id_deuda) ON DELETE SET NULL"
                )
            columnas_fijas = {
                fila[1]
                for fila in conexion.exec_driver_sql("PRAGMA table_info(deducciones_fijas)").fetchall()
            }
            if columnas_fijas:
                if "categoria" not in columnas_fijas:
                    conexion.exec_driver_sql(
                        "ALTER TABLE deducciones_fijas ADD COLUMN categoria "
                        "VARCHAR(60) NOT NULL DEFAULT 'Otros Gastos Fijos'"
                    )
                if "id_deuda" not in columnas_fijas:
                    conexion.exec_driver_sql(
                        "ALTER TABLE deducciones_fijas ADD COLUMN id_deuda VARCHAR(32) "
                        "REFERENCES deudas (id_deuda) ON DELETE SET NULL"
                    )
    else:
        with motor.begin() as conexion:
            conexion.exec_driver_sql(
                "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS id_deuda VARCHAR(32) "
                "REFERENCES deudas (id_deuda) ON DELETE SET NULL"
            )
            conexion.exec_driver_sql(
                "ALTER TABLE deducciones_fijas ADD COLUMN IF NOT EXISTS categoria "
                "VARCHAR(60) NOT NULL DEFAULT 'Otros Gastos Fijos'"
            )
            conexion.exec_driver_sql(
                "ALTER TABLE deducciones_fijas ADD COLUMN IF NOT EXISTS id_deuda VARCHAR(32) "
                "REFERENCES deudas (id_deuda) ON DELETE SET NULL"
            )

    # Normalización de datos: solo se escriben los nombres del catálogo, así que
    # la sentencia es segura en ambos motores (sin parámetros dependientes del
    # dialecto). Se hace en una transacción aparte para no repetir el DDL.
    with motor.begin() as conexion:
        # La cuarta columna excluye de la normalización una categoría técnica:
        # los pagos de «Trabajos Extras» usan «Trabajo extra», que no pertenece
        # al catálogo cerrado. Si se normalizara a «Otros Gastos Fijos», la
        # comprobación de idempotencia de los pagos dejaría de encontrarlos y
        # crearía duplicados en cada arranque (ADR-60).
        consultas = (
            ("gastos", "id_gasto", False, catalogo.CATEGORIA_TRABAJO),
            ("deducciones_fijas", "id_deduccion", True, None),
        )
        for tabla, columna_id, tiene_descripcion, categoria_excluida in consultas:
            seleccion = f"SELECT {columna_id}, categoria"
            filtro = ""
            if tiene_descripcion:
                seleccion += ", descripcion"
            if categoria_excluida is not None:
                filtro = f" WHERE categoria <> '{categoria_excluida}'"
            filas = conexion.exec_driver_sql(
                f"{seleccion} FROM {tabla}{filtro}"
            ).fetchall()
            for fila in filas:
                identificador, categoria = fila[0], fila[1]
                descripcion = fila[2] if tiene_descripcion else ""
                canonico = (
                    catalogo.CATEGORIA_CREDITOS
                    if tiene_descripcion and catalogo.es_credito(descripcion)
                    else catalogo.normalizar_categoria(categoria)
                )
                if canonico != categoria:
                    conexion.exec_driver_sql(
                        f"UPDATE {tabla} SET categoria = '{canonico}' "
                        f"WHERE {columna_id} = '{identificador}'"
                    )


def _migrar_valor_atajo() -> None:
    """Agrega `chancucos.valor_pago` en SQLite y PostgreSQL (SRS v1.9, 4.2).

    Los atajos existentes quedan sin valor: la tarjeta simplemente no muestra
    esa línea hasta que el usuario edite o vuelva a crear el atajo.
    """
    if _conexion_sqlite:
        with motor.begin() as conexion:
            existentes = {
                fila[1]
                for fila in conexion.exec_driver_sql("PRAGMA table_info(chancucos)").fetchall()
            }
            if existentes and "valor_pago" not in existentes:
                conexion.exec_driver_sql(
                    "ALTER TABLE chancucos ADD COLUMN valor_pago NUMERIC(14, 2)"
                )
    else:
        with motor.begin() as conexion:
            conexion.exec_driver_sql(
                "ALTER TABLE chancucos ADD COLUMN IF NOT EXISTS valor_pago NUMERIC(14, 2)"
            )


def _migrar_feedback_resolucion() -> None:
    """Agrega `feedback_usuarios.fecha_resolucion` (SRS v3.0, punto 7.2).

    Los reportes existentes conservan su estado; el campo nuevo queda nulo hasta
    que el administrador cambie el estado. Es idempotente en SQLite y PostgreSQL.
    """
    if _conexion_sqlite:
        with motor.begin() as conexion:
            existentes = {
                fila[1]
                for fila in conexion.exec_driver_sql(
                    "PRAGMA table_info(feedback_usuarios)"
                ).fetchall()
            }
            if existentes and "fecha_resolucion" not in existentes:
                conexion.exec_driver_sql(
                    "ALTER TABLE feedback_usuarios ADD COLUMN fecha_resolucion DATETIME"
                )
    else:
        with motor.begin() as conexion:
            conexion.exec_driver_sql(
                "ALTER TABLE feedback_usuarios ADD COLUMN IF NOT EXISTS fecha_resolucion TIMESTAMPTZ"
            )


def _migrar_tipo_deuda_inicial() -> None:
    """Permite el tipo `DEUDA_INICIAL` en `movimientos_proveedor` (SRS v4.44, §8.1).

    SQLite no puede cambiar un `CHECK` con `ALTER TABLE`, así que la tabla se
    reconstruye conservando todas sus filas y su índice. En PostgreSQL se
    reemplaza la restricción. Es idempotente: si el tipo ya está permitido, no
    hace nada.
    """
    if _conexion_sqlite:
        with motor.begin() as conexion:
            definicion = conexion.exec_driver_sql(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'movimientos_proveedor'"
            ).scalar()
            if not definicion or "DEUDA_INICIAL" in definicion:
                return
            conexion.exec_driver_sql(
                """
                CREATE TABLE movimientos_proveedor_v444 (
                    id_movimiento VARCHAR(32) NOT NULL,
                    fecha DATETIME NOT NULL,
                    tipo VARCHAR(20) NOT NULL,
                    id_venta VARCHAR(32),
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(14, 2) NOT NULL,
                    saldo_resultante NUMERIC(14, 2) NOT NULL,
                    PRIMARY KEY (id_movimiento),
                    CONSTRAINT ck_movimiento_monto CHECK (monto > 0),
                    CONSTRAINT ck_movimiento_tipo CHECK (
                        tipo IN ('COMPRA_CREDITO', 'ABONO', 'DEUDA_INICIAL')
                    ),
                    FOREIGN KEY(id_venta) REFERENCES ventas (id_venta)
                        ON DELETE RESTRICT
                )
                """
            )
            conexion.exec_driver_sql(
                "INSERT INTO movimientos_proveedor_v444 "
                "(id_movimiento, fecha, tipo, id_venta, concepto, monto, saldo_resultante) "
                "SELECT id_movimiento, fecha, tipo, id_venta, concepto, monto, "
                "saldo_resultante FROM movimientos_proveedor"
            )
            conexion.exec_driver_sql("DROP TABLE movimientos_proveedor")
            conexion.exec_driver_sql(
                "ALTER TABLE movimientos_proveedor_v444 RENAME TO movimientos_proveedor"
            )
            conexion.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_movimientos_proveedor_id_venta "
                "ON movimientos_proveedor (id_venta)"
            )
    elif _conexion_postgres:
        with motor.begin() as conexion:
            conexion.exec_driver_sql(
                """
                DO $$
                BEGIN
                    IF to_regclass('movimientos_proveedor') IS NOT NULL THEN
                        ALTER TABLE movimientos_proveedor
                            DROP CONSTRAINT IF EXISTS ck_movimiento_tipo;
                        ALTER TABLE movimientos_proveedor
                            ADD CONSTRAINT ck_movimiento_tipo
                            CHECK (tipo IN ('COMPRA_CREDITO', 'ABONO', 'DEUDA_INICIAL'));
                    END IF;
                END $$;
                """
            )


def _migrar_tipos_hora_2026() -> None:
    """Mapea el concepto histórico de recargo dominical al catálogo de 2026.

    SRS v4.8: los registros guardados bajo
    ``Recargo Dominical o Festivo Diurno/Nocturno`` (y sus variantes) pasan a la
    clave canónica ``RECARGO_DOMINICAL_FESTIVO``, que ahora significa solo
    jornada diurna. El ``factor_aplicado`` histórico se actualiza al vigente
    (0.90); el ``valor_total`` se conserva porque es un dato ya liquidado.
    Es idempotente: una segunda pasada no encuentra filas que cambiar.
    """
    claves_anteriores = (
        "Recargo Dominical o Festivo Diurno/Nocturno",
        "RECARGODOMINICALOFESTIVODIURNO/NOCTURNO",
        "RECARGO_DOMINICAL_FESTIVO_DIURNO_NOCTURNO",
    )
    with motor.begin() as conexion:
        for anterior in claves_anteriores:
            conexion.execute(
                text(
                    "UPDATE registros_horas_extra "
                    "SET tipo_hora = :nuevo, factor_aplicado = :factor "
                    "WHERE tipo_hora = :anterior"
                ),
                {
                    "nuevo": "RECARGO_DOMINICAL_FESTIVO",
                    "factor": 0.9,
                    "anterior": anterior,
                },
            )


def aplicar_migraciones() -> None:
    """Ejecuta todas las migraciones idempotentes del esquema.

    Es el único punto de entrada para arrancar la app o para migrar una base
    vacía a PostgreSQL: crea las tablas que falten y añade las columnas nuevas
    sin borrar datos. Puede llamarse las veces que haga falta.
    """
    crear_esquema()
    # La migración de atajos corre después de crear el esquema: si la tabla no
    # existía, ya se creó con la estructura nueva y la función no hace nada.
    _migrar_chancucos()
    _migrar_valor_atajo()
    _migrar_columnas_deudas()
    _migrar_proyeccion_quincena()
    _migrar_saldos_incapacidad()
    _migrar_columnas_usuarios()
    _migrar_garantia_detalle()
    _migrar_deduccion_vinculada()
    _migrar_categorias_y_vinculos()
    _migrar_feedback_resolucion()
    _migrar_tipo_deuda_inicial()
    _migrar_tipos_hora_2026()


def inicializar_base_datos() -> None:
    """Prepara el esquema y siembra las cuentas de demostración.

    Se ejecuta al construir la aplicación. La siembra es condicional (solo si no
    hay usuarios), por lo que reiniciar el servidor no duplica cuentas.
    """
    from app.servicios import usuarios

    aplicar_migraciones()
    with FabricaSesiones() as sesion:
        usuarios.sembrar_demostracion(sesion)
