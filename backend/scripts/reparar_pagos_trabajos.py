"""Repara los pagos de «Trabajos Extras» reclasificados y sus duplicados.

Responsabilidad
---------------
- Devolver a la categoría técnica «Trabajo extra» los pagos que una versión
  anterior de la migración de categorías convirtió a «Otros Gastos Fijos»
  (ADR-60).
- Eliminar las copias que ese fallo generó en cada arranque, dejando una sola
  por contrato, año, mes y quincena. Si el pago estaba cobrado, se conserva.
- Ser idempotente: se puede ejecutar las veces que haga falta.

Uso (desde `backend/`, con `DATABASE_URL` apuntando a la base a reparar):
    .venv\\Scripts\\python scripts\\reparar_pagos_trabajos.py --simular
    .venv\\Scripts\\python scripts\\reparar_pagos_trabajos.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RUTA_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RUTA_BACKEND))

from app.core.base_datos import FabricaSesiones, aplicar_migraciones  # noqa: E402
from app.servicios.trabajos import reparar_pagos_duplicados  # noqa: E402


def main() -> None:
    """Ejecuta la reparación desde la línea de comandos."""
    analizador = argparse.ArgumentParser(
        description="Repara los pagos duplicados de Trabajos Extras."
    )
    analizador.add_argument(
        "--simular",
        action="store_true",
        help="Muestra el conteo sin escribir en la base de datos.",
    )
    argumentos = analizador.parse_args()

    # La migración ya no reclasifica los pagos (ADR-60); se ejecuta para
    # asegurar que la base tiene todas las columnas antes de reparar.
    aplicar_migraciones()
    with FabricaSesiones() as sesion:
        resultado = reparar_pagos_duplicados(sesion, simular=argumentos.simular)

    if argumentos.simular:
        print(f"Pagos que se restaurarían: {resultado['restaurados']}")
        print(f"Duplicados que se eliminarían: {resultado['eliminados']}")
        print("Simulación: no se escribió nada en la base de datos.")
        return
    print(f"Pagos restaurados: {resultado['restaurados']}")
    print(f"Duplicados eliminados: {resultado['eliminados']}")
    print("Reparación terminada. Puedes volver a ejecutarla sin duplicar datos.")


if __name__ == "__main__":
    main()
