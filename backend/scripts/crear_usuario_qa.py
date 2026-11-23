"""Crea (o actualiza) los usuarios y datos de QA de la SRS v4.4.

Responsabilidad
---------------
Aprovisionar la cuenta `prueba_qa@misfinanzas.local` con perfil financiero y una
deuda de muestra, y la cuenta `prueba_qa_admin@misfinanzas.local` con rol de
administrador, para recorrer el flujo completo sin pasar por el onboarding.
Es idempotente: si las cuentas ya existen, solo asegura los datos mínimos.

Uso (desde `backend/`):

    .venv\\Scripts\\python -m scripts.crear_usuario_qa
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.base_datos import FabricaSesiones, aplicar_migraciones
from app.servicios import deudas, gastos, perfiles, usuarios

CORREO_QA = "prueba_qa@misfinanzas.local"
CONTRASENA_QA = "QA_MisFinanzas_2026!"
ALIAS_QA = "QA v4.4"

CORREO_ADMIN_QA = "prueba_qa_admin@misfinanzas.local"
CONTRASENA_ADMIN_QA = "QA_Admin_2026!"
ALIAS_ADMIN_QA = "QA Admin"


def _asegurar_cuenta(bd, correo: str, contrasena: str, alias: str, rol: str):
    """Devuelve una cuenta existente o la crea.

    Args:
        bd: Sesión de base de datos.
        correo: Correo de la cuenta.
        contrasena: Contraseña en texto plano.
        alias: Apodo visible.
        rol: Rol RBAC.

    Returns:
        La cuenta encontrada o creada.
    """
    cuenta = usuarios.buscar_por_correo(bd, correo)
    if cuenta is not None:
        return cuenta, "existente"
    return (
        usuarios.crear_usuario(bd, correo, contrasena, alias, rol),
        "creada",
    )


def main() -> None:
    """Crea las cuentas, el perfil y una deuda de muestra.

    Returns:
        None. Imprime el resultado por consola.
    """
    aplicar_migraciones()
    bd = FabricaSesiones()
    try:
        cuenta, accion = _asegurar_cuenta(
            bd, CORREO_QA, CONTRASENA_QA, ALIAS_QA, usuarios.ROL_USUARIO
        )
        # SRS v4.8: el perfil QA replica el caso base (40 % Q1 / 60 % Q2,
        # deducciones en Q2) para comprobar el neto real de 2.060.775 COP.
        perfiles.guardar_perfil(
            bd,
            cuenta.id_usuario,
            Decimal("3484000"),
            "QUINCENAL",
            porcentaje_quincena_1="40",
            porcentaje_quincena_2="60",
            quincena_deducciones=2,
            dia_quincena_1=15,
            dia_quincena_2=30,
        )
        if not deudas.listar_deudas(bd, cuenta.id_usuario):
            deuda = deudas.crear_deuda(
                bd, cuenta.id_usuario, "Banco QA", "1.200.000", "300.000", 4,
                descripcion="Crédito QA",
            )
            gastos.crear_gasto(
                bd,
                cuenta.id_usuario,
                "Vivienda",
                "Cuota del crédito QA",
                "300.000",
                date.today(),
                es_fijo=True,
                quincena=1,
                id_deuda=deuda.id_deuda,
            )

        administrador, accion_admin = _asegurar_cuenta(
            bd,
            CORREO_ADMIN_QA,
            CONTRASENA_ADMIN_QA,
            ALIAS_ADMIN_QA,
            usuarios.ROL_ADMIN,
        )
        if not perfiles.perfil_configurado(bd, administrador.id_usuario):
            perfiles.guardar_perfil(
                bd, administrador.id_usuario, Decimal("3484000"), "MENSUAL"
            )

        print(f"Cuenta QA {accion}: {CORREO_QA} / {CONTRASENA_QA}")
        print(
            f"Cuenta QA admin {accion_admin}: {CORREO_ADMIN_QA} / {CONTRASENA_ADMIN_QA}"
        )
    finally:
        bd.close()


if __name__ == "__main__":
    main()
