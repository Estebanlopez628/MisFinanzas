"""Pruebas de la SRS v3.0, bloque 3 (UI/UX y títulos)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

RUTA_APP = Path(__file__).resolve().parent.parent / "app"
CSS = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")


def test_acceso_de_ayuda_es_texto_lineal(cliente_usuario: TestClient) -> None:
    """Sin pastilla ni íconos pesados: enlaces limpios con SVG de 14 px."""
    html = cliente_usuario.get("/").text
    assert "ayuda-inicio__enlace" in html
    assert "ayuda-inicio__opcion" not in html
    assert "ayuda-inicio__icono" in html
    assert "stroke-width=\"1.75\"" in html
    assert "data-invitar-amigos" in html
    assert ".ayuda-inicio__enlace--movil" in CSS
    assert "border-radius: 999px" not in CSS.split(".ayuda-inicio {")[1].split("}")[0]


def test_textos_justificados_y_volver_primario(cliente_usuario: TestClient) -> None:
    """El centro de ayuda y el legal van justificados; volver es azul."""
    html = cliente_usuario.get("/ayuda").text
    assert 'class="boton boton--primario boton--pequeno"' in html
    assert "Volver al inicio" in html
    assert "text-align: justify" in CSS
    assert ".dialogo-legal__cuerpo p," in CSS
    assert ".ayuda-acordeon p," in CSS


def test_contraste_de_flechas_calendario_y_modales() -> None:
    """Selects, fechas y modales usan gris claro y centrado global."""
    assert "stroke='%239CA3AF'" in CSS
    assert "filter: invert(0.82) brightness(1.15)" in CSS
    assert "color-scheme: dark" in CSS
    assert ".modal-centrado," in CSS
    assert "inset: 0" in CSS
    assert "dialog::backdrop" in CSS
    assert "z-index: 50" in CSS


def test_enlaces_azul_suave() -> None:
    """El morado desaparece: azul #60A5FA en todos los enlaces de texto."""
    assert CSS.count("#60A5FA") >= 4
    assert ".enlace:visited" in CSS
    perfil = (RUTA_APP / "templates/perfil/index.html").read_text(encoding="utf-8")
    assert "Recuperar contraseña" not in perfil


def test_titulo_y_limpieza_del_modal_de_abono() -> None:
    """El modal de abono tiene el título nuevo y sin guiones visibles."""
    html = (RUTA_APP / "templates/olb_byte/cobro.html").read_text(encoding="utf-8")
    assert "Registrar Abono / Pago Total" in html
    assert "Opción 1 ·" not in html
    # No hay separadores de guiones en texto visible.
    for linea in html.splitlines():
        if "{#" not in linea and "#}" not in linea:
            assert "-------" not in linea


def test_boton_agregar_gasto_igual_a_guardar_incapacidad() -> None:
    """SRS v3.1: todos comparten el azul institucional (primario)."""
    finanzas = (RUTA_APP / "templates/finanzas/index.html").read_text(encoding="utf-8")
    trabajos = (RUTA_APP / "templates/trabajos/index.html").read_text(encoding="utf-8")
    incapacidades = (RUTA_APP / "templates/incapacidades/index.html").read_text(encoding="utf-8")

    assert 'class="boton boton--primario" type="submit"' in incapacidades
    assert 'class="boton boton--primario" type="submit"' in finanzas
    assert 'class="boton boton--primario" type="submit"' in trabajos


def test_campo_bloqueado_con_candado() -> None:
    """El valor vinculado se pinta gris con candado y cursor de no escritura."""
    js = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")
    assert 'classList.add("campo__control--bloqueado")' in js
    assert "background-color: rgba(30, 41, 59, 0.85)" in CSS
    assert "cursor: not-allowed" in CSS
    assert "rect x='4' y='10'" in CSS  # candado SVG


def test_titulos_nuevos_de_cartera(cliente_admin: TestClient) -> None:
    """El panel usa los títulos aprobados y el principal va centrado."""
    html = cliente_admin.get("/olb-byte/cartera").text
    assert "ESTADO DE CARTERA" in html
    assert "panel__titulo--centrado" in html
    assert "CUENTAS POR COBRAR Y PAGAR" in html
    assert "FLUJO DE CAJA DISPONIBLE" in html
    assert "BALANCE DE CARTERA Y EFECTIVO" not in html
