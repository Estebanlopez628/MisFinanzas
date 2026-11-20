"""Pruebas de endurecimiento HTTP (bloque C y D).

Cubren las cabeceras de seguridad, la protección CSRF por origen, el límite de
intentos de login, los recursos PWA, la publicidad por rol y la administración
de cuentas.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.config import ConfiguracionApp
from app.core.limitador import limitador_login
from app.core.seguridad import crear_token
from app.dependencias import NOMBRE_COOKIE
from app.main import crear_aplicacion
from app.servicios import perfiles, usuarios

CUENTA_ADMIN = {"correo": "admin@olbbyte.co", "contrasena": "Admin123*"}


def _crear_cuenta(bd, rol: str = "USER_FINANZAS"):
    """Crea una cuenta desechable con correo único y perfil configurado.

    El perfil se siembra porque, desde el SRS v1.2, cualquier ruta de negocio
    exige el onboarding completo; estas pruebas ejercitan seguridad HTTP, no el
    flujo de bienvenida.

    Args:
        bd: Sesión de base de datos.
        rol: Rol inicial de la cuenta.

    Returns:
        El usuario persistido.
    """
    correo = f"http-{uuid.uuid4().hex[:8]}@ejemplo.com"
    cuenta = usuarios.crear_usuario(bd, correo, "ClaveSegura123", "Cuenta HTTP", rol)
    perfiles.guardar_perfil(
        bd,
        cuenta.id_usuario,
        "2.960.000",
        perfiles.MODALIDAD_QUINCENAL,
        "50",
        "50",
        perfiles.QUINCENA_PRIMERA,
    )
    return cuenta


def test_cabeceras_de_seguridad_en_todas_las_respuestas(cliente: TestClient) -> None:
    """La respuesta incluye CSP, nosniff, frame y políticas de referencia."""
    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert respuesta.headers["x-frame-options"] == "DENY"
    assert respuesta.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = respuesta.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp


def test_post_con_origen_ajeno_se_bloquea(cliente: TestClient) -> None:
    """Un formulario enviado desde otro dominio se rechaza con 403."""
    respuesta = cliente.post(
        "/login",
        data={"correo": "nadie@ejemplo.com", "contrasena": "x"},
        headers={"Origin": "https://malicioso.example"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 403
    assert "Origen no permitido" in respuesta.text
    # El rechazo tampoco debe viajar sin cabeceras de endurecimiento.
    assert respuesta.headers["x-frame-options"] == "DENY"
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in respuesta.headers["content-security-policy"]


def test_post_con_sec_fetch_cross_site_se_bloquea(cliente: TestClient) -> None:
    """Sin cabecera `Origin`, la marca cross-site del navegador basta para 403."""
    respuesta = cliente.post(
        "/login",
        data={"correo": "nadie@ejemplo.com", "contrasena": "x"},
        headers={"Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 403


def test_post_con_origen_propio_se_permite(cliente: TestClient) -> None:
    """El origen del propio sitio no se bloquea."""
    respuesta = cliente.post(
        "/login",
        data=CUENTA_ADMIN,
        headers={"Origin": "http://testserver"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/"


def test_get_con_origen_ajeno_no_se_bloquea(cliente: TestClient) -> None:
    """Las lecturas no necesitan la comprobación de origen."""
    respuesta = cliente.get("/login", headers={"Origin": "https://malicioso.example"})

    assert respuesta.status_code == 200


def test_login_bloquea_tras_cinco_fallos(cliente: TestClient) -> None:
    """La ventana deslizante responde 429 después del máximo de fallos."""
    limitador_login.reiniciar()
    correo = f"bruta-{uuid.uuid4().hex[:8]}@ejemplo.com"

    try:
        for _ in range(5):
            respuesta = cliente.post(
                "/login",
                data={"correo": correo, "contrasena": "incorrecta"},
                follow_redirects=False,
            )
            assert respuesta.status_code == 401

        bloqueada = cliente.post(
            "/login",
            data={"correo": correo, "contrasena": "incorrecta"},
            follow_redirects=False,
        )
        assert bloqueada.status_code == 429
        assert "Demasiados intentos" in bloqueada.text

        # Incluso con la contraseña correcta la cuenta queda retenida hasta que
        # expire la ventana: la protección es por IP + correo, no por intento.
        retenida = cliente.post(
            "/login",
            data={"correo": correo, "contrasena": "Cualquiera123"},
            follow_redirects=False,
        )
        assert retenida.status_code == 429
    finally:
        limitador_login.reiniciar()


def test_login_correcto_limpia_los_fallos(cliente: TestClient) -> None:
    """Autenticarse bien reinicia el contador de esa clave."""
    limitador_login.reiniciar()
    try:
        for _ in range(3):
            cliente.post(
                "/login",
                data={"correo": CUENTA_ADMIN["correo"], "contrasena": "incorrecta"},
                follow_redirects=False,
            )

        assert (
            cliente.post(
                "/login", data=CUENTA_ADMIN, follow_redirects=False
            ).status_code
            == 303
        )

        # Tras el acceso correcto se permiten de nuevo intentos fallidos.
        otra_vez = cliente.post(
            "/login",
            data={"correo": CUENTA_ADMIN["correo"], "contrasena": "incorrecta"},
            follow_redirects=False,
        )
        assert otra_vez.status_code == 401
    finally:
        limitador_login.reiniciar()


def test_pwa_sirve_manifiesto_service_worker_e_iconos(cliente: TestClient) -> None:
    """Los recursos necesarios para instalar la PWA están disponibles."""
    manifiesto = cliente.get("/manifest.webmanifest")
    assert manifiesto.status_code == 200
    assert "application/manifest+json" in manifiesto.headers["content-type"]
    assert '"short_name"' in manifiesto.text
    assert '"/estaticos/img/icono-192.svg"' in manifiesto.text

    trabajador = cliente.get("/sw.js")
    assert trabajador.status_code == 200
    assert "javascript" in trabajador.headers["content-type"]
    assert "/estaticos/" in trabajador.text

    icono = cliente.get("/estaticos/img/icono-192.svg")
    assert icono.status_code == 200
    assert "svg" in icono.headers["content-type"]

    favicon = cliente.get("/favicon.ico", follow_redirects=False)
    assert favicon.status_code == 301
    assert favicon.headers["location"] == "/estaticos/img/favicon.svg"


def test_publicidad_visible_solo_para_el_rol_publico(
    cliente_usuario: TestClient, cliente_admin: TestClient
) -> None:
    """El espacio publicitario nunca aparece en la sesión del administrador."""
    publico = cliente_usuario.get("/").text
    administrador = cliente_admin.get("/").text

    assert "apoyo-cafe" in publico
    assert "banner-publicidad" not in publico
    assert "apoyo-cafe" not in administrador


def test_documentacion_disponible_fuera_de_produccion(cliente: TestClient) -> None:
    """En pruebas y desarrollo `/docs` se mantiene accesible."""
    assert cliente.get("/docs").status_code == 200


def test_configuracion_de_produccion_exige_clave_y_cierra_docs(
    monkeypatch,
) -> None:
    """En producción la clave corta es un error y la documentación se apaga."""
    monkeypatch.setenv("ENTORNO", "produccion")
    monkeypatch.setenv("CLAVE_SECRETA", "corta")
    configuracion = ConfiguracionApp()

    assert configuracion.es_produccion is True
    assert configuracion.cookie_segura is True
    assert configuracion.documentacion_habilitada is False

    try:
        configuracion.validar_para_produccion()
    except RuntimeError as error:
        assert "CLAVE_SECRETA" in str(error)
    else:  # pragma: no cover - protección contra regresiones
        raise AssertionError("Se esperaba RuntimeError por clave insegura")


def test_cookie_segura_con_variable_de_entorno(
    cliente: TestClient, monkeypatch
) -> None:
    """`COOKIE_SEGURA=1` permite probar el despliegue HTTPS en local."""
    monkeypatch.setenv("COOKIE_SEGURA", "1")

    respuesta = cliente.post("/login", data=CUENTA_ADMIN, follow_redirects=False)

    assert respuesta.status_code == 303
    assert "secure" in respuesta.headers["set-cookie"].lower()


def test_aplicacion_en_produccion_cierra_docs(monkeypatch) -> None:
    """La fábrica de aplicación respeta `documentacion_habilitada`."""
    import app.main as modulo_main
    from app.core.config import ConfiguracionApp

    produccion = ConfiguracionApp(entorno="produccion", clave_secreta="x" * 40)
    monkeypatch.setattr(modulo_main, "obtener_configuracion", lambda: produccion)

    aplicacion = modulo_main.crear_aplicacion()
    cliente = TestClient(aplicacion)

    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/salud").status_code == 200


def test_administracion_solo_para_administradores(
    cliente_usuario: TestClient,
) -> None:
    """Un usuario público recibe 403 en el listado y en las acciones."""
    assert cliente_usuario.get("/admin/usuarios").status_code == 403
    assert (
        cliente_usuario.post(
            "/admin/usuarios/cualquiera/rol", data={"rol": "ADMIN_OLB"}
        ).status_code
        == 403
    )


def test_administrador_lista_cuentas(cliente_admin: TestClient) -> None:
    """El listado muestra las cuentas sembradas y las acciones disponibles."""
    respuesta = cliente_admin.get("/admin/usuarios")

    assert respuesta.status_code == 200
    assert "admin@olbbyte.co" in respuesta.text
    assert "usuario@finanzas.co" in respuesta.text


def test_administrador_no_cambia_su_propio_rol(
    cliente_admin: TestClient, bd
) -> None:
    """La autorrebaja de privilegios se bloquea en el servidor."""
    admin = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert admin is not None

    respuesta = cliente_admin.post(
        f"/admin/usuarios/{admin.id_usuario}/rol",
        data={"rol": usuarios.ROL_USUARIO},
    )

    assert respuesta.status_code == 400
    assert "propio rol" in respuesta.text
    assert usuarios.obtener_por_id(bd, admin.id_usuario).rol == usuarios.ROL_ADMIN


def test_administrador_cambia_rol_de_otra_cuenta(
    cliente_admin: TestClient, bd
) -> None:
    """Un administrador puede promover a otra cuenta."""
    cuenta = _crear_cuenta(bd)

    respuesta = cliente_admin.post(
        f"/admin/usuarios/{cuenta.id_usuario}/rol",
        data={"rol": usuarios.ROL_ADMIN},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    bd.expire_all()
    assert usuarios.obtener_por_id(bd, cuenta.id_usuario).rol == usuarios.ROL_ADMIN


def test_desactivar_cuenta_invalida_sesion_y_login(
    cliente_admin: TestClient, bd
) -> None:
    """Una cuenta desactivada pierde la sesión abierta y no puede autenticarse."""
    cuenta = _crear_cuenta(bd)
    cliente = TestClient(crear_aplicacion())
    cliente.cookies.set(
        NOMBRE_COOKIE, crear_token(cuenta.id_usuario, cuenta.rol, cuenta.alias)
    )
    assert cliente.get("/", follow_redirects=False).status_code == 200

    respuesta = cliente_admin.post(
        f"/admin/usuarios/{cuenta.id_usuario}/estado",
        data={"activo": "0"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303

    perdida = cliente.get("/", follow_redirects=False)
    assert perdida.status_code == 303
    assert perdida.headers["location"].startswith("/login")

    acceso = cliente.post(
        "/login",
        data={"correo": cuenta.correo, "contrasena": "ClaveSegura123"},
        follow_redirects=False,
    )
    assert acceso.status_code == 401


def test_administrador_no_desactiva_su_propia_cuenta(
    cliente_admin: TestClient, bd
) -> None:
    """Evita dejar la plataforma sin administrador activo."""
    admin = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert admin is not None

    respuesta = cliente_admin.post(
        f"/admin/usuarios/{admin.id_usuario}/estado",
        data={"activo": "0"},
    )

    assert respuesta.status_code == 400
    assert "propia cuenta" in respuesta.text
    bd.expire_all()
    assert usuarios.obtener_por_id(bd, admin.id_usuario).activo is True
