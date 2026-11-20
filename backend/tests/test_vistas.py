"""Pruebas de humo de las vistas y del control de acceso por rol.

Verifican que el tablero responde, que el RBAC se aplica **en el servidor**, que
la navegación superior quedó reducida a tres opciones (SRS v1.2) y que un
visitante anónimo es enviado al login.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

# Tarjetas y enlaces esperados tras la limpieza del bloque 2.
TARJETAS_ADMIN = ("Mis Finanzas", "OLB_BYTE", "Resumen de Deudas", "Trabajos Extras")
TARJETAS_PUBLICAS = ("Mis Finanzas", "Resumen de Deudas", "Trabajos Extras")


def test_dashboard_responde_para_administrador(cliente_admin: TestClient) -> None:
    """El tablero del administrador muestra las cuatro tarjetas principales."""
    respuesta = cliente_admin.get("/")

    assert respuesta.status_code == 200
    for titulo in TARJETAS_ADMIN:
        assert f">{titulo}</h3>" in respuesta.text
    # Los submódulos ya no son tarjetas externas.
    assert "Gastos y presupuesto" not in respuesta.text
    assert "Accesos exclusivos" not in respuesta.text
    # El administrador no ve publicidad.
    assert "Espacio reservado para anuncios" not in respuesta.text


def test_dashboard_oculta_modulos_privados_al_usuario_publico(
    cliente_usuario: TestClient,
) -> None:
    """Un USER_FINANZAS no recibe la tarjeta de OLB_BYTE ni los módulos privados."""
    respuesta = cliente_usuario.get("/")

    assert respuesta.status_code == 200
    for titulo in TARJETAS_PUBLICAS:
        assert f">{titulo}</h3>" in respuesta.text
    assert ">OLB_BYTE</h3>" not in respuesta.text
    assert ">Chancucos</h3>" not in respuesta.text
    assert "Invítame un café" in respuesta.text


def test_navegacion_superior_solo_tiene_tres_opciones(
    cliente_admin: TestClient,
) -> None:
    """El header quedó limitado a Inicio, Mi Perfil y Salir."""
    respuesta = cliente_admin.get("/")

    assert respuesta.status_code == 200
    assert ">Inicio<" in respuesta.text
    assert ">Mi Perfil<" in respuesta.text
    assert ">Salir<" in respuesta.text
    # Enlaces retirados del header.
    for etiqueta in (">Gastos<", ">Historial<", ">Incapacidades<", ">Deudas<", ">Usuarios<"):
        assert etiqueta not in respuesta.text


def test_navegacion_marca_la_opcion_activa(cliente_admin: TestClient) -> None:
    """Inicio se resalta en el dashboard y Mi Perfil en su propia vista."""
    inicio = cliente_admin.get("/")
    assert 'aria-current="page">Inicio</a>' in inicio.text
    assert 'aria-current="page">Mi Perfil</a>' not in inicio.text

    perfil = cliente_admin.get("/perfil")
    assert 'aria-current="page">Mi Perfil</a>' in perfil.text
    assert 'aria-current="page">Inicio</a>' not in perfil.text


def test_subnavegacion_de_finanzas_tiene_las_cuatro_pestanas(
    cliente_admin: TestClient,
) -> None:
    """Las pestañas internas de Mis Finanzas siguen el orden del SRS v1.3."""
    respuesta = cliente_admin.get("/finanzas")

    assert respuesta.status_code == 200
    for etiqueta in (
        "Resumen / Liquidación",
        "Gastos y Presupuesto",
        "Configurar Atajos de Pago",
        "Historial de Registros",
    ):
        assert etiqueta in respuesta.text
    assert ">Incapacidades</a>" not in respuesta.text
    # Solo la pestaña activa recibe el estado y el atributo de accesibilidad.
    assert respuesta.text.count('aria-current="page"') == 1
    assert "subnav-finanzas__enlace--activo" in respuesta.text
    posicion_activo = respuesta.text.index("subnav-finanzas__enlace--activo")
    posicion_resumen = respuesta.text.index("Resumen / Liquidación")
    assert posicion_activo < posicion_resumen


def test_dashboard_redirige_al_login_sin_sesion(cliente: TestClient) -> None:
    """Sin cookie de sesión el tablero no se renderiza: se redirige al login."""
    respuesta = cliente.get("/", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"


def test_visitante_puede_ver_el_login(cliente: TestClient) -> None:
    """La pantalla de acceso es pública y muestra el formulario real."""
    respuesta = cliente.get("/login")

    assert respuesta.status_code == 200
    assert 'name="correo"' in respuesta.text
    assert 'name="contrasena"' in respuesta.text
    assert 'action="/login"' in respuesta.text


def test_vista_mis_finanzas_expone_parametros_legales(cliente_usuario: TestClient) -> None:
    """La vista de finanzas debe mostrar la base de 210 horas y el tope de 2 SMMLV."""
    respuesta = cliente_usuario.get("/finanzas")

    assert respuesta.status_code == 200
    assert "210" in respuesta.text
    assert "3.501.810" in respuesta.text
    assert 'data-calculadora' in respuesta.text


def test_endpoint_de_salud(cliente: TestClient) -> None:
    """El endpoint de salud debe responder JSON con estado ok, sin sesión."""
    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"
