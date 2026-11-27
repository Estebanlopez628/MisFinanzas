"""Pruebas de la SRS v3.7, bloque C (icono nativo neón azul)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

RUTA_APP = Path(__file__).resolve().parent.parent / "app"
IMGS = RUTA_APP / "static" / "img"


def test_pngs_del_icono_oficial() -> None:
    """Los cinco PNG existen y tienen las dimensiones correctas."""
    esperados = {
        "favicon-32.png": (32, 32),
        "icono-180.png": (180, 180),
        "icono-192.png": (192, 192),
        "icono-512.png": (512, 512),
        "icono-512-maskable.png": (512, 512),
    }
    for nombre, tamano in esperados.items():
        ruta = IMGS / nombre
        assert ruta.exists(), nombre
        with Image.open(ruta) as imagen:
            assert imagen.size == tamano, nombre


def test_etiquetas_html_y_manifiesto(cliente: TestClient) -> None:
    """base.html y el manifiesto apuntan al nuevo icono en todos los tamaños."""
    html = cliente.get("/login").text
    assert 'sizes="32x32"' in html and "favicon-32.png" in html
    assert 'sizes="192x192"' in html and "icono-192.png" in html
    assert 'rel="apple-touch-icon" sizes="180x180"' in html

    manifiesto = cliente.get("/manifest.webmanifest")
    datos = manifiesto.json()
    sizes = {icono["sizes"]: icono for icono in datos["icons"]}
    assert "192x192" in sizes and "512x512" in sizes
    assert sizes["192x192"]["purpose"] == "any maskable"
    assert any(icono["purpose"] == "maskable" for icono in datos["icons"])
    assert json.loads(manifiesto.text)["icons"]


def test_service_worker_actualizado() -> None:
    """La caché subió para que los dispositivos descarguen el icono nuevo."""
    js = (RUTA_APP / "static/js/sw.js").read_text(encoding="utf-8")
    assert 'var CACHE = "olb-finanzas-v187";' in js
