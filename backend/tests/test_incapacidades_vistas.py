"""Pruebas de la vista de incapacidades (Tarea 4b y SRS v1.5).

Verifican que el formulario se renderiza, que la liquidación muestra el
descuento y el desglose por mes, y que los errores de captura se informan sin
romper la página. SRS v1.5 retiró el rollover: no hay saldos arrastrados.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

RUTA = "/incapacidades"
RUTA_CALCULO = "/incapacidades/calcular"


def test_formulario_disponible(cliente_usuario: TestClient) -> None:
    """La página debe cargar con los cuatro campos del formulario."""
    respuesta = cliente_usuario.get(RUTA)

    assert respuesta.status_code == 200
    assert 'name="fecha_inicio"' in respuesta.text
    assert 'name="fecha_fin"' in respuesta.text
    assert 'name="sueldo_basico"' in respuesta.text
    assert 'name="periodo_mes"' in respuesta.text
    assert "Cómo se calcula" in respuesta.text
    # SRS v1.5: el cálculo es automático y los días salen de las fechas.
    assert "Calcular incapacidad" not in respuesta.text
    assert "Guardar incapacidad" in respuesta.text


def test_liquidacion_simple_muestra_descuento(cliente_usuario: TestClient) -> None:
    """3 días con sueldo 3.000.000: un día al 66.67% → descuento 33.330."""
    respuesta = cliente_usuario.post(
        RUTA_CALCULO,
        data={
            "fecha_inicio": "2026-03-02",
            "fecha_fin": "2026-03-04",
            "sueldo_basico": "3.000.000",
            "periodo_mes": "2026-03",
        },
    )

    assert respuesta.status_code == 200
    assert "Resultado de la liquidación" in respuesta.text
    assert "33.330" in respuesta.text
    assert "1 día(s) arrastrados" not in respuesta.text


def test_liquidacion_que_cruza_de_mes_muestra_desglose(
    cliente_usuario: TestClient,
) -> None:
    """Marzo 30 a abril 2: marzo sin descuento y abril con 66.660."""
    respuesta = cliente_usuario.post(
        RUTA_CALCULO,
        data={
            "fecha_inicio": "2026-03-30",
            "fecha_fin": "2026-04-02",
            "sueldo_basico": "3000000",
            "periodo_mes": "2026-03",
        },
    )

    assert respuesta.status_code == 200
    assert "Desglose por mes" in respuesta.text
    assert "Abril de 2026" in respuesta.text
    assert "66.660" in respuesta.text
    assert "Saldos que se arrastran" not in respuesta.text


def test_mes_sin_dias_liquida_cero_y_muestra_el_total(
    cliente_usuario: TestClient,
) -> None:
    """Si el mes elegido no tiene días, el descuento es cero pero el rango se ve."""
    respuesta = cliente_usuario.post(
        RUTA_CALCULO,
        data={
            "fecha_inicio": "2026-05-04",
            "fecha_fin": "2026-05-06",
            "sueldo_basico": "3000000",
            "periodo_mes": "2026-04",
        },
    )

    assert respuesta.status_code == 200
    assert "0 día(s) en el mes" in respuesta.text
    assert "3 día(s) de incapacidad" in respuesta.text


def test_rango_invertido_muestra_error(cliente_usuario: TestClient) -> None:
    """El formulario debe explicar el error y conservar los valores escritos."""
    respuesta = cliente_usuario.post(
        RUTA_CALCULO,
        data={
            "fecha_inicio": "2026-03-10",
            "fecha_fin": "2026-03-01",
            "sueldo_basico": "3000000",
            "periodo_mes": "",
        },
    )

    assert respuesta.status_code == 200
    assert "no puede ser anterior" in respuesta.text
    assert "2026-03-10" in respuesta.text
    assert "Resultado de la liquidación" not in respuesta.text


def test_sueldo_invalido_muestra_error(cliente_usuario: TestClient) -> None:
    """Un sueldo con letras no debe producir una liquidación."""
    respuesta = cliente_usuario.post(
        RUTA_CALCULO,
        data={
            "fecha_inicio": "2026-03-02",
            "fecha_fin": "2026-03-04",
            "sueldo_basico": "mucho dinero",
            "periodo_mes": "2026-03",
        },
    )

    assert respuesta.status_code == 200
    assert "no es un número válido" in respuesta.text
    assert "Resultado de la liquidación" not in respuesta.text


def test_sueldo_cero_muestra_error(cliente_usuario: TestClient) -> None:
    """El sueldo debe ser positivo para poder liquidar."""
    respuesta = cliente_usuario.post(
        RUTA_CALCULO,
        data={
            "fecha_inicio": "2026-03-02",
            "fecha_fin": "2026-03-04",
            "sueldo_basico": "0",
            "periodo_mes": "",
        },
    )

    assert respuesta.status_code == 200
    assert "mayor que cero" in respuesta.text


def test_periodo_invalido_muestra_error(cliente_usuario: TestClient) -> None:
    """Un periodo con formato distinto a AAAA-MM se rechaza."""
    respuesta = cliente_usuario.post(
        RUTA_CALCULO,
        data={
            "fecha_inicio": "2026-03-02",
            "fecha_fin": "2026-03-04",
            "sueldo_basico": "3000000",
            "periodo_mes": "03/2026",
        },
    )

    assert respuesta.status_code == 200
    assert "AAAA-MM" in respuesta.text


def test_modulo_accesible_para_ambos_roles(
    cliente_admin: TestClient, cliente_usuario: TestClient
) -> None:
    """Incapacidades dejó de ser tarjeta externa; la ruta sigue disponible.

    En el bloque 3 el formulario se integrará dentro de "Mis Finanzas"; por
    ahora se comprueba que ambos roles conservan el acceso directo.
    """
    for cliente_autenticado in (cliente_admin, cliente_usuario):
        respuesta = cliente_autenticado.get(RUTA)
        assert respuesta.status_code == 200


def test_incapacidades_exige_sesion(cliente: TestClient) -> None:
    """Sin sesión, el formulario de incapacidades no se renderiza."""
    respuesta = cliente.get(RUTA, follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"
