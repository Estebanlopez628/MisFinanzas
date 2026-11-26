"""Login con ondas, orden de campos y vista móvil con detalle de órdenes (SRS v1.8, bloques 4, 5 y 7)."""

from __future__ import annotations

from datetime import datetime

from app.servicios import acceso_google, comercial


def test_login_muestra_los_campos_en_el_orden_pedido(cliente, monkeypatch) -> None:
    """Correo, contraseña, recuperación, ingresar y registrarse van en ese orden."""
    monkeypatch.setattr(acceso_google, "google_activo", lambda: False)
    html = cliente.get("/login").text

    posiciones = [
        html.index("Correo o usuario"),
        html.index('name="contrasena"'),
        html.index("¿Olvidaste tu contraseña?"),
        html.index('boton--primario acceso-nuevo__boton'),
        html.index(">Registrarse</a>"),
    ]
    assert posiciones == sorted(posiciones)
    assert 'data-mostrar-clave="campo-clave"' in html


def test_login_con_google_muestra_el_icono_circular(cliente, monkeypatch) -> None:
    """El botón de Google es circular, con el mismo enlace OAuth de siempre."""
    monkeypatch.setattr(acceso_google, "google_activo", lambda: True)
    html = cliente.get("/login").text

    assert 'href="/login/google"' in html
    assert "boton-google" in html
    assert "O continúa con" in html


def test_olvide_contrasena_responde(cliente) -> None:
    """El enlace de recuperación abre su página de instrucciones."""
    respuesta = cliente.get("/olvide-contrasena")

    assert respuesta.status_code == 200
    assert "Recuperar contraseña" in respuesta.text


def test_ordenes_tienen_lista_movil_y_detalle(cliente_admin, bd) -> None:
    """Cada orden tiene una fila móvil y un detalle que se cierra con «Volver»."""
    fecha = datetime(2026, 11, 10, 15, 0, tzinfo=comercial.ZONA_TIENDA)
    productos = [
        comercial.LineaVenta(
            nombre="Audífonos", categoria="Audio", cantidad=1, precio_unitario="50000", costo_unitario="30000"
        )
    ]
    venta = comercial.registrar_venta(bd, "Ana Pérez", "3001234567", productos, fecha)

    html = cliente_admin.get("/olb-byte").text

    assert 'class="ordenes-moviles"' in html
    assert f'data-abrir-dialogo="orden-{venta.id_venta}"' in html
    assert f'id="orden-{venta.id_venta}"' in html
    # SRS v4.44: el regreso se hace con la X roja uniforme.
    assert 'class="detalle-orden__cerrar" data-cerrar-dialogo' in html
