"""Pruebas de «Atajos guardados» en escritorio y móvil (SRS v1.9)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import chancucos, usuarios

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"


def test_los_tres_botones_de_la_tabla_tienen_el_mismo_grosor(
    cliente_admin: TestClient, bd
) -> None:
    """Copiar, Pagar y Eliminar comparten la clase de tamaño uniforme."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    chancucos.crear_chancuco(
        bd,
        cuenta.id_usuario,
        "EPM energía",
        "REF-15",
        valor_pago="185.000",
        url_pago="https://pagos.epm.com.co",
        dia_pago_1=15,
    )

    html = cliente_admin.get("/chancucos").text
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")

    assert html.count("atajo-accion") >= 6
    bloque = css.split(".boton.atajo-accion {", 1)[1].split("}", 1)[0]
    for regla in ("min-height: 34px;", "padding: 7px 12px;", "font-size: 0.78rem;"):
        assert regla in bloque


def test_la_fila_movil_y_el_modal_muestran_toda_la_informacion(
    cliente_admin: TestClient, bd
) -> None:
    """La fila es tipo Excel y el modal agrupa datos y acciones Pagar/Eliminar."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    chancuco = chancucos.crear_chancuco(
        bd,
        cuenta.id_usuario,
        "Claro internet",
        "REF-99",
        valor_pago="120.000",
        url_pago="https://pagos.claro.com.co",
        dia_pago_1=10,
        dia_pago_2=25,
    )

    html = cliente_admin.get("/chancucos").text

    assert 'class="tabla tabla--atajos"' in html
    assert f'data-chancuco-fila data-id-chancuco="{chancuco.id_chancuco}"' in html
    assert "atajo-modal" in html
    assert "Detalle del atajo" in html
    assert "REF-99" in html
    assert "$120.000" in html
    assert "Día 10 · Día 25" in html
    assert 'data-copiar="REF-99"' in html
    assert ">Pagar</a>" in html
    assert ">Eliminar</button>" in html
    assert html.index(">Pagar</a>") < html.index(">Eliminar</button>")


def test_el_css_de_movil_oculta_columnas_y_el_js_abre_el_modal() -> None:
    """Solo descripción, valor y día en la fila; la fila abre el modal."""
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    javascript = (RAIZ_APP / "static" / "js" / "deudas.js").read_text(encoding="utf-8")
    plantilla = (RAIZ_APP / "templates" / "chancucos" / "index.html").read_text(encoding="utf-8")

    movil = css.split("@media (max-width: 640px)", 1)[1]
    assert ".tabla--atajos tr[data-chancuco-fila]" in movil
    assert "> td:nth-child(1)" in movil
    assert "> td:nth-child(5)" in movil
    assert "> td:nth-child(6) > a" in movil
    assert ".atajo-modal > summary" in movil
    assert 'conectarFilas("tr[data-chancuco-fila]"' in javascript
    assert "js/deudas.js" in plantilla
