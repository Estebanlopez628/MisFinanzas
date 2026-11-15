"""Pruebas de trabajos extras y referencias de pago (bloque B)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.servicios import chancucos, trabajos, usuarios


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


def test_trabajo_extra_cambia_de_estado(bd) -> None:
    """El trabajo nace PENDIENTE y se puede marcar COBRADO."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(
        bd, id_usuario, "Diseño de logo", "500.000", date(2026, 11, 10), "ACME"
    )
    assert trabajo.estado == "PENDIENTE"
    assert trabajo.valor == Decimal("500000.00")

    trabajo = trabajos.cambiar_estado(bd, id_usuario, trabajo.id_trabajo, "cobrado")
    assert trabajo.estado == "COBRADO"


def test_resumen_trabajos_separa_cobrado_y_pendiente(bd) -> None:
    """Los totales se agrupan por estado."""
    id_usuario = _id_admin(bd)
    primero = trabajos.crear_trabajo(bd, id_usuario, "Uno", "100000", date(2026, 11, 1))
    trabajos.crear_trabajo(bd, id_usuario, "Dos", "250000", date(2026, 11, 2))
    trabajos.cambiar_estado(bd, id_usuario, primero.id_trabajo, "COBRADO")

    resumen = trabajos.resumen_trabajos(bd, id_usuario)
    assert resumen["cobrado"] == Decimal("100000.00")
    assert resumen["pendiente"] == Decimal("250000.00")
    assert resumen["cobrados"] == 1
    assert resumen["pendientes"] == 1


def test_trabajo_rechaza_estado_invalido(bd) -> None:
    """Un estado fuera del catálogo se rechaza."""
    id_usuario = _id_admin(bd)
    trabajo = trabajos.crear_trabajo(bd, id_usuario, "Uno", "100000", date(2026, 11, 1))

    try:
        trabajos.cambiar_estado(bd, id_usuario, trabajo.id_trabajo, "PERDIDO")
    except ValueError as error:
        assert "PENDIENTE" in str(error)
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_vista_trabajos_registra(cliente_admin: TestClient) -> None:
    """El formulario de trabajos responde y lista el registro."""
    respuesta = cliente_admin.post(
        "/trabajos-extras",
        data={
            "descripcion": "Asesoría",
            "cliente": "Cliente X",
            "valor": "300.000",
            "fecha": "2026-11-12",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    html = cliente_admin.get("/trabajos-extras").text
    assert "Asesoría" in html
    assert "300.000" in html


def test_chancuco_valida_url_y_favorito(bd) -> None:
    """La URL debe ser HTTP(S) y el favorito se alterna."""
    id_usuario = _id_admin(bd)
    chancuco = chancucos.crear_chancuco(
        bd,
        id_usuario,
        "EPM energía",
        "123456",
        "https://epm.com.co/pagos",
        favorito=True,
    )
    assert chancuco.favorito is True
    assert chancucos.listar_chancucos(bd, id_usuario)[0].descripcion == "EPM energía"

    chancuco = chancucos.alternar_favorito(bd, id_usuario, chancuco.id_chancuco)
    assert chancuco is not None and chancuco.favorito is False


def test_chancuco_rechaza_url_peligrosa(bd) -> None:
    """Solo se admiten enlaces http o https."""
    try:
        chancucos.crear_chancuco(
            bd, _id_admin(bd), "EPM energía", "123", "javascript:alert(1)"
        )
    except ValueError as error:
        assert "http" in str(error).lower()
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba ValueError")


def test_chancuco_ajeno_no_se_elimina(bd) -> None:
    """La eliminación valida el dueño del registro."""
    id_usuario = _id_admin(bd)
    chancuco = chancucos.crear_chancuco(bd, id_usuario, "EPM energía", "123")

    assert chancucos.eliminar_chancuco(bd, "otro", chancuco.id_chancuco) is False
    assert chancucos.eliminar_chancuco(bd, id_usuario, chancuco.id_chancuco) is True


def test_vista_chancucos_registra(cliente_admin: TestClient) -> None:
    """El panel guarda y muestra el atajo con su botón Pagar."""
    respuesta = cliente_admin.post(
        "/chancucos",
        data={
            "descripcion": "Claro internet",
            "numero_referencia": "998877",
            "url_pago": "https://claro.com.co",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    html = cliente_admin.get("/chancucos").text
    assert "Claro internet" in html
    assert "998877" in html
    assert "https://claro.com.co" in html


def test_subnavegacion_marca_atajos_en_su_pestana(cliente_admin: TestClient) -> None:
    """La pestaña Configurar Atajos de Pago queda activa en su propia vista."""
    html = cliente_admin.get("/chancucos").text

    assert "Configurar Atajos de Pago" in html
    assert html.count('aria-current="page"') == 1
    # El título del hero repite la etiqueta, así que la comparación se hace
    # dentro del bloque de subnavegación para no confundir ambas apariciones.
    inicio_subnav = html.index("subnav-finanzas")
    posicion_activo = html.index("subnav-finanzas__enlace--activo", inicio_subnav)
    posicion_etiqueta = html.index("Configurar Atajos de Pago", inicio_subnav)
    assert posicion_activo < posicion_etiqueta
