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

    assert html.count("atajo-accion") >= 5
    bloque = css.split(".boton.atajo-accion {", 1)[1].split("}", 1)[0]
    for regla in ("min-height: 34px;", "padding: 7px 12px;", "font-size: 0.78rem;"):
        assert regla in bloque


def test_la_fila_movil_y_el_modal_muestran_toda_la_informacion(
    cliente_admin: TestClient, bd
) -> None:
    """La fila es tipo Excel y el modal permite editar el atajo con Actualizar/Eliminar."""
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
    assert "Editar atajo" in html
    assert "REF-99" in html
    assert "$120.000" in html
    assert "Día 10 · Día 25" in html
    # El modal es de edición: no lleva Copiar ni Pagar, y la URL va en un input.
    assert html.count('data-copiar="REF-99"') == 1
    assert "<dt>Enlace de pago</dt>" not in html
    assert 'name="url_pago"' in html
    assert ">Actualizar</button>" in html
    assert ">Eliminar</button>" in html

    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    datos = css.split(".atajo-modal__datos > div {", 1)[1].split("}", 1)[0]
    assert "border-bottom" not in datos


def test_los_atajos_de_mis_finanzas_abren_su_propio_modal(
    cliente_admin: TestClient, bd
) -> None:
    """En Mis Finanzas el modal muestra toda la información del atajo."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    chancuco = chancucos.crear_chancuco(
        bd,
        cuenta.id_usuario,
        "Agua acueducto",
        "REF-AGUA",
        valor_pago="95.000",
        url_pago="https://pagos.acueducto.com.co",
        dia_pago_1=8,
    )

    html = cliente_admin.get("/finanzas").text

    assert f'data-atajo-fila data-id-chancuco="{chancuco.id_chancuco}"' in html
    assert "atajo-finanzas-modal" in html
    assert "Detalle del atajo" in html
    assert "REF-AGUA" in html
    assert "$95.000" in html
    assert "Día 8" in html
    assert 'data-copiar="REF-AGUA"' in html
    assert ">Pagar</a>" in html
    assert "<dt>Enlace de pago</dt>" not in html

    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    descripcion = css.split(".lista-atajos__descripcion {", 1)[1].split("}", 1)[0]
    referencia = css.split(".lista-atajos__referencia code {", 1)[1].split("}", 1)[0]
    assert "font-size: 0.85rem;" in descripcion
    assert "font-size: 0.85rem;" in referencia

    centrado = css.split(".atajo-finanzas-modal .acciones-formulario--edicion {", 1)[1]
    assert "justify-items: center;" in centrado.split("}", 1)[0]
    movil = css.split("@media (max-width: 640px)", 1)[1]
    assert ".lista-atajos__item[data-atajo-fila]" in movil
    assert ".lista-atajos__texto small.ayuda" in movil
    assert "> .lista-atajos__referencia" in movil
    assert ">Ver</summary>" not in html

    javascript = (RAIZ_APP / "static" / "js" / "deudas.js").read_text(encoding="utf-8")
    assert 'conectarFilas("li[data-atajo-fila]"' in javascript
    plantilla = (RAIZ_APP / "templates" / "finanzas" / "index.html").read_text(encoding="utf-8")
    assert "js/deudas.js" in plantilla


def test_el_css_de_movil_oculta_columnas_y_el_js_abre_el_modal() -> None:
    """Solo descripción, valor y día en la fila; la fila abre el modal."""
    css = (RAIZ_APP / "static" / "css" / "estilos.css").read_text(encoding="utf-8")
    javascript = (RAIZ_APP / "static" / "js" / "deudas.js").read_text(encoding="utf-8")
    plantilla = (RAIZ_APP / "templates" / "chancucos" / "index.html").read_text(encoding="utf-8")

    movil = css.split("@media (max-width: 640px)", 1)[1]
    assert ".tabla--atajos thead tr" in movil
    assert ".tabla--atajos thead th:nth-child(2)" in movil
    assert "max-content" in movil
    assert ".tabla--atajos tr[data-chancuco-fila]" in movil
    assert "> td:nth-child(1)" in movil
    assert "> td:nth-child(5)" in movil
    assert "> td:nth-child(6) > a" in movil
    assert ">Ver</summary>" not in plantilla
    assert 'conectarFilas("tr[data-chancuco-fila]"' in javascript
    assert "js/deudas.js" in plantilla


def test_el_copiado_es_unico_y_vuelve_a_copiar_a_los_cinco_segundos() -> None:
    """Un solo manejador global muestra «¡Copiado!» y lo restauran a los 5 s."""
    app_js = (RAIZ_APP / "static" / "js" / "app.js").read_text(encoding="utf-8")
    finanzas_js = (RAIZ_APP / "static" / "js" / "finanzas.js").read_text(encoding="utf-8")

    assert "CONFIRMACION_COPIADO_MS = 5000" in app_js
    assert 'boton.textContent = "¡Copiado!"' in app_js
    assert "restaurarBotonCopiar" in app_js
    assert 'querySelectorAll(".boton--copiado")' in app_js
    assert "prepararCopiadoRapido" not in finanzas_js
    assert "copiarAlPortapapeles" not in finanzas_js


def test_editar_un_atajo_guarda_todos_los_cambios(cliente_admin: TestClient, bd) -> None:
    """El botón Actualizar del modal persiste los datos editados."""
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    chancuco = chancucos.crear_chancuco(
        bd, cuenta.id_usuario, "EPM", "REF-VIEJA", valor_pago="100.000", dia_pago_1=15
    )

    respuesta = cliente_admin.post(
        f"/chancucos/{chancuco.id_chancuco}/editar",
        data={
            "descripcion": "EPM energía",
            "numero_referencia": "REF-NUEVA",
            "valor_pago": "185.000",
            "url_pago": "https://pagos.epm.com.co/nueva",
            "dia_pago_1": "20",
            "dia_pago_2": "30",
            "favorito": "1",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    bd.refresh(chancuco)
    assert chancuco.descripcion == "EPM energía"
    assert chancuco.numero_referencia == "REF-NUEVA"
    assert float(chancuco.valor_pago) == 185000.0
    assert chancuco.dia_pago_1 == 20
    assert chancuco.dia_pago_2 == 30
    assert chancuco.favorito is True
    assert chancuco.url_pago == "https://pagos.epm.com.co/nueva"

    invalida = cliente_admin.post(
        f"/chancucos/{chancuco.id_chancuco}/editar",
        data={
            "descripcion": "EPM energía",
            "numero_referencia": "REF-NUEVA",
            "url_pago": "javascript:alert(1)",
        },
        follow_redirects=False,
    )
    assert invalida.status_code == 303
    assert "http" in invalida.headers["location"]
