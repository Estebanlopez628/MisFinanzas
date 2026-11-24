"""Pruebas de la SRS v4.38: emojis de color y scroll exacto en modales."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas as servicio_deudas
from app.servicios import usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


def test_emojis_a_todo_color_en_titulos() -> None:
    """Los títulos usan emojis de color, no trazos SVG monocromáticos."""
    vistas = {
        "presupuesto/index.html": "🧾",
        "chancucos/index.html": "🔗",
        "historial/index.html": "📜",
    }
    for nombre, emoji in vistas.items():
        html = (RUTA / "templates" / nombre).read_text(encoding="utf-8")
        assert 'class="modulo__icono heroe__titulo-icono"' in html
        assert f">{emoji}</span>" in html
        assert "<svg" not in html.split('class="heroe__titulo-icono"')[0][-400:]

    finanzas = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    assert "💰" in finanzas


def test_scroll_se_guarda_y_restaura_en_toda_recarga() -> None:
    """Toda recarga guarda X e Y y la restauración espera al layout final."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    assert 'CLAVE_SCROLL_X = "misfinanzas_saved_scroll_x"' in js
    assert "window.guardarScrollApp = guardarScroll;" in js
    assert "window.recargarManteniendoScroll = function (yaGuardado) {" in js
    # La única recarga directa queda dentro del ayudante que guarda la posición.
    assert js.count("window.location.reload();") == 1
    assert js.count("window.recargarManteniendoScroll();") == 3
    assert js.count("window.recargarManteniendoScroll(true);") == 1
    assert 'window.scrollTo({ left: objetivoX, top: objetivoY, behavior: "instant" });' in js
    assert 'window.addEventListener("load", function () {' in js
    assert 'left: destino.x, top: destino.y' in js


def test_acreedor_editable_en_editar_deuda(cliente_admin: TestClient, bd) -> None:
    """El acreedor se puede corregir desde «Editar deuda» sin recrearla."""
    vista = (RUTA / "templates/deudas/index.html").read_text(encoding="utf-8")
    assert '<span class="campo__etiqueta">Acreedor</span>' in vista
    assert 'name="acreedor"' in vista
    assert 'type="hidden" name="acreedor"' not in vista

    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    deuda = servicio_deudas.crear_deuda(
        bd, cuenta.id_usuario, "Acreedor original", "1200000", "200000", 6,
        descripcion="Deuda QA v438",
    )
    respuesta = cliente_admin.post(
        f"/deudas/{deuda.id_deuda}/editar",
        data={
            "acreedor": "Acreedor corregido",
            "descripcion": "Deuda QA v438",
            "saldo_total": "1200000",
            "cuota": "200000",
            "cuotas_pendientes": "6",
            "periodicidad": "MENSUAL",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    bd.refresh(deuda)
    assert deuda.acreedor == "Acreedor corregido"


def test_modal_editar_solido_y_campos_contenidos() -> None:
    """El modal en estados inhabilitados conserva capa, fondo y campos."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("details.edicion-gasto--modal[open] > .edicion-gasto__formulario")
    bloque = css[inicio : css.index("}", inicio)]
    assert "background: var(--bg-card)" in bloque
    assert "z-index: 9002" in bloque
    assert ".edicion-gasto--modal[open] .campo," in css
    assert "min-width: 0;" in css

    fila = (RUTA / "templates/finanzas/_gasto_fijo.html").read_text(encoding="utf-8")
    for etiqueta in ("Categoría", "Descripción", "Valor (COP)"):
        assert etiqueta in fila
    assert "Actualizar" in fila
    assert "Abonar" in fila
    # SRS v4.39: el botón «Cancelar» se retira y el pie se centra.
    assert ">Cancelar<" not in fila
    assert "acciones-formulario--gasto" in fila
    assert ".edicion-gasto__formulario .acciones-formulario--gasto {" in css
    assert "justify-content: center;" in css
