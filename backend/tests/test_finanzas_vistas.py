"""Pruebas de la calculadora de "Mis Finanzas" (Tarea 6).

Verifican el formulario, el POST clásico (respaldo sin JavaScript) y el endpoint
JSON que alimenta el recálculo en vivo.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

RUTA = "/finanzas"
RUTA_JSON = "/finanzas/calcular"

SEIS_CAMPOS_HORAS = (
    "horas_EXTRA_DIURNA_NORMAL",
    "horas_EXTRA_NOCTURNA",
    "horas_EXTRA_DIURNA_DOMINICAL_FESTIVA",
    "horas_EXTRA_NOCTURNA_DOMINICAL_FESTIVA",
    "horas_RECARGO_NOCTURNO",
    "horas_RECARGO_DOMINICAL_FESTIVO",
)


def test_formulario_incluye_todos_los_campos(cliente_usuario: TestClient) -> None:
    """La calculadora expone sueldo, incapacidad y la matriz completa de recargos."""
    respuesta = cliente_usuario.get(RUTA)

    assert respuesta.status_code == 200
    assert 'name="sueldo_basico"' in respuesta.text
    assert 'name="deduccion_incapacidad"' in respuesta.text
    for campo in SEIS_CAMPOS_HORAS:
        assert f'name="{campo}"' in respuesta.text, campo
    assert 'data-calculadora' in respuesta.text
    assert 'data-campo="saldo_bolsillo"' in respuesta.text
    assert "js/finanzas.js" in respuesta.text


def test_post_clasico_sin_horas(cliente_usuario: TestClient) -> None:
    """Sueldo 3.000.000 sin recargos: saldo 2.960.000 y auxilio completo."""
    respuesta = cliente_usuario.post(RUTA, data={"sueldo_basico": "3.000.000"})

    assert respuesta.status_code == 200
    assert "2.960.000" in respuesta.text
    assert "Aplica Auxilio de Transporte" in respuesta.text
    assert "Sin horas extras ni recargos registrados." in respuesta.text


def test_post_clasico_con_horas_extras(cliente_usuario: TestClient) -> None:
    """10 horas nocturnas: recargo 250.000; salud y pensión sobre 3.250.000 (SRS v1.4)."""
    respuesta = cliente_usuario.post(
        RUTA,
        data={"sueldo_basico": "3000000", "horas_EXTRA_NOCTURNA": "10"},
    )

    assert respuesta.status_code == 200
    assert "3.190.000" in respuesta.text
    assert "Hora extra nocturna" in respuesta.text
    assert "250.000" in respuesta.text


def test_post_clasico_anula_auxilio_sobre_el_tope(cliente_usuario: TestClient) -> None:
    """Un sueldo por encima de 2 SMMLV pierde el auxilio de transporte."""
    respuesta = cliente_usuario.post(RUTA, data={"sueldo_basico": "3600000"})

    assert respuesta.status_code == 200
    assert "Supera los 2 salarios mínimos: No aplica Auxilio de Transporte" in respuesta.text
    assert 'data-aplica="no"' in respuesta.text


def test_post_clasico_reporta_sueldo_invalido(cliente_usuario: TestClient) -> None:
    """Un sueldo con letras no produce liquidación y conserva lo escrito."""
    respuesta = cliente_usuario.post(RUTA, data={"sueldo_basico": "mucho"})

    assert respuesta.status_code == 200
    assert "no es un número válido" in respuesta.text
    assert 'value="mucho"' in respuesta.text


def test_post_clasico_reporta_horas_negativas(cliente_usuario: TestClient) -> None:
    """Las horas negativas se rechazan con el nombre legible del concepto."""
    respuesta = cliente_usuario.post(
        RUTA, data={"sueldo_basico": "3000000", "horas_RECARGO_NOCTURNO": "-3"}
    )

    assert respuesta.status_code == 200
    assert "no pueden ser negativas" in respuesta.text


def test_json_devuelve_totales_formateados(cliente_usuario: TestClient) -> None:
    """El endpoint reactivo responde con los campos que consume el DOM."""
    respuesta = cliente_usuario.post(
        RUTA_JSON,
        json={"sueldo_basico": "3.000.000", "deduccion_incapacidad": "0"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    assert cuerpo["datos"]["saldo_bolsillo"] == "$2.960.000"
    assert cuerpo["datos"]["auxilio_transporte"] == "$200.000"
    assert cuerpo["datos"]["deduccion_salud"] == "$120.000"
    assert cuerpo["aplica_auxilio"] is True
    assert cuerpo["detalle"] == []


def test_json_incluye_el_desglose_de_recargos(cliente_usuario: TestClient) -> None:
    """Cada tipo de hora con registro aparece en `detalle` con su factor."""
    respuesta = cliente_usuario.post(
        RUTA_JSON,
        json={"sueldo_basico": "3000000", "horas_EXTRA_DIURNA_DOMINICAL_FESTIVA": "4"},
    )

    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    assert len(cuerpo["detalle"]) == 1
    fila = cuerpo["detalle"][0]
    assert fila["etiqueta"] == "Hora extra diurna dominical/festiva"
    assert fila["factor"] == "2,00"
    assert fila["horas"] == "4,00"
    assert fila["valor"] == "$114.285,71"


def test_json_anula_el_auxilio_y_explica_el_motivo(cliente_usuario: TestClient) -> None:
    """Sobre el tope, el mensaje del SRS viaja en la respuesta JSON."""
    respuesta = cliente_usuario.post(RUTA_JSON, json={"sueldo_basico": "3600000"})

    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    assert cuerpo["aplica_auxilio"] is False
    assert cuerpo["datos"]["auxilio_transporte"] == "$0"
    assert cuerpo["mensaje_auxilio"].startswith("Supera los 2 salarios mínimos")


def test_json_reporta_errores_de_validacion(cliente_usuario: TestClient) -> None:
    """Los errores usan el mismo formato que el resto de respuestas.

    Un sueldo vacío ya no es error: se toma del perfil configurado en el
    onboarding (SRS v1.2). Por eso la validación se ejercita con un valor no
    numérico, que sí debe rechazarse.
    """
    respuesta = cliente_usuario.post(RUTA_JSON, json={"sueldo_basico": "dos millones"})

    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["ok"] is False
    assert any("no es un número válido" in error for error in cuerpo["errores"])


def test_json_rechaza_cuerpo_no_objetivo(cliente_usuario: TestClient) -> None:
    """Un JSON válido pero que no es un objeto se rechaza con 400."""
    respuesta = cliente_usuario.post(RUTA_JSON, json=["3.000.000"])

    assert respuesta.status_code == 400
    assert respuesta.json()["ok"] is False


def test_json_exige_sesion(cliente: TestClient) -> None:
    """Sin sesión, el endpoint reactivo responde 401 (no HTML)."""
    respuesta = cliente.post(
        RUTA_JSON,
        json={"sueldo_basico": "3000000"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["ok"] is False
