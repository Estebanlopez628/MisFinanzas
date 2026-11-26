"""Pruebas de la SRS v4.44: Deep Links normalizados, errores en modal y cabecera."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.servicios.chancucos import _validar_url, normalizar_enlace_pago

RUTA = Path(__file__).resolve().parent.parent / "app"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    (
        ("daviplata://", "daviplata://"),
        ("daviplata://.", "daviplata://."),
        ("daviplata", "daviplata://"),
        ("Nequi", "nequi://"),
        ("www.entidad.com/pago", "https://www.entidad.com/pago"),
        ("https://pagos.entidad.com", "https://pagos.entidad.com"),
    ),
)
def test_normalizacion_de_enlaces(entrada: str, esperado: str) -> None:
    """Nombres de app y dominios se completan; los esquemas se conservan."""
    assert _validar_url(entrada) == esperado


def test_vacio_es_opcional() -> None:
    """Un enlace vacío se guarda sin error."""
    assert normalizar_enlace_pago("   ") is None
    assert _validar_url("") is None


@pytest.mark.parametrize("entrada", ("daviplata:pago", "ftp:/sin-barras"))
def test_esquemas_mal_formados_siguen_rechazados(entrada: str) -> None:
    """Sin `://` ni nombre de app válido, el enlace se rechaza."""
    with pytest.raises(ValueError):
        _validar_url(entrada)


def test_javascript_sigue_prohibido() -> None:
    """Ningún enlace ejecutable se guarda aunque se normalice."""
    with pytest.raises(ValueError):
        _validar_url("javascript://alert(1)")


def test_formulario_normaliza_antes_de_validar() -> None:
    """El frontend completa el enlace antes de validarlo."""
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    inicio = js.index("function normalizarEnlace(texto)")
    bloque = js[inicio : inicio + 700]
    assert "https://" in bloque
    assert "toLowerCase() + \"://\"" in bloque
    submit = js[js.index("var valor = normalizarEnlace(campo.value);") :][:120]
    assert "campo.value = valor;" in submit


def test_errores_del_modal_quedan_dentro_del_modal() -> None:
    """El formulario de edición tiene banner propio y se mantiene abierto."""
    plantilla = (RUTA / "templates/chancucos/index.html").read_text(encoding="utf-8")
    assert "data-atajo-editar" in plantilla
    assert 'data-error-modal hidden' in plantilla
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    bloque = js[js.index("form[data-atajo-editar]") :][:4000]
    assert "mostrarErrorModal(formulario, banner" in bloque
    assert "evento.preventDefault();" in bloque
    assert 'evento.submitter.hasAttribute("formaction")' in bloque
    assert "window.recargarManteniendoScroll()" in bloque


def test_tarjeta_movil_ref_izquierda_valor_derecha() -> None:
    """En la fila 2, la referencia va antes del valor y cada uno cae sobre su botón."""
    plantilla = (RUTA / "templates/finanzas/index.html").read_text(encoding="utf-8")
    datos = plantilla[plantilla.index("atajo-tarjeta-movil__datos") :]
    datos = datos[: datos.index("atajo-tarjeta-movil__acciones")]
    assert datos.index("atajo-tarjeta-movil__ref") < datos.index("atajo-tarjeta-movil__valor")
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".atajo-tarjeta-movil__datos {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 1fr 1fr" in bloque
    valor = css.split(".atajo-tarjeta-movil__valor {", 1)[1].split("}", 1)[0]
    assert "justify-self: end" in valor and "text-align: right" in valor


def test_cabecera_factura_centrada_sin_tocar_el_resto() -> None:
    """Logo y eslogan se centran entre sí; el resto de la factura no cambia."""
    css = (RUTA / "static/css/factura-olb.css").read_text(encoding="utf-8")
    contenedor = css.split(".marca-contenedor {", 1)[1].split("}", 1)[0]
    assert "display: flex" in contenedor
    assert "flex-direction: column" in contenedor
    assert "align-items: center" in contenedor
    eslogan = css.split(".marca-eslogan {", 1)[1].split("}", 1)[0]
    assert "text-align: center" in eslogan
    assert "margin-top: -10px" in contenedor
    assert "margin-left: -6px" in contenedor


def test_recuadro_totales_transparente_con_celdas_blancas() -> None:
    """El fondo blanco vive solo en las celdas de valor (SRS §4.3)."""
    css = (RUTA / "static/css/factura-olb.css").read_text(encoding="utf-8")
    caja = css.split(".totales-caja {", 1)[1].split("}", 1)[0]
    assert "background: transparent" in caja
    assert "border-radius: 10px" in caja
    assert "overflow: hidden" in caja
    valor = css.split("\n.total-valor {", 1)[1].split("}", 1)[0]
    assert "background: #ffffff" in valor


def test_divisor_entre_total_y_abonado_solo_cuando_hay_abono() -> None:
    """La fila TOTAL hereda el divisor de SUBTOTAL si existe ABONADO / SALDO."""
    plantilla = (RUTA / "templates/olb_byte/_hoja_factura.html").read_text(encoding="utf-8")
    assert (
        'class="total-fila total-fila--final{% if venta.saldo_pendiente and '
        'venta.saldo_pendiente > 0 %} total-fila--con-abono{% endif %}"'
    ) in plantilla
    css = (RUTA / "static/css/factura-olb.css").read_text(encoding="utf-8")
    subtotal = css.split(".total-fila--subtotal .total-valor {", 1)[1].split("}", 1)[0]
    con_abono = css.split(".total-fila--con-abono .total-valor {", 1)[1].split("}", 1)[0]
    assert "border-bottom: 1px solid #b8d6f5" in subtotal
    assert "border-bottom: 1px solid #b8d6f5" in con_abono
    abono = css.split(".total-fila--abono .total-etiqueta {", 1)[1].split("}", 1)[0]
    assert "border-top" not in abono
