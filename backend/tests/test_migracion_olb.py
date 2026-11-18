"""Pruebas de la reconstrucción de OLB_BYTE al esquema sin inventario (ADR-35).

El motor SQLAlchemy se fija al importar `app.core.base_datos`, así que cada caso
corre en un proceso aparte con su propia base SQLite creada con el esquema anterior.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

RAIZ_BACKEND = Path(__file__).resolve().parent.parent

ESQUEMA_ANTERIOR = """
CREATE TABLE productos (
    id_producto VARCHAR(32) PRIMARY KEY,
    sku VARCHAR(40) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    costo NUMERIC(14,2) NOT NULL DEFAULT 0,
    precio_venta NUMERIC(14,2) NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT 0,
    garantia_meses SMALLINT
);
CREATE TABLE ventas (
    id_venta VARCHAR(32) PRIMARY KEY,
    id_cliente VARCHAR(32) NOT NULL,
    fecha_venta DATETIME NOT NULL,
    total NUMERIC(14,2) NOT NULL DEFAULT 0,
    saldo_pendiente NUMERIC(14,2) NOT NULL DEFAULT 0,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
);
CREATE TABLE venta_detalle (
    id_detalle VARCHAR(32) PRIMARY KEY,
    id_venta VARCHAR(32) NOT NULL,
    id_producto VARCHAR(32) NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario NUMERIC(14,2) NOT NULL
);
CREATE TABLE abonos (
    id_abono VARCHAR(32) PRIMARY KEY,
    id_venta VARCHAR(32) NOT NULL,
    monto NUMERIC(14,2) NOT NULL,
    metodo_pago VARCHAR(30) NOT NULL DEFAULT 'EFECTIVO',
    fecha_abono DATETIME NOT NULL
);
"""

SCRIPT_RECONSTRUCCION = """
import sqlite3, sys
from app.core.base_datos import crear_esquema

crear_esquema()

conexion = sqlite3.connect(sys.argv[1])
for tabla in ("productos", "ventas", "venta_detalle", "abonos"):
    columnas = [fila[1] for fila in conexion.execute(f"PRAGMA table_info({tabla})")]
    print(tabla, ",".join(columnas))
"""


SCRIPT_RENOMBRE = """
import sqlite3, sys
from app.core.base_datos import crear_esquema

crear_esquema()
conexion = sqlite3.connect(sys.argv[1])
conexion.execute("ALTER TABLE venta_detalle RENAME COLUMN categoria TO referencia")
conexion.commit()
conexion.close()

crear_esquema()
conexion = sqlite3.connect(sys.argv[1])
print(",".join(fila[1] for fila in conexion.execute("PRAGMA table_info(venta_detalle)")))
"""


def _correr_migracion(ruta_bd: Path, script: str = SCRIPT_RECONSTRUCCION) -> subprocess.CompletedProcess[str]:
    """Ejecuta una migración en un proceso aislado sobre la base indicada.

    Args:
        ruta_bd: Archivo SQLite con el esquema de prueba.
        script: Código Python a ejecutar en el proceso.

    Returns:
        Resultado del proceso con la salida estándar y de error.
    """
    entorno = os.environ.copy()
    entorno["DATABASE_URL"] = f"sqlite:///{ruta_bd.as_posix()}"
    entorno["ENTORNO"] = "pruebas"
    entorno["CLAVE_SECRETA"] = "clave-secreta-solo-para-pruebas-0123456789"
    return subprocess.run(
        [sys.executable, "-c", script, str(ruta_bd)],
        cwd=RAIZ_BACKEND,
        env=entorno,
        capture_output=True,
        text=True,
        check=False,
    )


def _crear_base_anterior(ruta: Path, con_datos: bool) -> None:
    """Crea una base con el esquema anterior, opcionalmente con una venta.

    Args:
        ruta: Archivo SQLite a crear.
        con_datos: Si es verdadero, inserta una orden antes de migrar.
    """
    conexion = sqlite3.connect(ruta)
    conexion.executescript(ESQUEMA_ANTERIOR)
    if con_datos:
        conexion.execute(
            "INSERT INTO ventas (id_venta, id_cliente, fecha_venta, total, saldo_pendiente, estado) "
            "VALUES ('v1', 'c1', '2026-01-01', 100, 100, 'PENDIENTE')"
        )
    conexion.commit()
    conexion.close()


def test_reconstruye_tablas_vacias_al_esquema_sin_stock(tmp_path: Path) -> None:
    """Sin datos, la migración quita `stock` y agrega las columnas nuevas."""
    ruta = tmp_path / "anterior.db"
    _crear_base_anterior(ruta, con_datos=False)

    resultado = _correr_migracion(ruta)

    assert resultado.returncode == 0, resultado.stderr
    salida = dict(linea.split(" ", 1) for linea in resultado.stdout.strip().splitlines())
    assert "stock" not in salida["productos"].split(",")
    assert "numero_orden" in salida["ventas"].split(",")
    assert "producto_nombre" in salida["venta_detalle"].split(",")
    assert "costo_unitario" in salida["venta_detalle"].split(",")


def test_no_reconstruye_si_hay_ventas_registradas(tmp_path: Path) -> None:
    """Con una orden registrada, la migración se detiene para no perder datos."""
    ruta = tmp_path / "con_datos.db"
    _crear_base_anterior(ruta, con_datos=True)

    resultado = _correr_migracion(ruta)

    assert resultado.returncode != 0
    assert "tiene datos" in resultado.stderr
    conexion = sqlite3.connect(ruta)
    filas = conexion.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    conexion.close()
    assert filas == 1


def test_referencia_se_renombra_a_categoria_sin_perder_datos(tmp_path: Path) -> None:
    """Una base con `referencia` en las líneas de venta pasa a tener `categoria`."""
    ruta = tmp_path / "referencia.db"

    resultado = _correr_migracion(ruta, SCRIPT_RENOMBRE)

    assert resultado.returncode == 0, resultado.stderr
    assert "categoria" in resultado.stdout.strip().split(",")
    assert "referencia" not in resultado.stdout.strip().split(",")


def test_base_nueva_no_requiere_reconstruccion(tmp_path: Path) -> None:
    """Ejecutar la migración dos veces sobre una base ya nueva no hace nada."""
    ruta = tmp_path / "nueva.db"
    _crear_base_anterior(ruta, con_datos=False)
    assert _correr_migracion(ruta).returncode == 0

    segunda = _correr_migracion(ruta)

    assert segunda.returncode == 0, segunda.stderr

