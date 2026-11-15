"""Pruebas del onboarding salarial y del perfil financiero (bloque 1, SRS v1.2).

Cubren la validación de porcentajes por quincena, el cálculo desde el neto sin
deducciones, el guardado desde la vista y la redirección obligatoria al perfil
cuando el usuario todavía no se ha configurado.
"""

from __future__ import annotations

import re
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.modelos import PerfilFinanciero
from app.servicios import perfiles, usuarios


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta administradora sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de la cuenta `admin@olbbyte.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


def _eliminar_perfil(bd, id_usuario: str) -> None:
    """Simula un usuario nuevo borrando su perfil financiero.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño del perfil a eliminar.
    """
    bd.execute(delete(PerfilFinanciero).where(PerfilFinanciero.id_usuario == id_usuario))
    bd.commit()


def test_guardar_perfil_mensual(bd) -> None:
    """El perfil mensual no guarda porcentajes quincenales."""
    perfil = perfiles.guardar_perfil(bd, _id_admin(bd), "2.960.000", "MENSUAL")

    assert perfil.sueldo_basico == Decimal("2960000.00")
    assert perfil.modalidad_pago == "MENSUAL"
    assert perfil.porcentaje_quincena_1 is None
    assert perfil.porcentaje_quincena_2 is None
    assert perfil.quincena_deducciones is None
    assert perfil.auxilio_transporte_habilitado is True


def test_guardar_perfil_actualiza_sin_duplicar(bd) -> None:
    """Guardar dos veces actualiza la misma fila 1:1."""
    id_usuario = _id_admin(bd)
    perfiles.guardar_perfil(bd, id_usuario, "2000000", "MENSUAL")
    perfiles.guardar_perfil(bd, id_usuario, "3000000", "MENSUAL")

    total = bd.scalar(
        select(func.count())
        .select_from(PerfilFinanciero)
        .where(PerfilFinanciero.id_usuario == id_usuario)
    )
    assert total == 1
    assert perfiles.obtener_perfil(bd, id_usuario).sueldo_basico == Decimal("3000000.00")


def test_perfil_quincenal_prorratea_el_sueldo(bd) -> None:
    """Con 50 % por quincena el sueldo del periodo es la mitad."""
    perfil = perfiles.guardar_perfil(bd, _id_admin(bd), "2960000", "QUINCENAL", "50")

    assert perfil.porcentaje_quincena_2 == Decimal("50.00")
    assert perfil.quincena_deducciones == 1
    assert perfiles.sueldo_del_periodo(perfil, 1) == Decimal("1480000.00")
    assert perfiles.sueldo_del_periodo(perfil, 2) == Decimal("1480000.00")
    assert perfiles.sueldo_del_periodo(perfil, 0) == Decimal("2960000.00")


def test_porcentajes_distintos_por_quincena(bd) -> None:
    """Cada quincena usa su propio porcentaje (40 % / 60 %)."""
    perfil = perfiles.guardar_perfil(
        bd, _id_admin(bd), "3.000.000", "QUINCENAL", "40", "60", 2
    )

    assert perfil.porcentaje_quincena_1 == Decimal("40.00")
    assert perfil.porcentaje_quincena_2 == Decimal("60.00")
    assert perfil.quincena_deducciones == 2
    assert perfiles.sueldo_del_periodo(perfil, 1) == Decimal("1200000.00")
    assert perfiles.sueldo_del_periodo(perfil, 2) == Decimal("1800000.00")


def test_modalidad_quincenal_exige_porcentaje(bd) -> None:
    """Sin porcentaje la modalidad quincenal es inválida."""
    try:
        perfiles.guardar_perfil(bd, _id_admin(bd), "2960000", "QUINCENAL", None)
    except ValueError as error:
        assert "porcentaje" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_porcentajes_deben_sumar_cien(bd) -> None:
    """Una suma distinta de 100 % se rechaza con un mensaje claro."""
    try:
        perfiles.guardar_perfil(
            bd, _id_admin(bd), "3.000.000", "QUINCENAL", "40", "50", 1
        )
    except ValueError as error:
        assert "sumar 100" in str(error)
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError por suma de porcentajes")


def test_calcular_quincenas_desde_neto_sin_deducciones(bd) -> None:
    """El neto de la quincena sin descuentos deriva ambos porcentajes."""
    primero, segundo, deducciones = perfiles.calcular_quincenas_desde_neto(
        "3.000.000", "1.200.000", 1
    )

    assert primero == Decimal("40.00")
    assert segundo == Decimal("60.00")
    assert deducciones == 2

    perfil = perfiles.guardar_perfil(
        bd, _id_admin(bd), "3.000.000", "QUINCENAL", primero, segundo, deducciones
    )
    assert perfiles.sueldo_del_periodo(perfil, 1) == Decimal("1200000.00")
    assert perfiles.sueldo_del_periodo(perfil, 2) == Decimal("1800000.00")


def test_calcular_desde_neto_valida_el_rango(bd) -> None:
    """El neto debe ser positivo y menor que el sueldo mensual."""
    for neto in ("0", "3.000.000", "4.000.000"):
        try:
            perfiles.calcular_quincenas_desde_neto("3.000.000", neto, 1)
        except ValueError as error:
            assert "neto" in str(error).lower()
        else:  # pragma: no cover - protección contra regresiones
            raise AssertionError(f"Se esperaba ValueError para el neto {neto}")


def test_vista_perfil_guarda_porcentajes(bd, cliente_admin: TestClient) -> None:
    """El POST guarda ambos porcentajes y vuelve al tablero."""
    respuesta = cliente_admin.post(
        "/perfil",
        data={
            "alias": "Esteban",
            "sueldo_basico": "2.960.000",
            "modalidad_pago": "QUINCENAL",
            "porcentaje_quincena_1": "40",
            "porcentaje_quincena_2": "60",
            "quincena_deducciones": "2",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/?guardado=1"
    perfil = perfiles.obtener_perfil(bd, _id_admin(bd))
    assert perfil is not None
    assert perfil.sueldo_basico == Decimal("2960000.00")
    assert perfil.porcentaje_quincena_1 == Decimal("40.00")
    assert perfil.porcentaje_quincena_2 == Decimal("60.00")
    assert perfil.quincena_deducciones == 2


def test_vista_perfil_calcula_desde_neto(bd, cliente_admin: TestClient) -> None:
    """En el caso B el servidor deriva los porcentajes y la quincena con descuentos."""
    respuesta = cliente_admin.post(
        "/perfil",
        data={
            "alias": "Esteban",
            "sueldo_basico": "3.000.000",
            "modalidad_pago": "QUINCENAL",
            "conoce_porcentajes": "NO",
            "neto_sin_deducciones": "1.800.000",
            "quincena_sin_deducciones": "1",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    perfil = perfiles.obtener_perfil(bd, _id_admin(bd))
    assert perfil.porcentaje_quincena_1 == Decimal("60.00")
    assert perfil.porcentaje_quincena_2 == Decimal("40.00")
    assert perfil.quincena_deducciones == 2


def test_vista_perfil_rechaza_sueldo_invalido(cliente_admin: TestClient) -> None:
    """Un sueldo con letras devuelve 400 sin guardar."""
    respuesta = cliente_admin.post(
        "/perfil",
        data={
            "alias": "Esteban",
            "sueldo_basico": "dos millones",
            "modalidad_pago": "MENSUAL",
        },
    )

    assert respuesta.status_code == 400
    assert "no es un número válido" in respuesta.text


def test_vista_perfil_usa_las_preguntas_del_srs_v13(cliente_admin: TestClient) -> None:
    """El formulario usa los textos aprobados en el SRS v1.3 (bloque 4)."""
    respuesta = cliente_admin.get("/perfil")
    texto = re.sub(r"\s+", " ", respuesta.text)

    assert respuesta.status_code == 200
    assert (
        "¿En qué quincena te realizan todas las deducciones y pago de recargos?"
        in texto
    )
    assert (
        "Escribe el valor neto que recibes en la quincena donde NO te realizan "
        "deducciones de ley ni pago de horas extras."
        in texto
    )
    # Los radios del caso A/B se apilan: un contenedor por opción.
    assert texto.count('class="opcion"') == 2


def test_vista_perfil_oculta_quincenas_en_modalidad_mensual(
    bd, cliente_admin: TestClient
) -> None:
    """Con pago mensual no se muestra la configuración de quincenas."""
    perfiles.guardar_perfil(bd, _id_admin(bd), "2.960.000", "MENSUAL")

    respuesta = cliente_admin.get("/perfil")
    texto = re.sub(r"\s+", " ", respuesta.text)

    assert respuesta.status_code == 200
    assert "data-grupo-quincenal hidden" in texto
    assert "En modalidad mensual recibes todo el sueldo en un solo pago" in texto


def test_vista_perfil_muestra_quincenas_en_modalidad_quincenal(
    cliente_admin: TestClient,
) -> None:
    """Con pago quincenal el bloque de porcentajes queda visible."""
    respuesta = cliente_admin.get("/perfil")
    texto = re.sub(r"\s+", " ", respuesta.text)

    assert "data-grupo-quincenal hidden" not in texto
    assert "data-aviso-mensual hidden" in texto


def test_cambio_de_contrasena_verifica_la_actual(bd, cliente_admin: TestClient) -> None:
    """La contraseña actual incorrecta no permite el cambio."""
    respuesta = cliente_admin.post(
        "/perfil/contrasena",
        data={
            "contrasena_actual": "incorrecta",
            "contrasena_nueva": "NuevaClave123",
            "confirmar_contrasena": "NuevaClave123",
        },
    )

    assert respuesta.status_code == 400
    assert "contraseña actual no es correcta" in respuesta.text.lower()


def test_onboarding_bloquea_los_modulos_sin_perfil(
    bd, cliente_admin: TestClient
) -> None:
    """Sin perfil, el tablero y los módulos redirigen al onboarding."""
    _eliminar_perfil(bd, _id_admin(bd))

    tablero = cliente_admin.get("/", follow_redirects=False)
    assert tablero.status_code == 303
    assert tablero.headers["location"] == "/perfil?bienvenida=1"

    finanzas = cliente_admin.get("/finanzas", follow_redirects=False)
    assert finanzas.status_code == 303
    assert finanzas.headers["location"] == "/perfil?bienvenida=1"

    gastos = cliente_admin.get("/gastos", follow_redirects=False)
    assert gastos.status_code == 303


def test_onboarding_muestra_el_saludo_de_bienvenida(
    bd, cliente_admin: TestClient
) -> None:
    """La vista de perfil saluda al usuario nuevo y ofrece el formulario."""
    _eliminar_perfil(bd, _id_admin(bd))

    respuesta = cliente_admin.get("/perfil?bienvenida=1")

    assert respuesta.status_code == 200
    assert "bienvenido" in respuesta.text.lower()
    assert "Configuración inicial" in respuesta.text
    assert 'name="porcentaje_quincena_1"' in respuesta.text
    assert 'name="neto_sin_deducciones"' in respuesta.text


def test_usuario_registrado_es_enviado_al_onboarding(cliente: TestClient, bd) -> None:
    """Un registro nuevo no entra al tablero hasta configurar su perfil."""
    correo = "nuevo-onboarding@ejemplo.com"
    usuarios.crear_usuario(bd, correo, "ClaveSegura123", "Nuevo", usuarios.ROL_USUARIO)

    ingreso = cliente.post(
        "/login",
        data={"correo": correo, "contrasena": "ClaveSegura123"},
        follow_redirects=True,
    )

    assert ingreso.status_code == 200
    assert ingreso.url.path == "/perfil"
    assert "bienvenido" in ingreso.text.lower()
