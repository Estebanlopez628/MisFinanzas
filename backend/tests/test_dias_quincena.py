"""Pruebas de los días de cada quincena (SRS v1.9, bloque 2).

Cubren la validación de los días que escribe el usuario, los valores
predeterminados para perfiles sin días, las etiquetas que siguen al perfil en
metas, deducciones, gastos y el panel de quincenas, y las respuestas de la
vista de perfil ante datos incorrectos (sin errores internos).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.servicios import perfiles, quincenas, usuarios


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


def _perfil_quincenal(bd, dia_1: str = "5", dia_2: str = "20"):
    """Guarda un perfil quincenal con los días indicados.

    Args:
        bd: Sesión de base de datos.
        dia_1: Día de la quincena 1.
        dia_2: Día de la quincena 2.

    Returns:
        El perfil persistido.
    """
    return perfiles.guardar_perfil(
        bd,
        _id_admin(bd),
        "3000000",
        "QUINCENAL",
        "50",
        "50",
        1,
        dia_quincena_1=dia_1,
        dia_quincena_2=dia_2,
    )


def _datos_perfil(**extra: str) -> dict[str, str]:
    """Arma el formulario de perfil quincenal con porcentajes válidos.

    Args:
        **extra: Campos adicionales que sobrescriben o completan el formulario.

    Returns:
        Diccionario de campos para el POST.
    """
    datos = {
        "alias": "Esteban",
        "sueldo_basico": "3.000.000",
        "modalidad_pago": "QUINCENAL",
        "porcentaje_quincena_1": "50",
        "porcentaje_quincena_2": "50",
        "quincena_deducciones": "1",
    }
    datos.update(extra)
    return datos


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("5", 5), ("05", 5), (" 20 ", 20), ("31", 31), (15, 15)],
)
def test_parsear_dia_acepta_numeros_validos(valor, esperado) -> None:
    """Un día entre 1 y 31, con o sin cero a la izquierda, es válido."""
    assert perfiles.parsear_dia_quincena(valor, "El día") == esperado


@pytest.mark.parametrize("valor", ["", "   ", "5.5", "5,0", "cinco", "0", "32", "123", "-1"])
def test_parsear_dia_rechaza_texto_y_fuera_de_rango(valor) -> None:
    """Letras, símbolos, decimales y días inexistentes se rechazan con ValueError."""
    with pytest.raises(ValueError):
        perfiles.parsear_dia_quincena(valor, "El día")


def test_el_dia_vacio_pide_que_sea_obligatorio() -> None:
    """Un campo vacío indica que el dato es obligatorio, no un error técnico."""
    with pytest.raises(ValueError, match="obligatorio"):
        perfiles.parsear_dia_quincena("", "El día de la quincena 1")


def test_la_quincena_2_debe_ser_posterior_a_la_1() -> None:
    """Días iguales o en orden invertido se rechazan para no duplicar fechas."""
    assert perfiles.validar_dias_quincena("5", "20") == (5, 20)
    with pytest.raises(ValueError, match="posterior"):
        perfiles.validar_dias_quincena("20", "5")
    with pytest.raises(ValueError, match="posterior"):
        perfiles.validar_dias_quincena("15", "15")


def test_etiquetas_usan_los_dias_del_perfil(bd) -> None:
    """Los rótulos de metas y deducciones muestran el día que escribió el usuario."""
    perfil = _perfil_quincenal(bd, "5", "20")

    assert perfiles.etiquetas_quincena(perfil) == {
        1: "Quincena 1 · día 5",
        2: "Quincena 2 · día 20",
    }


def test_sin_perfil_las_etiquetas_usan_15_y_30() -> None:
    """Sin perfil se mantienen los días predeterminados de la app."""
    assert perfiles.etiquetas_quincena(None) == {
        1: "Quincena 1 · día 15",
        2: "Quincena 2 · día 30",
    }


def test_guardar_quincenal_sin_dias_usa_15_y_30(bd) -> None:
    """Un guardado de servicio sin días conserva los valores predeterminados."""
    perfil = perfiles.guardar_perfil(bd, _id_admin(bd), "3000000", "QUINCENAL", "50", "50", 1)

    assert (perfil.dia_quincena_1, perfil.dia_quincena_2) == (15, 30)


def test_cambiar_a_mensual_conserva_los_dias(bd) -> None:
    """Pasar a mensual no borra los días; si vuelve a quincenal, reaparecen."""
    _perfil_quincenal(bd, "5", "20")

    perfil = perfiles.guardar_perfil(bd, _id_admin(bd), "3000000", "MENSUAL")

    assert (perfil.dia_quincena_1, perfil.dia_quincena_2) == (5, 20)


def test_el_resumen_de_quincenas_usa_los_dias_del_perfil(bd) -> None:
    """El panel de Mis Finanzas muestra el día configurado en su etiqueta."""
    perfil = _perfil_quincenal(bd, "5", "20")

    resumen = quincenas.resumen_quincenas(bd, _id_admin(bd), perfil, 2026, 11)

    etiquetas = [fila.etiqueta for fila in resumen]
    assert etiquetas == ["Quincena 1 · día 5", "Quincena 2 · día 20"]


def test_vista_perfil_guarda_los_dias(bd, cliente_admin: TestClient) -> None:
    """El formulario guarda los días escritos y vuelve al tablero."""
    respuesta = cliente_admin.post(
        "/perfil",
        data=_datos_perfil(dia_quincena_1="5", dia_quincena_2="20"),
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    perfil = perfiles.obtener_perfil(bd, _id_admin(bd))
    assert (perfil.dia_quincena_1, perfil.dia_quincena_2) == (5, 20)


def test_vista_perfil_pide_los_dias_si_faltan(cliente_admin: TestClient) -> None:
    """Sin días, el perfil quincenal no se guarda y pide el dato."""
    respuesta = cliente_admin.post("/perfil", data=_datos_perfil(), follow_redirects=False)

    assert respuesta.status_code == 400
    assert "El día de la quincena 1 es obligatorio" in respuesta.text


def test_vista_perfil_responde_400_ante_letras(cliente_admin: TestClient) -> None:
    """Letras en el día devuelven un mensaje amable, no un error interno."""
    respuesta = cliente_admin.post(
        "/perfil",
        data=_datos_perfil(dia_quincena_1="cinco", dia_quincena_2="20"),
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert "debe ser un día del mes entre 1 y 31" in respuesta.text


def test_vista_perfil_rechaza_quincena_2_anterior(cliente_admin: TestClient) -> None:
    """La quincena 2 debe caer después de la 1."""
    respuesta = cliente_admin.post(
        "/perfil",
        data=_datos_perfil(dia_quincena_1="20", dia_quincena_2="5"),
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert "posterior" in respuesta.text


def test_formulario_de_perfil_trae_los_campos_de_dia(bd, cliente_admin: TestClient) -> None:
    """La vista de perfil ofrece los dos días y sus rótulos se actualizan en vivo."""
    _perfil_quincenal(bd, "5", "20")

    html = cliente_admin.get("/perfil").text

    assert 'name="dia_quincena_1"' in html
    assert 'name="dia_quincena_2"' in html
    assert 'data-dia-quincena="1"' in html
    assert "Quincena 1 (día 5)" in html
    assert "Quincena 2 (día 20)" in html


def test_presupuesto_muestra_los_dias_configurados(bd, cliente_admin: TestClient) -> None:
    """Metas y deducciones fijas muestran los días del usuario, no 15 y 30."""
    _perfil_quincenal(bd, "5", "20")

    html = " ".join(cliente_admin.get("/presupuesto").text.split())

    assert "Quincena 1 · día 5" in html
    assert "Quincena 2 · día 20" in html
    assert "Quincena 1 · día 15" not in html


def test_gastos_muestra_los_dias_configurados(bd, cliente_admin: TestClient) -> None:
    """El registro de gastos usa las mismas etiquetas que el resto de la app."""
    _perfil_quincenal(bd, "5", "20")

    html = " ".join(cliente_admin.get("/gastos").text.split())

    assert "Quincena 1 · día 5" in html
    assert "Quincena 2 · día 20" in html
    assert "día 15" not in html
