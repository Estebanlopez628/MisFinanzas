"""Metadatos de vista previa (Open Graph y Twitter Cards) al compartir el enlace."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import crear_aplicacion

URL_PRODUCCION = "https://misfinanzas-odbc.onrender.com"
DESCRIPCION = (
    "Toma el control de tu dinero de forma simple y visual. Atrévete a probar un nuevo método "
    "para manejar tus finanzas. ¡Dale clic al enlace para ingresar y descubrirla!"
)


def test_etiquetas_open_graph_y_twitter_en_el_head() -> None:
    """La página de acceso declara título, descripción, URL, imagen y tarjeta grande."""
    html = TestClient(crear_aplicacion()).get("/login").text

    assert '<meta property="og:type" content="website" />' in html
    assert '<meta property="og:title" content="Mis Finanzas" />' in html
    assert '<meta name="twitter:title" content="Mis Finanzas" />' in html
    assert '<meta name="twitter:card" content="summary_large_image" />' in html
    assert f'<meta property="og:url" content="{URL_PRODUCCION}/" />' in html


def test_descripcion_compartida_sin_espacios_sobrantes() -> None:
    """Open Graph y Twitter reciben la misma descripción, sin el espacio inicial del texto original."""
    html = TestClient(crear_aplicacion()).get("/login").text

    assert f'<meta property="og:description" content="{DESCRIPCION}" />' in html
    assert f'<meta name="twitter:description" content="{DESCRIPCION}" />' in html


def test_imagen_de_vista_previa_es_absoluta_y_responde() -> None:
    """La imagen usa URL absoluta sin espacios y el servidor la entrega."""
    cliente = TestClient(crear_aplicacion())
    html = cliente.get("/login").text
    imagen = f"{URL_PRODUCCION}/estaticos/img/vista-previa.jpg?v=5"

    assert f'<meta property="og:image" content="{imagen}" />' in html
    assert f'<meta name="twitter:image" content="{imagen}" />' in html
    assert " " not in imagen

    respuesta = cliente.get("/estaticos/img/vista-previa.jpg")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("image/jpeg")
