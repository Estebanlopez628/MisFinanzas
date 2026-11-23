"""Pruebas de la SRS v4.8, bloque 1 (factores 2026 y datos históricos)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.core import base_datos
from app.core.config import ParametrosNomina
from app.core.config import FACTORES_RECARGO
from app.modelos import RegistroHorasExtra
from app.servicios import nomina, perfiles, usuarios
from app.servicios.periodos import guardar_liquidacion


def _id_admin(bd) -> str:
    """Devuelve el identificador del administrador sembrado.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador del administrador de pruebas.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_tabla_oficial_de_siete_conceptos() -> None:
    """Los siete factores 2026 son exactos y están en orden canónico."""
    assert list(FACTORES_RECARGO.items()) == [
        ("EXTRA_DIURNA_NORMAL", Decimal("1.25")),
        ("EXTRA_NOCTURNA", Decimal("1.75")),
        ("EXTRA_DIURNA_DOMINICAL_FESTIVA", Decimal("2.15")),
        ("EXTRA_NOCTURNA_DOMINICAL_FESTIVA", Decimal("2.65")),
        ("RECARGO_NOCTURNO", Decimal("0.35")),
        ("RECARGO_DOMINICAL_FESTIVO", Decimal("0.90")),
        ("RECARGO_NOCTURNO_DOMINICAL_FESTIVO", Decimal("1.25")),
    ]


def test_hora_ordinaria_usa_220_horas() -> None:
    """El divisor vigente en 2026 es 220, sobreescribible por configuración."""
    assert nomina.calcular_valor_hora_ordinaria(Decimal("2200000")) == Decimal("10000.0000")
    alternos = ParametrosNomina(horas_mensuales=Decimal("210"))
    assert nomina.calcular_valor_hora_ordinaria(Decimal("2100000"), alternos) == Decimal(
        "10000.0000"
    )


def test_acepta_horas_decimales_con_nuevos_factores() -> None:
    """10,4 horas dominicales diurnas se liquidan con el factor 2,15."""
    recargo = nomina.calcular_recargo(
        "EXTRA_DIURNA_DOMINICAL_FESTIVA", Decimal("10.4"), Decimal("10000")
    )
    assert recargo.factor == Decimal("2.15")
    assert recargo.valor_total == Decimal("223600.00")


def test_migracion_mapea_el_concepto_historico(bd) -> None:
    """El concepto heredado pasa a la clave canónica y la migración es idempotente."""
    id_usuario = _id_admin(bd)
    liquidacion = nomina.liquidar_periodo(Decimal("3000000"))
    periodo = guardar_liquidacion(bd, id_usuario, 2026, 11, 0, liquidacion, {})
    registro = RegistroHorasExtra(
        id_periodo=periodo.id_periodo,
        tipo_hora="Recargo Dominical o Festivo Diurno/Nocturno",
        cantidad_horas=Decimal("4"),
        factor_aplicado=Decimal("1.90"),
        valor_hora_base=Decimal("10000"),
        valor_total=Decimal("76000"),
    )
    bd.add(registro)
    bd.commit()

    base_datos._migrar_tipos_hora_2026()
    bd.refresh(registro)
    assert registro.tipo_hora == "RECARGO_DOMINICAL_FESTIVO"
    assert registro.factor_aplicado == Decimal("0.90")

    # Segunda pasada: no hay cambios y no se crean filas.
    base_datos._migrar_tipos_hora_2026()
    bd.refresh(registro)
    assert registro.tipo_hora == "RECARGO_DOMINICAL_FESTIVO"
    assert len(bd.scalars(select(RegistroHorasExtra)).all()) == 1


def test_migracion_no_toca_otros_conceptos(bd) -> None:
    """Solo se reescribe el concepto heredado; los demás conservan su clave."""
    id_usuario = _id_admin(bd)
    liquidacion = nomina.liquidar_periodo(Decimal("3000000"))
    periodo = guardar_liquidacion(bd, id_usuario, 2026, 10, 0, liquidacion, {})
    registro = RegistroHorasExtra(
        id_periodo=periodo.id_periodo,
        tipo_hora="EXTRA_NOCTURNA",
        cantidad_horas=Decimal("2"),
        factor_aplicado=Decimal("1.75"),
        valor_hora_base=Decimal("10000"),
        valor_total=Decimal("35000"),
    )
    bd.add(registro)
    bd.commit()

    base_datos._migrar_tipos_hora_2026()
    bd.refresh(registro)
    assert registro.tipo_hora == "EXTRA_NOCTURNA"
    assert registro.factor_aplicado == Decimal("1.75")


def test_nuevo_concepto_aparece_en_la_vista(cliente_admin) -> None:
    """El selector de conceptos de Mis Finanzas ofrece los siete ítems."""
    html = cliente_admin.get("/finanzas").text
    assert "Recargo nocturno dominical/festivo" in html
    assert "Recargo ordinario dominical/festivo" in html
    assert 'name="horas_RECARGO_NOCTURNO_DOMINICAL_FESTIVO"' in html
