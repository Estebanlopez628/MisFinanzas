"""Pruebas de la SRS v2.0, Fase B (correcciones del frontend).

Cubre el enlace directo de WhatsApp en la factura, el ciclo ida/vuelta con
`sessionStorage` y la visibilidad/autocompletado de los gastos vinculados a
deudas. Los textos del mensaje de factura y de la pregunta SI/NO quedan
protegidos contra regresiones.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import deudas, gastos, usuarios

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


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


def test_factura_js_normaliza_y_abre_chat_dirigido() -> None:
    """El botón sanea el celular y construye `wa.me/<57...>?text=<mensaje>`."""
    js = (RUTA_APP / "static/js/factura.js").read_text(encoding="utf-8")

    assert "function numeroDelEnlace(enlace)" in js
    assert r"replace(/[\s\-()\+]/g" in js
    assert '/^\\d{10}$/.test(limpio)' in js
    assert '/^57\\d{10}$/.test(limpio)' in js
    assert 'return "57" + limpio;' in js
    assert "var enlaceDirecto = \"https://wa.me/\" + numero + \"?text=\" + encodeURIComponent(texto);" in js
    assert 'window.open(enlaceDirecto, "_blank", "noopener,noreferrer")' in js
    # La apertura genérica ya no se usa en el evento de compartir.
    assert "window.open(whatsapp" not in js


def test_mensaje_de_la_factura_no_cambia() -> None:
    """El texto compartido sigue saliendo del mismo atributo y servicio."""
    plantilla = (RUTA_APP / "templates/olb_byte/factura.html").read_text(encoding="utf-8")
    assert 'data-texto="{{ texto_compartir }}"' in plantilla

    from app.servicios import comercial

    assert comercial.texto_compartir_factura.__doc__ is not None
    assert "adjunto tu factura de compra" in comercial.texto_compartir_factura.__doc__


def test_session_storage_usa_la_clave_y_etiquetas_de_la_srs() -> None:
    """El ciclo de ida y vuelta guarda módulo, etiqueta y datos del formulario."""
    js = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")

    assert 'var CLAVE_PENDIENTE = "misfinanzas_pending_debt_link";' in js
    assert 'modulo: "deducciones_fijas"' in js
    assert 'etiqueta: "Deducciones Fijas"' in js
    assert 'modulo: "finanzas_gastos_fijos"' in js
    assert 'etiqueta: "Gastos Fijos - Finanzas"' in js
    assert 'modulo: "trabajos_extras_gastos_fijos"' in js
    assert 'etiqueta: "Gastos Fijos - Trabajos Extras"' in js
    assert "origin_module: origen.modulo" in js
    assert "origin_label: origen.etiqueta" in js
    assert "form_data: datosFormulario(formulario)" in js
    assert "sessionStorage.removeItem(CLAVE_PENDIENTE)" in js
    # La pregunta SI/NO y su bloqueo siguen intactos.
    assert 'value="SI" data-vincular-si' in (RUTA_APP / "templates/_categorias.html").read_text(
        encoding="utf-8"
    )


def test_banner_de_regreso_muestra_la_etiqueta(cliente_admin: TestClient) -> None:
    """La vista de deudas muestra un banner con el nombre legible del origen."""
    html = cliente_admin.get("/deudas?volver=finanzas").text
    # SRS v3.0: el enlace es de texto y vive bajo el formulario «Nueva deuda».
    assert "enlace-volver-origen" in html
    assert "data-banner-volver" in html
    assert "Volver a Gastos Fijos - Finanzas para completar el registro" in html
    assert "guardado_deuda=1" in html

    html = cliente_admin.get("/deudas?volver=deducciones").text
    assert "Volver a Deducciones Fijas para completar el registro" in html

    html = cliente_admin.get("/deudas?volver=trabajos").text
    assert "Volver a Gastos Fijos - Trabajos Extras para completar el registro" in html

    # La etiqueta se ajusta también desde sessionStorage.
    js = (RUTA_APP / "static/js/deudas.js").read_text(encoding="utf-8")
    assert '"misfinanzas_pending_debt_link"' in js
    assert '"← Volver a " + pendiente.origin_label' in js


def test_cuota_se_autocompleta_y_bloquea() -> None:
    """Al elegir deuda se copia la cuota y el valor queda de solo lectura."""
    plantilla = (RUTA_APP / "templates/_categorias.html").read_text(encoding="utf-8")
    assert 'data-cuota="{{ (deuda.cuota_mensual or 0) | cop(false) }}"' in plantilla
    assert "El valor de este gasto está sincronizado con tu deuda" in plantilla
    assert 'href="/deudas"' in plantilla

    js = (RUTA_APP / "static/js/categorias.js").read_text(encoding="utf-8")
    assert "campoValor.value = cuota;" in js
    assert "campoValor.readOnly = true;" in js
    assert "campoValor.readOnly = false;" in js


def test_gasto_vinculado_visible_en_finanzas_y_gastos(
    bd, cliente_admin: TestClient
) -> None:
    """El gasto vinculado conserva su descripción y muestra solo la cuota vigente."""
    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco Visible", "1.200.000", "100.000", 12)
    gastos.crear_gasto(
        bd,
        id_usuario,
        "Créditos y Obligaciones",
        "Cuota visible",
        "50.000",
        date.today(),
        es_fijo=True,
        id_deuda=deuda.id_deuda,
    )

    html_finanzas = " ".join(cliente_admin.get("/finanzas").text.split())
    assert "Cuota visible" in html_finanzas
    # No se añade el acreedor a la fila: solo la descripción del usuario y la
    # cuota vigente, para no ensanchar el cuadro del gasto.
    assert "lista-gastos__vinculo" not in html_finanzas
    posicion = html_finanzas.find("Cuota visible")
    assert "100.000" in html_finanzas[posicion : posicion + 400]

    html_gastos = cliente_admin.get("/gastos").text
    assert "Cuota visible" in html_gastos
    assert "lista-gastos__vinculo" not in html_gastos

    filas = cliente_admin.get("/gastos/api/fijos").json()["gastos"]
    assert any(fila["acreedor_deuda"] == "Banco Visible" for fila in filas)


def test_gasto_vinculado_visible_en_trabajos_extras(bd) -> None:
    """Trabajos Extras conserva el gasto vinculado con la cuota de la deuda."""
    from app.servicios import gastos as servicio_gastos
    from app.servicios import trabajos

    id_usuario = _id_admin(bd)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco Trabajo", "600.000", "50.000", 12)
    trabajo = trabajos.crear_trabajo(
        bd, id_usuario, "Diseño", "500.000", date.today(), cliente="Cliente"
    )
    gasto = servicio_gastos.crear_gasto(
        bd,
        id_usuario,
        "Créditos y Obligaciones",
        "Cuota del trabajo",
        "1.000",
        date.today(),
        es_fijo=True,
        id_deuda=deuda.id_deuda,
    )
    gasto.id_trabajo = trabajo.id_trabajo
    bd.commit()

    fijos = trabajos.gastos_fijos_trabajo(bd, trabajo.id_trabajo)
    assert any(fijo.id_deuda == deuda.id_deuda for fijo in fijos)


def test_visibilidad_no_duplica_la_cuota_en_los_totales(bd) -> None:
    """La lista muestra el vínculo pero la quincena no vuelve a restarlo."""
    from decimal import Decimal

    from app.servicios import perfiles, quincenas

    id_usuario = _id_admin(bd)
    perfil = perfiles.obtener_perfil(bd, id_usuario)
    deuda = deudas.crear_deuda(bd, id_usuario, "Banco", "1.200.000", "100.000", 12)
    hoy = date.today()
    gastos.crear_gasto(
        bd,
        id_usuario,
        "Créditos y Obligaciones",
        "Cuota",
        "100.000",
        hoy,
        es_fijo=True,
        id_deuda=deuda.id_deuda,
    )

    resumen = quincenas.resumen_quincenas(bd, id_usuario, perfil, hoy.year, hoy.month)
    assert all(fila.gastos == Decimal("0.00") for fila in resumen)
    assert sum(len(fila.gastos_vinculados) for fila in resumen) == 1
