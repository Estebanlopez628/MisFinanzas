"""Pruebas del bloque 4 de la SRS v1.9: modales, atajos y recibo."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core import base_datos
from app.servicios import chancucos, usuarios

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"
CSS = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")


def _bloque(texto: str, selector: str) -> str:
    """Devuelve el cuerpo de la primera regla CSS de un selector.

    Args:
        texto: Contenido del archivo CSS.
        selector: Selector a buscar.

    Returns:
        Declaraciones de la regla, sin las llaves.
    """
    return texto.split(selector + " {", 1)[1].split("}", 1)[0]


def test_todos_los_modales_usan_la_regla_global_de_centrado() -> None:
    """La utilidad `.modal-centrado` y el modal de edición comparten la regla."""
    bloque = _bloque(CSS, ".modal-centrado,\ndetails.edicion-gasto--modal[open]")

    for declaracion in (
        "position: fixed;",
        "inset: 0;",
        "display: flex;",
        "align-items: center;",
        "justify-content: center;",
        "z-index: 9000;",
        "padding: 1rem;",
    ):
        assert declaracion in bloque

    assert "details.edicion-gasto--modal[open]::before {" in CSS
    assert "content: none;" in CSS
    assert "details.edicion-gasto--modal[open] > summary {" in CSS


def test_el_atajo_guarda_y_muestra_el_valor_a_pagar(
    cliente_admin: TestClient, bd
) -> None:
    """El campo nuevo se persiste y aparece antes del botón «Pagar»."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None

    respuesta = cliente_admin.post(
        "/chancucos",
        data={
            "descripcion": "EPM energía",
            "numero_referencia": "REF-1",
            "valor_pago": "185.000",
            "url_pago": "https://pagos.epm.com.co",
            "dia_pago_1": "15",
            "unico_pago": "1",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303

    lista = chancucos.listar_chancucos(bd, cuenta.id_usuario)
    assert lista[0].valor_pago is not None
    assert float(lista[0].valor_pago) == 185000.0

    html = cliente_admin.get("/chancucos").text
    assert "Valor a pagar" in html
    assert "$185.000" in html

    finanzas = cliente_admin.get("/finanzas").text
    assert "Valor a pagar: $185.000" in finanzas
    assert "Pagar" in finanzas


def test_la_migracion_del_valor_del_atajo_es_idempotente(tmp_path, monkeypatch) -> None:
    """La columna se agrega en SQLite sin borrar los atajos existentes."""
    motor_viejo = create_engine(f"sqlite:///{(tmp_path / 'atajos.db').as_posix()}")
    with motor_viejo.begin() as conexion:
        conexion.exec_driver_sql(
            "CREATE TABLE chancucos ("
            "id_chancuco VARCHAR(32) PRIMARY KEY, descripcion VARCHAR(120), "
            "numero_referencia VARCHAR(60))"
        )
        conexion.exec_driver_sql(
            "INSERT INTO chancucos VALUES ('c1', 'Claro', '123')"
        )

    monkeypatch.setattr(base_datos, "motor", motor_viejo)
    monkeypatch.setattr(base_datos, "_conexion_sqlite", True)
    base_datos._migrar_valor_atajo()
    base_datos._migrar_valor_atajo()

    with motor_viejo.connect() as conexion:
        columnas = {
            fila[1] for fila in conexion.exec_driver_sql("PRAGMA table_info(chancucos)").fetchall()
        }
        descripcion = conexion.exec_driver_sql(
            "SELECT descripcion FROM chancucos WHERE id_chancuco = 'c1'"
        ).scalar()
    assert "valor_pago" in columnas
    assert descripcion == "Claro"
    motor_viejo.dispose()


def test_el_recibo_tiene_fondo_perla_texto_carbon_y_valores_verdes() -> None:
    """Se mantienen la cabecera azul y el verde de montos y estados."""
    cuerpo = _bloque(CSS, ".recibo")
    cabecera = _bloque(CSS, ".recibo__cabecera")
    cifra = _bloque(CSS, ".recibo__cifra,\nstrong.valor-negativo.recibo__cifra--saldo")

    assert "background: #f8fafc;" in cuerpo
    assert "color: #111827;" in cuerpo
    assert "background: var(--accent-blue);" in cabecera
    assert "color: #ffffff;" in cabecera
    assert "color: #16a34a;" in cifra

    fragmento = (RAIZ_APP / "templates" / "olb_byte" / "_fragmento_recibo.html").read_text(
        encoding="utf-8"
    )
    assert "background: #f8fafc;" in fragmento
    assert "#0f172a" not in fragmento
