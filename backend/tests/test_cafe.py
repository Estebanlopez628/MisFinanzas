"""Apoyo voluntario al desarrollador: botón «invítame un café» y modal (solo Colombia)."""

from __future__ import annotations

TEXTO_ENLACE = "invítame un café"
NUMERO_TELEFONO = "316 382 63 66"


def test_usuario_comun_ve_el_enlace_de_apoyo(cliente_usuario) -> None:
    """USER_FINANZAS ve el botón del pie y el modal con el QR de Bre-B."""
    html = cliente_usuario.get("/").text

    assert TEXTO_ENLACE in html
    assert 'data-abrir-dialogo="dialogo-cafe"' in html
    assert 'id="dialogo-cafe"' in html
    assert "$6.000 COP" in html
    assert 'alt="Código QR de Bre-B"' in html
    assert "data:image/png;base64," in html


def test_el_apoyo_no_expone_el_telefono(cliente_usuario) -> None:
    """Ni el número ni los botones de copiado aparecen: solo el QR."""
    html = cliente_usuario.get("/").text

    assert NUMERO_TELEFONO not in html
    assert "data-copiar" not in html.split('id="dialogo-cafe"')[1].split("</dialog>")[0]
    assert "Número:" not in html


def test_administrador_no_ve_el_apoyo(cliente_admin) -> None:
    """El administrador no recibe el botón ni el modal de apoyo."""
    html = cliente_admin.get("/").text

    assert TEXTO_ENLACE not in html
    assert 'id="dialogo-cafe"' not in html
