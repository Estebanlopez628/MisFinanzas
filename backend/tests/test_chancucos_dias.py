"""Pruebas de los días de pago de los atajos (SRS v1.7, bloque D).

Cubren la validación del día (1–31), el pago único frente al pago doble, el
distintivo «Día 15» en la tabla y en la tarjeta de Mis Finanzas, y la
idempotencia de la migración de columnas.
"""

from __future__ import annotations

from app.core import base_datos
from app.servicios import chancucos, usuarios


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------


def test_atajo_guarda_un_dia_de_pago(bd) -> None:
    """Un pago único conserva su día y deja el segundo en `None`."""
    atajo = chancucos.crear_chancuco(
        bd, _id_admin(bd), "EPM energía", "123456", dia_pago_1="15"
    )

    assert atajo.dia_pago_1 == 15
    assert atajo.dia_pago_2 is None


def test_atajo_guarda_dos_dias_de_pago(bd) -> None:
    """Un pago doble conserva los dos días."""
    atajo = chancucos.crear_chancuco(
        bd,
        _id_admin(bd),
        "Tarjeta Visa",
        "998877",
        dia_pago_1=15,
        dia_pago_2="30",
    )

    assert (atajo.dia_pago_1, atajo.dia_pago_2) == (15, 30)


def test_segundo_dia_igual_al_primero_se_descarta(bd) -> None:
    """Dos días iguales se interpretan como un solo pago."""
    atajo = chancucos.crear_chancuco(
        bd, _id_admin(bd), "Gas", "1", dia_pago_1=10, dia_pago_2=10
    )

    assert atajo.dia_pago_2 is None


def test_dia_fuera_de_rango_se_rechaza(bd) -> None:
    """Los días 0 y 32 no son válidos."""
    for dia in ("0", "32", "abc"):
        try:
            chancucos.crear_chancuco(
                bd, _id_admin(bd), "Agua", "2", dia_pago_1=dia
            )
        except ValueError as error:
            assert "1 y 31" in str(error)
        else:  # pragma: no cover - protección contra regresiones
            raise AssertionError(f"Se aceptó el día {dia}")


# ---------------------------------------------------------------------------
# Camino HTTP
# ---------------------------------------------------------------------------


def test_http_pago_unico_ignora_el_segundo_dia(cliente_admin, bd) -> None:
    """Con «único pago» el segundo día enviado no se guarda."""
    respuesta = cliente_admin.post(
        "/chancucos",
        data={
            "descripcion": "Claro internet",
            "numero_referencia": "998877",
            "unico_pago": "1",
            "dia_pago_1": "15",
            "dia_pago_2": "30",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    atajo = chancucos.listar_chancucos(bd, _id_admin(bd))[0]
    assert atajo.dia_pago_1 == 15
    assert atajo.dia_pago_2 is None


def test_http_pago_doble_guarda_los_dos_dias(cliente_admin, bd) -> None:
    """Elegir «dos pagos» conserva el segundo día."""
    cliente_admin.post(
        "/chancucos",
        data={
            "descripcion": "Tarjeta Visa",
            "numero_referencia": "445566",
            "unico_pago": "0",
            "dia_pago_1": "15",
            "dia_pago_2": "30",
        },
        follow_redirects=False,
    )

    atajo = chancucos.listar_chancucos(bd, _id_admin(bd))[0]
    assert (atajo.dia_pago_1, atajo.dia_pago_2) == (15, 30)


def test_panel_muestra_los_dias_de_pago(cliente_admin, bd) -> None:
    """La tabla de atajos muestra «Día 15 · Día 30»."""
    chancucos.crear_chancuco(
        bd,
        _id_admin(bd),
        "Tarjeta Visa",
        "445566",
        dia_pago_1=15,
        dia_pago_2=30,
    )

    html = cliente_admin.get("/chancucos").text

    assert "Día 15 · Día 30" in html


def test_tarjeta_de_finanzas_muestra_el_dia(cliente_admin, bd) -> None:
    """La tarjeta embebida en Mis Finanzas lleva el distintivo del día."""
    chancucos.crear_chancuco(bd, _id_admin(bd), "EPM energía", "123456", dia_pago_1=15)

    html = cliente_admin.get("/finanzas").text

    assert "Día 15" in html
    assert "atajo-dia-texto" in html


def test_atajo_antiguo_sin_dia_sigue_visible(cliente_admin, bd) -> None:
    """Un atajo migrado sin día no rompe la vista ni inventa una fecha."""
    chancucos.crear_chancuco(bd, _id_admin(bd), "Gas natural", "777888")

    html = cliente_admin.get("/chancucos").text

    assert "Gas natural" in html
    assert "Sin día definido" in html


# ---------------------------------------------------------------------------
# Migración
# ---------------------------------------------------------------------------


def test_migracion_de_chancucos_es_idempotente() -> None:
    """Ejecutar la migración dos veces no falla ni duplica columnas."""
    base_datos._migrar_columnas_chancucos()
    base_datos._migrar_columnas_chancucos()

    with base_datos.motor.connect() as conexion:
        columnas = [
            fila[1]
            for fila in conexion.exec_driver_sql("PRAGMA table_info(chancucos)")
        ]

    assert "dia_pago_1" in columnas
    assert "dia_pago_2" in columnas
