"""Pruebas del modo «Ambas quincenas» en las metas (SRS v1.7).

Cubren las dos formas de aplicar el monto cuando la meta se descuenta en los
dos pagos: `DIVIDIR` reparte la cuota ($100.000 → $50.000 + $50.000) y
`DUPLICAR` cobra la cuota completa en cada pago ($100.000 + $100.000). También
verifican que el total proyectado y los gastos generados reflejen el modo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modelos import ProyeccionAhorro
from app.servicios import ahorro, gastos, pagos_metas, usuarios

HOY = date.today()


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


def _gastos_de_la_meta(bd, id_usuario: str, id_proyeccion: str):
    """Lista los gastos del mes en curso generados por una meta.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los gastos.
        id_proyeccion: Meta consultada.

    Returns:
        Gastos de la meta, ordenados por quincena.
    """
    return sorted(
        (
            gasto
            for gasto in gastos.listar_gastos(bd, id_usuario, HOY.year, HOY.month)
            if gasto.id_proyeccion == id_proyeccion
        ),
        key=lambda gasto: gasto.quincena or 0,
    )


def _crear_meta(bd, id_usuario: str, modo: str, valor: str = "100.000"):
    """Crea una meta de 12 meses en ambas quincenas.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de la meta.
        modo: `DIVIDIR` o `DUPLICAR`.
        valor: Cuota escrita por el usuario.

    Returns:
        La meta persistida.
    """
    return ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Viaje a Santa Marta",
        valor,
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses=12,
        fecha_inicio=HOY,
        quincena=ahorro.QUINCENA_AMBAS,
        modo_ambas=modo,
    )


# ---------------------------------------------------------------------------
# Aritmética pura
# ---------------------------------------------------------------------------


def test_valor_por_pago_dividir_reparte_la_cuota() -> None:
    """Con DIVIDIR cada pago recibe la mitad de la cuota."""
    assert ahorro.valor_por_pago(
        "100.000", ahorro.QUINCENA_AMBAS, ahorro.MODO_DIVIDIR
    ) == Decimal("50000.00")


def test_valor_por_pago_duplicar_cobra_la_cuota_completa() -> None:
    """Con DUPLICAR cada pago recibe la cuota completa."""
    assert ahorro.valor_por_pago(
        "100.000", ahorro.QUINCENA_AMBAS, ahorro.MODO_DUPLICAR
    ) == Decimal("100000.00")


def test_valor_por_pago_una_sola_quincena_ignora_el_modo() -> None:
    """En quincena 1 o 2 el monto siempre es la cuota completa."""
    assert ahorro.valor_por_pago("100.000", 1, ahorro.MODO_DUPLICAR) == Decimal(
        "100000.00"
    )
    assert ahorro.valor_por_pago("100.000", 2, ahorro.MODO_DIVIDIR) == Decimal(
        "100000.00"
    )


def test_modo_invalido_se_rechaza() -> None:
    """Un modo desconocido no se acepta."""
    with pytest.raises(ValueError):
        ahorro.valor_por_pago("100.000", ahorro.QUINCENA_AMBAS, "MITAD")


# ---------------------------------------------------------------------------
# Persistencia y gastos generados
# ---------------------------------------------------------------------------


def test_meta_dividir_genera_dos_gastos_de_la_mitad(bd) -> None:
    """DIVIDIR crea un gasto de $50.000 en cada quincena."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, ahorro.MODO_DIVIDIR)
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, HOY.year, HOY.month)

    generados = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion)
    assert [gasto.quincena for gasto in generados] == [1, 2]
    assert [gasto.valor for gasto in generados] == [
        Decimal("50000.00"),
        Decimal("50000.00"),
    ]


def test_meta_duplicar_genera_dos_gastos_completos(bd) -> None:
    """DUPLICAR crea un gasto de $100.000 en cada quincena."""
    id_usuario = _id_admin(bd)
    meta = _crear_meta(bd, id_usuario, ahorro.MODO_DUPLICAR)
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, HOY.year, HOY.month)

    generados = _gastos_de_la_meta(bd, id_usuario, meta.id_proyeccion)
    assert [gasto.quincena for gasto in generados] == [1, 2]
    assert [gasto.valor for gasto in generados] == [
        Decimal("100000.00"),
        Decimal("100000.00"),
    ]


def test_total_proyectado_respeta_el_modo(bd) -> None:
    """El total de la meta suma lo que realmente descuenta cada mes."""
    id_usuario = _id_admin(bd)
    _crear_meta(bd, id_usuario, ahorro.MODO_DIVIDIR)
    _crear_meta(bd, id_usuario, ahorro.MODO_DUPLICAR)

    resumenes = ahorro.resumen_metas(bd, id_usuario)
    dividir = next(m for m in resumenes if m.proyeccion.modo_ambas == ahorro.MODO_DIVIDIR)
    duplicar = next(
        m for m in resumenes if m.proyeccion.modo_ambas == ahorro.MODO_DUPLICAR
    )

    # 100.000 × 12 meses = 1.200.000 / 200.000 × 12 meses = 2.400.000
    assert dividir.total_proyectado == Decimal("1200000.00")
    assert duplicar.total_proyectado == Decimal("2400000.00")


def test_quincena_unica_fuerza_modo_dividir(bd) -> None:
    """En una sola quincena el modo se normaliza a DIVIDIR."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Fondo",
        "100.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses=6,
        fecha_inicio=HOY,
        quincena=1,
        modo_ambas=ahorro.MODO_DUPLICAR,
    )
    assert meta.modo_ambas == ahorro.MODO_DIVIDIR


# ---------------------------------------------------------------------------
# Camino HTTP
# ---------------------------------------------------------------------------


def test_http_crear_meta_duplicar_guarda_el_modo(cliente_admin, bd) -> None:
    """El formulario envía `modo_ambas` y la meta lo conserva."""
    respuesta = cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "Computador nuevo",
            "valor_mensual": "100.000",
            "tipo_duracion": ahorro.DURACION_LIMITADA,
            "meses": "12",
            "unidad_periodo": "MESES",
            "fecha_inicio": HOY.isoformat(),
            "quincena": str(ahorro.QUINCENA_AMBAS),
            "modo_ambas": ahorro.MODO_DUPLICAR,
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    meta = bd.scalar(select(ProyeccionAhorro))
    assert meta is not None
    assert meta.modo_ambas == ahorro.MODO_DUPLICAR
    assert meta.quincena == ahorro.QUINCENA_AMBAS

    # La tarjeta de la meta debe renderizar el total mensual duplicado.
    vista = cliente_admin.get("/presupuesto")
    assert vista.status_code == 200
    assert "$200.000 al mes" in vista.text


def test_http_modo_invalido_devuelve_400(cliente_admin) -> None:
    """Un modo manipulado se rechaza con la vista de error."""
    respuesta = cliente_admin.post(
        "/presupuesto/metas",
        data={
            "categoria": "Ahorro",
            "descripcion": "Meta inválida",
            "valor_mensual": "100.000",
            "tipo_duracion": ahorro.DURACION_LIMITADA,
            "meses": "12",
            "unidad_periodo": "MESES",
            "fecha_inicio": HOY.isoformat(),
            "quincena": str(ahorro.QUINCENA_AMBAS),
            "modo_ambas": "OTRO",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
