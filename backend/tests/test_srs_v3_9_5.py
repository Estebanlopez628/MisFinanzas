"""Pruebas de la SRS v3.9.5 (ícono PNG homogéneo y velocímetros en fila)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from app.routers import vistas

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


def test_icono_png_oficial_esta_en_estaticos() -> None:
    """El PNG del módulo está en la carpeta pública y es cuadrado."""
    ruta = RUTA_APP / "static/img/icono_OLBBYTE.png"
    assert ruta.exists()
    with Image.open(ruta) as imagen:
        ancho, alto = imagen.size
    assert abs(ancho - alto) <= 10


def test_icono_homologado_en_la_tarjeta(cliente_admin: TestClient) -> None:
    """El <img> usa 20×20 y object-fit: contain, igual que los demás íconos."""
    tarjeta = next(t for t in vistas.TARJETAS_DASHBOARD if t["clave"] == "olb-byte")
    assert tarjeta["icono_archivo"] == "img/icono_OLBBYTE.png"
    assert "icono_svg" not in tarjeta

    html = cliente_admin.get("/").text
    assert '<img class="tarjeta__icono-imagen"' in html
    assert 'alt="OLB_BYTE" width="24" height="24"' in html

    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    bloque = css.split(".tarjeta__icono-imagen {", 1)[1].split("}", 1)[0]
    assert "width: 24px" in bloque and "height: 24px" in bloque
    assert "object-fit: contain" in bloque
    assert "flex-shrink: 0" in bloque


def test_velocimetros_en_dos_columnas_sin_tocar_movil() -> None:
    """El contenedor fuerza dos columnas en escritorio y los SVG son compactos."""
    html = (RUTA_APP / "templates/presupuesto/index.html").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in html
    assert "max-width: 540px" in html
    assert html.count("min-width: 0; display: flex; flex-direction: column; align-items: center;") == 2
    assert html.count("flex-shrink: 0;") >= 2

    css = (RUTA_APP / "static/css/estilos.css").read_text(encoding="utf-8")
    inicio = css.index("@media (min-width: 768px) {", css.index(".cierre-deuda"))
    bloque = css[inicio : inicio + 900]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in bloque
    # SRS v4.5: el escritorio pasa de 540/520 px a 640 px.
    assert "max-width: 640px" in bloque
