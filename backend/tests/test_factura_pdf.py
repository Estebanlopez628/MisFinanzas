"""Pruebas de la factura PDF de OLB_BYTE (Fase 7, ADR-36).

Las pruebas que generan PDF usan Chromium real de Playwright; por eso son las
únicas que tardan más. Cubren el nombre del archivo, los logos, la capacidad de una
página, la respuesta HTTP y el fallo controlado cuando el navegador no está.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.routers.vistas import plantillas
from app.servicios import comercial, factura_pdf


def _venta(bd, lineas: int = 2, nombre: str = "Ana Pérez"):
    """Registra una orden con el número de líneas indicado.

    Args:
        bd: Sesión de base de datos.
        lineas: Número de productos distintos.
        nombre: Cliente.

    Returns:
        La orden persistida.
    """
    fecha = datetime(2026, 11, 10, 15, 0, tzinfo=comercial.ZONA_TIENDA)
    productos = [
        comercial.LineaVenta(
            nombre=f"Producto {indice}",
            referencia=f"REF-{indice}",
            cantidad=1,
            precio_unitario="50000",
            costo_unitario="30000",
        )
        for indice in range(lineas)
    ]
    return comercial.registrar_venta(bd, nombre, "3001234567", productos, fecha)


def _paginas(pdf: bytes) -> int:
    """Cuenta las páginas de un PDF leyendo sus objetos `/Page`.

    Args:
        pdf: Bytes del PDF.

    Returns:
        Número de páginas declaradas.
    """
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf))


def test_nombre_de_archivo_quita_tildes_y_simbolos() -> None:
    """El nombre usa el número de orden y el cliente en ASCII, sin símbolos."""
    assert factura_pdf.nombre_archivo(1, "Ana Pérez") == "Factura_OLB_BYTE_No_1_Ana_Perez.pdf"
    assert factura_pdf.nombre_archivo(7, "José Luis / Ruiz") == "Factura_OLB_BYTE_No_7_Jose_Luis_Ruiz.pdf"
    assert factura_pdf.nombre_archivo(3, "¿¡!?") == "Factura_OLB_BYTE_No_3_Cliente.pdf"


def test_logos_se_embeben_como_data_uri() -> None:
    """Los cinco logos de `assets/` se leen y quedan como data URI PNG."""
    for clave in factura_pdf.PATRONES_LOGO:
        assert factura_pdf.logo_como_data_uri(clave).startswith("data:image/png;base64,"), clave


def test_datos_factura_completa_la_tabla_hasta_diez_filas(bd) -> None:
    """Con dos líneas quedan ocho filas vacías para mantener la tabla de diez filas."""
    venta = _venta(bd, lineas=2)

    contexto = factura_pdf.datos_factura(bd, venta)

    assert len(contexto["lineas"]) == 2
    assert len(contexto["filas_vacias"]) == 8
    assert contexto["nota"] == "Gracias por apoyar nuestro emprendimiento tecnológico"
    assert contexto["nombre_archivo"] == "Factura_OLB_BYTE_No_1_Ana_Perez.pdf"


def test_datos_factura_rechaza_mas_de_diez_productos(bd) -> None:
    """Una factura con más de diez líneas no cabe en una página y se rechaza."""
    venta = _venta(bd, lineas=11)

    with pytest.raises(ValueError, match="hasta 10 productos"):
        factura_pdf.datos_factura(bd, venta)


def test_plantilla_muestra_datos_medios_y_nota(bd) -> None:
    """El HTML del PDF trae cliente, productos, totales, medios de pago y pie de página."""
    venta = _venta(bd, lineas=2)
    contexto = factura_pdf.datos_factura(bd, venta)

    html = plantillas.get_template("olb_byte/factura_pdf.html").render(contexto)

    assert "Ana Pérez" in html
    assert "Producto 0" in html
    assert "Gracias por apoyar nuestro emprendimiento tecnológico" in html
    assert "316 382 63 66" in html
    assert "1151949473-3" in html
    assert "Saldo pendiente" in html
    assert "ANULADA" not in html


def test_plantilla_marca_las_ordenes_anuladas(bd) -> None:
    """Una orden anulada lleva la marca de agua ANULADA en su factura."""
    venta = _venta(bd, lineas=1)
    comercial.anular_venta(bd, venta.id_venta, "Error")

    html = plantillas.get_template("olb_byte/factura_pdf.html").render(
        factura_pdf.datos_factura(bd, venta)
    )

    assert "marca-anulada" in html


def test_pdf_real_tiene_una_sola_pagina(bd) -> None:
    """Chromium genera un PDF Carta de una sola página con diez filas."""
    venta = _venta(bd, lineas=3)
    html = plantillas.get_template("olb_byte/factura_pdf.html").render(
        factura_pdf.datos_factura(bd, venta)
    )

    pdf = factura_pdf.generar_pdf(html)

    assert pdf.startswith(b"%PDF")
    assert _paginas(pdf) == 1


def test_ruta_pdf_descarga_con_nombre_de_archivo(cliente_admin: TestClient, bd) -> None:
    """La descarga responde PDF con el nombre de archivo de la factura."""
    venta = _venta(bd, lineas=2)

    respuesta = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}/pdf")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert 'attachment; filename="Factura_OLB_BYTE_No_1_Ana_Perez.pdf"' in respuesta.headers["content-disposition"]
    assert respuesta.content.startswith(b"%PDF")


def test_vista_previa_se_muestra_en_linea(cliente_admin: TestClient, bd) -> None:
    """La vista previa pide el PDF en línea, no como descarga."""
    venta = _venta(bd, lineas=1)

    respuesta = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}/pdf", params={"descargar": 0})

    assert respuesta.headers["content-disposition"].startswith("inline")


def test_ruta_pdf_con_mas_de_diez_productos_explica_el_motivo(cliente_admin: TestClient, bd) -> None:
    """Sin poder generar el PDF, la respuesta indica el motivo y cómo volver."""
    venta = _venta(bd, lineas=11)

    respuesta = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}/pdf")

    assert respuesta.status_code == 422
    assert "hasta 10 productos" in respuesta.text
    assert f"/olb-byte/factura/{venta.id_venta}" in respuesta.text


def test_sin_chromium_responde_503_con_instrucciones(
    cliente_admin: TestClient, bd, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el navegador no está instalado, se explica cómo instalarlo."""
    venta = _venta(bd, lineas=1)

    def sin_navegador(_html: str) -> bytes:
        raise factura_pdf.ChromiumNoDisponible("No se pudo generar el PDF: playwright install chromium")

    monkeypatch.setattr(factura_pdf, "generar_pdf", sin_navegador)

    respuesta = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}/pdf")

    assert respuesta.status_code == 503
    assert "playwright install chromium" in respuesta.text


def test_pdf_de_orden_inexistente_devuelve_404(cliente_admin: TestClient) -> None:
    """Una orden que no existe responde 404."""
    assert cliente_admin.get("/olb-byte/factura/no-existe/pdf").status_code == 404


def test_usuario_publico_no_descarga_facturas(cliente_usuario: TestClient, bd) -> None:
    """La factura PDF exige administrador."""
    venta = _venta(bd, lineas=1)

    assert cliente_usuario.get(f"/olb-byte/factura/{venta.id_venta}/pdf").status_code == 403


def test_vista_de_factura_ofrece_vista_previa_descarga_y_compartir(cliente_admin: TestClient, bd) -> None:
    """La factura en pantalla enlaza la vista previa, la descarga y compartir (RF-19)."""
    venta = _venta(bd, lineas=1)

    respuesta = cliente_admin.get(f"/olb-byte/factura/{venta.id_venta}")

    assert "Vista previa PDF" in respuesta.text
    assert "Descargar PDF" in respuesta.text
    assert f"/olb-byte/factura/{venta.id_venta}/pdf" in respuesta.text
    assert "data-compartir" in respuesta.text
    assert "Factura_OLB_BYTE_No_1_Ana_Perez.pdf" in respuesta.text
