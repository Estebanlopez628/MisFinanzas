"""Pruebas de la SRS v2.0, Fase C (nuevas vistas, textos y gráfica).

Cubre el panel de tres bloques, la fila inferior de Inicio, el centro de ayuda,
el modal legal compartido con el login y la tarjeta administrativa con contador.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.servicios import comercial, feedback, usuarios

RUTA_APP = Path(__file__).resolve().parent.parent / "app"


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


def _id_usuario(bd) -> str:
    """Devuelve el identificador de la cuenta estándar sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador de `usuario@finanzas.co`.
    """
    cuenta = usuarios.buscar_por_correo(bd, "usuario@finanzas.co")
    assert cuenta is not None
    return cuenta.id_usuario


def test_balance_tres_bloques_formulas_y_colores() -> None:
    """Los tres bloques usan las fórmulas y los colores de la SRS."""
    resumen = {
        "cartera_clientes": Decimal("500000"),
        "deuda_proveedor": Decimal("100000"),
        "abonos_clientes": Decimal("800000"),
        "abonos_proveedor": Decimal("300000"),
    }
    datos = comercial.balance_tres_bloques(resumen)

    assert [barra["etiqueta"] for barra in datos["bloque_a"]] == [
        "Por cobrar a clientes",
        "Por pagar a proveedores",
        "Saldo neto de cartera",
    ]
    assert datos["bloque_a"][0]["color"] == "#3B82F6"
    assert datos["bloque_a"][2]["texto"] == "$400.000"
    assert datos["bloque_a"][2]["nota"] == "Resultado de lo que te deben menos lo que debes"
    assert [barra["etiqueta"] for barra in datos["bloque_b"]] == [
        "Dinero neto en caja (Entradas - Salidas)",
        "Disponible real (Caja - Deudas)",
    ]
    assert datos["bloque_c"]["texto"] == "+$900.000"
    assert "Has recaudado el 100%" not in datos["mensaje"]


def test_balance_tres_bloques_déficit_apunta_a_la_izquierda() -> None:
    """Un saldo negativo va a la izquierda y se pinta obligatoriamente en rojo."""
    resumen = {
        "cartera_clientes": Decimal("0"),
        "deuda_proveedor": Decimal("500000"),
        "abonos_clientes": Decimal("0"),
        "abonos_proveedor": Decimal("300000"),
    }
    datos = comercial.balance_tres_bloques(resumen)

    caja = datos["bloque_b"][0]
    assert caja["texto"] == "−$300.000"
    assert caja["color"] == "#EF4444"
    assert caja["direccion"] == "izquierda"
    assert datos["bloque_c"]["texto"] == "−$800.000"
    assert datos["bloque_c"]["color"] == "#EF4444"
    assert "Has recaudado el 100% de tus ventas" in datos["mensaje"]


def test_vista_cartera_muestra_los_tres_bloques(cliente_admin: TestClient) -> None:
    """La tarjeta reemplaza al antiguo panel de barras de balance."""
    html = cliente_admin.get("/olb-byte/cartera").text
    # SRS v3.0, punto 10: títulos actualizados del panel de tres bloques.
    assert "Estado de cartera" in html
    assert "Análisis de lo que tienes en la calle y tu dinero en caja." in html
    assert "CUENTAS POR COBRAR Y PAGAR" in html
    assert "FLUJO DE CAJA DISPONIBLE" in html
    assert "RESULTADO FINAL ESPERADO" in html
    assert "Ganancia final proyectada" in html
    assert "balance-bloque--final" in html


def test_inicio_usuario_muestra_ayuda_e_invitar_no_tarjeta_admin(
    cliente_usuario: TestClient,
) -> None:
    """El usuario estándar ve la fila inferior y nunca la tarjeta admin."""
    html = cliente_usuario.get("/").text
    assert "Ayuda y comentarios" in html
    assert "Invitar amigos" in html
    assert "data-invitar-amigos" in html
    assert "Comentarios y Reportes" not in html
    # La marca global vive en el <head>; lo que no debe aparecer es la tarjeta
    # del módulo privado en la rejilla.
    assert ">OLB BYTE</h3>" not in html


def test_inicio_admin_ve_tarjeta_con_contador_y_no_fila_de_ayuda(
    bd, cliente_admin: TestClient
) -> None:
    """La tarjeta administrativa queda junto a Trabajos Extras con su badge."""
    from app.dependencias import UsuarioSesion

    usuario = UsuarioSesion(
        id_usuario=_id_usuario(bd),
        correo="usuario@finanzas.co",
        alias="Usuario",
        rol="USER_FINANZAS",
    )
    feedback.crear_reporte(bd, usuario, "ERROR", "Fallo en la dona", "Finanzas")

    html = cliente_admin.get("/").text
    assert "Comentarios y Reportes" in html
    assert "data-contador-comentarios" in html
    assert ">1</span>" in html
    # El bloque inferior es exclusivo de USER_FINANZAS.
    assert "data-invitar-amigos" not in html


def test_orden_de_tarjetas_admin() -> None:
    """«Comentarios y Reportes» se sitúa justo después de Trabajos Extras."""
    from app.routers.vistas import TARJETAS_DASHBOARD

    claves = [tarjeta["clave"] for tarjeta in TARJETAS_DASHBOARD]
    assert claves.index("comentarios") == claves.index("trabajos-extras") + 1


def test_vista_ayuda_textos_literales_y_sin_modulos_privados(
    cliente_usuario: TestClient,
) -> None:
    """Las guías, el legal y el selector no mencionan OLB_BYTE ni facturación."""
    html = cliente_usuario.get("/ayuda").text
    assert "Mis Finanzas" in html
    assert "MisFinanzas" not in html
    assert "Centro de ayuda" in html
    assert "Obtén ayuda, guías de uso e instalación" in html
    assert "Envía comentarios" in html
    assert "Reporta problemas técnicos o sugerencias" in html
    assert "Condiciones y Política de privacidad" in html
    assert "Licencias y Acerca de" in html
    assert "© 2026 Mis Finanzas" in html
    assert "Base mínima de liquidez de $300.000 COP" in html
    assert "Registro y Detalles de deudas" in html

    inicio = html.find('id="dialogo-centro-ayuda"')
    fin = html.find("</dialog>", inicio)
    centro = html[inicio:fin]
    assert "olb" not in centro.lower()
    assert "factur" not in centro.lower()

    inicio = html.find('id="dialogo-comentarios"')
    fin = html.find("</dialog>", inicio)
    comentarios = html[inicio:fin]
    assert "OLB BYTE" not in comentarios
    assert "OLB_BYTE" not in comentarios
    assert "Facturación" not in comentarios


def test_modal_legal_literal_y_enlace_en_login(cliente: TestClient) -> None:
    """El login abre exactamente el mismo modal legal de la ayuda."""
    html = cliente.get("/login").text
    assert "Al continuar, aceptas nuestras" in html
    assert "Condiciones y Política de privacidad" in html
    assert "CONDICIONES DE USO Y POLÍTICA DE PRIVACIDAD — MISFINANZAS" in html
    assert "Última actualización: Noviembre 2026" in html
    assert "6. Aceptación" in html
    assert "id=\"dialogo-legal\"" in html


def test_panel_admin_cambia_estado_y_bloquea_usuario(
    bd, cliente_admin: TestClient, cliente_usuario: TestClient
) -> None:
    """El administrador ve los reportes y el usuario recibe 403."""
    from app.dependencias import UsuarioSesion

    usuario = UsuarioSesion(
        id_usuario=_id_usuario(bd),
        correo="usuario@finanzas.co",
        alias="Usuario",
        rol="USER_FINANZAS",
    )
    reporte = feedback.crear_reporte(
        bd, usuario, "SUGERENCIA", "Más categorías", "Gastos y presupuestos"
    )

    html = cliente_admin.get("/admin/comentarios").text
    assert "Más categorías" in html
    assert "Gastos y presupuestos" in html
    assert "Sugerencia de nueva función" in html
    assert "Pendiente" in html

    cambio = cliente_admin.post(
        f"/feedback/{reporte.id_feedback}/estado", json={"estado": "Resuelto"}
    )
    assert cambio.json()["pendientes"] == 0
    assert cliente_usuario.get("/admin/comentarios").status_code == 403
