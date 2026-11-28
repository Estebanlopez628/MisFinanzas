"""Pruebas de la SRS de Migración de Cartera, grilla 2 × 2 y corrección de metas.

Cubre los cinco bloques: pestaña nueva con sus dos formularios, impacto en métricas
y CSV, reubicación de las tarjetas de cartera, salto automático a WhatsApp tras
registrar una venta y borrado integral de los gastos de una meta en ambas quincenas.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.modelos import Abono, Gasto, MovimientoProveedor, ProyeccionAhorro, Venta, VentaDetalle
from app.servicios import ahorro, comercial, pagos_metas, usuarios


def _id_admin(bd) -> str:
    """Devuelve el identificador de la cuenta de administrador sembrada.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Identificador del administrador.
    """
    cuenta = usuarios.buscar_por_correo(bd, "admin@olbbyte.co")
    assert cuenta is not None
    return cuenta.id_usuario


# ---------------------------------------------------------------------------
# Bloque 2: pestaña de migración
# ---------------------------------------------------------------------------


def test_la_pestana_de_migracion_esta_junto_a_registro_de_ventas(cliente_admin: TestClient) -> None:
    """La subnavegación incluye la pestaña nueva en segundo lugar."""
    html = cliente_admin.get("/olb-byte").text
    pestanas = [
        "Registro de ventas",
        "Migración de Cartera",
        "Cuentas por cobrar",
        "Cartera y pagos a proveedores",
        "Soporte y garantías",
        "Gestión y control de ventas",
    ]
    posiciones = [html.index(nombre) for nombre in pestanas]
    assert posiciones == sorted(posiciones)


def test_la_vista_de_migracion_tiene_los_dos_bloques_con_linea_neon(cliente_admin: TestClient) -> None:
    """Los títulos blancos de los dos bloques usan `.form-header-white`."""
    html = cliente_admin.get("/olb-byte/migracion").text
    for titulo in (
        "Ventas realizadas antes del sistema",
        "Deudas al proveedor anteriores al sistema",
    ):
        assert f'class="panel__titulo form-header-white">{titulo}</h2>' in html
    assert 'class="heroe__titulo form-header-white">🧾 Migración de Cartera</h1>' in html
    assert "name=fecha_compra" not in html
    assert 'name="fecha_compra"' in html
    assert "+ Agregar otro producto" in html
    assert "data-migracion-form" in html
    assert "data-venta-form" not in html


def test_registrar_venta_migrada_sin_productos_va_a_cuentas_por_cobrar(
    cliente_admin: TestClient, bd
) -> None:
    """El saldo global queda pendiente con origen de migración."""
    respuesta = cliente_admin.post(
        "/olb-byte/migracion/ventas",
        data={
            "cliente_nombre": "Cliente Histórico",
            "cliente_telefono": "3001234567",
            "fecha_compra": "2025-08-15",
            "total": "450.000",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    venta = bd.scalar(select(Venta).order_by(Venta.numero_orden.desc()))
    assert venta is not None
    assert venta.origen == comercial.ORIGEN_MIGRACION_CARTERA
    assert venta.fecha_compra == date(2025, 8, 15)
    assert venta.total == Decimal("450000")
    assert venta.saldo_pendiente == Decimal("450000")
    assert venta.estado_pago == comercial.ESTADO_PAGO_PENDIENTE
    assert comercial.deuda_proveedor(bd) == Decimal("0")
    detalles = bd.scalars(select(VentaDetalle)).all()
    assert len(detalles) == 1
    assert detalles[0].producto_nombre == "Saldo pendiente migrado"


def test_registrar_venta_migrada_con_costo_no_crea_deuda_al_proveedor(
    cliente_admin: TestClient, bd
) -> None:
    """El costo se guarda para el reparto, sin inflar el pasivo al migrar."""
    respuesta = cliente_admin.post(
        "/olb-byte/migracion/ventas",
        data={
            "cliente_nombre": "Cliente Detallado",
            "cliente_telefono": "3101234567",
            "fecha_compra": "2025-09-10",
            "total": "200.000",
            "producto_nombre": ["Audífonos"],
            "categoria": ["Audífonos"],
            "cantidad": ["1"],
            "precio_unitario": ["150.000"],
            "costo_unitario": ["60.000"],
            "garantia_meses": ["0"],
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    venta = bd.scalar(select(Venta))
    assert venta is not None
    assert venta.total_costo == Decimal("60000")
    assert len(bd.scalars(select(VentaDetalle)).all()) == 2
    assert comercial.deuda_proveedor(bd) == Decimal("0")


def test_abono_de_venta_migrada_reconoce_utilidad_proporcional(bd) -> None:
    """Con costo, la utilidad es `Abono − Costo proporcional`; sin costo, el 100 %."""
    sin_costo = comercial.registrar_venta_migrada(
        bd, "Global", "3001111111", "100000", date(2025, 1, 5)
    )
    con_costo = comercial.registrar_venta_migrada(
        bd,
        "Detallado",
        "3002222222",
        "200000",
        date(2025, 1, 6),
        [comercial.LineaVenta("Producto", 1, "200000", "50000")],
    )
    comercial.registrar_abono(bd, sin_costo.id_venta, "80000")
    comercial.registrar_abono(bd, con_costo.id_venta, "80000")

    resumen = comercial.resumen_migracion(bd)
    assert resumen["utilidad"] == Decimal("80000") + Decimal("60000")
    assert resumen["pago_proveedor"] == Decimal("20000")
    assert resumen["abonado"] == Decimal("160000")


def test_la_deuda_inicial_acepta_proveedor_fecha_y_referencia(cliente_admin: TestClient, bd) -> None:
    """Los campos opcionales quedan guardados sin alterar el saldo histórico."""
    respuesta = cliente_admin.post(
        "/olb-byte/migracion/deudas-iniciales",
        data={
            "concepto": "Compra de inventario 2024",
            "monto": "300.000",
            "proveedor_nombre": "Distribuidora Central",
            "fecha_deuda": "2024-11-20",
            "referencia_factura": "FC-1182",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    movimiento = bd.scalar(select(MovimientoProveedor))
    assert movimiento is not None
    assert movimiento.tipo == comercial.TIPO_DEUDA_INICIAL
    assert movimiento.proveedor_nombre == "Distribuidora Central"
    assert movimiento.fecha_deuda == date(2024, 11, 20)
    assert movimiento.referencia_factura == "FC-1182"
    assert comercial.deuda_proveedor(bd) == Decimal("300000")


def test_el_csv_de_migracion_incluye_origen_y_fechas(cliente_admin: TestClient, bd) -> None:
    """El CSV propio de la migración conserva las columnas exigidas."""
    venta = comercial.registrar_venta_migrada(
        bd, "Ana Migración", "3001234567", "120000", date(2025, 3, 4)
    )
    comercial.registrar_abono(bd, venta.id_venta, "40000")
    respuesta = cliente_admin.get("/olb-byte/migracion/exportar.csv")

    assert respuesta.status_code == 200
    assert respuesta.text.startswith("\ufeff")
    cabecera = respuesta.text.lstrip("\ufeff").splitlines()[0]
    assert "Origen" in cabecera
    assert "Fecha de compra" in cabecera
    assert "Fecha de recaudo" in cabecera
    assert "Utilidad reconocida" in cabecera
    fila = respuesta.text.lstrip("\ufeff").splitlines()[1]
    assert comercial.ORIGEN_MIGRACION_CARTERA in fila


def test_las_ordenes_migradas_no_ofrecen_factura_ni_whatsapp(cliente_admin: TestClient, bd) -> None:
    """La migración no genera comprobante; el respaldo manual sigue en las normales."""
    migrada = comercial.registrar_venta_migrada(bd, "Vieja", "3001234567", "50000")
    normal = comercial.registrar_venta(
        bd,
        "Nueva",
        "3007654321",
        [comercial.LineaVenta("Cable", 1, "50000", "10000")],
    )
    html = cliente_admin.get("/olb-byte").text
    asserts = html.split(f'id="orden-{migrada.id_venta}"', 1)[1].split("</dialog>", 1)[0]
    assert "Ver factura" not in asserts
    assert "Enviar por WhatsApp" not in asserts
    assert f'id="orden-{normal.id_venta}"' in html
    assert "Enviar por WhatsApp" in html


# ---------------------------------------------------------------------------
# Bloque 3: grilla 2 × 2 en cartera
# ---------------------------------------------------------------------------


def test_la_cartera_tiene_cuatro_paneles_en_dos_filas(cliente_admin: TestClient) -> None:
    """Pago, Movimientos, Gastos e Historial aparecen en ese orden."""
    html = cliente_admin.get("/olb-byte/cartera").text
    titulos = (
        "Pago al proveedor",
        "Movimientos con el proveedor",
        "Gastos operativos",
        "Historial de gastos operativos",
    )
    posiciones = [html.index(titulo) for titulo in titulos]
    assert posiciones == sorted(posiciones)
    assert html.count('class="rejilla-paneles rejilla-paneles--proveedor rejilla-paneles--cartera"') == 2
    for titulo in titulos[2:]:
        fragmento = html.split(f">{titulo}</h2>", 1)[0]
        assert "form-header-white" in fragmento[-80:]


# ---------------------------------------------------------------------------
# Bloque 4: guardado con salto automático a WhatsApp
# ---------------------------------------------------------------------------


def test_el_alta_normal_devuelve_json_con_el_enlace_de_whatsapp(cliente_admin: TestClient) -> None:
    """La respuesta JSON confirma el guardado y entrega el chat del cliente."""
    respuesta = cliente_admin.post(
        "/olb-byte/ventas",
        headers={"X-OLB-AJAX": "1"},
        data={
            "cliente_nombre": "Ana Whats",
            "cliente_telefono": "3001234567",
            "forma_pago": "CONTADO",
            "metodo_pago": "EFECTIVO",
            "producto_nombre": ["Cable"],
            "categoria": ["Cables y adaptadores"],
            "cantidad": ["1"],
            "costo_unitario": ["10000"],
            "precio_unitario": ["30000"],
            "garantia_meses": ["3"],
        },
    )
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["ok"] is True
    assert datos["cliente_telefono"] == "3001234567"
    assert datos["enlace_whatsapp"].startswith("https://wa.me/573001234567")


def test_sin_telefono_valido_no_hay_enlace_automatico(cliente_admin: TestClient) -> None:
    """Se guarda la venta sin abrir un enlace roto."""
    respuesta = cliente_admin.post(
        "/olb-byte/ventas",
        headers={"X-OLB-AJAX": "1"},
        data={
            "cliente_nombre": "Sin celular",
            "cliente_telefono": "123",
            "forma_pago": "CONTADO",
            "metodo_pago": "EFECTIVO",
            "producto_nombre": ["Cable"],
            "categoria": ["Otros"],
            "cantidad": ["1"],
            "costo_unitario": ["0"],
            "precio_unitario": ["20000"],
            "garantia_meses": ["0"],
        },
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["enlace_whatsapp"] == ""


def test_la_recarga_con_wa_auto_solo_inyecta_el_enlace_si_hay_celular(
    cliente_admin: TestClient, bd
) -> None:
    """El salto móvil se prepara en la página de órdenes recién recargada."""
    venta = comercial.registrar_venta(
        bd,
        "Ana Auto",
        "3001234567",
        [comercial.LineaVenta("Cable", 1, "20000", "0")],
    )
    html = cliente_admin.get(
        "/olb-byte", params={"guardado": "1", "wa_auto": venta.id_venta}
    ).text
    assert "data-wa-auto" in html
    assert "https://wa.me/573001234567" in html


# ---------------------------------------------------------------------------
# Bloque 5: borrado integral de metas
# ---------------------------------------------------------------------------


def test_eliminar_meta_borra_las_dos_quincenas_y_limpia_huerfanos(
    cliente_admin: TestClient, bd
) -> None:
    """Ningún gasto fijo de la meta queda activo tras eliminarla."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Meta de ambas quincenas",
        "200.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses="3",
        fecha_inicio=date.today(),
        quincena=ahorro.QUINCENA_AMBAS,
        modo_ambas=ahorro.MODO_DIVIDIR,
    )
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, date.today().year, date.today().month)
    gastos_meta = bd.scalars(
        select(Gasto).where(Gasto.id_proyeccion == meta.id_proyeccion)
    ).all()
    assert len(gastos_meta) == 6
    assert {gasto.quincena for gasto in gastos_meta} == {1, 2}

    respuesta = cliente_admin.post(
        f"/presupuesto/metas/{meta.id_proyeccion}/eliminar", follow_redirects=False
    )
    assert respuesta.status_code == 303
    assert (
        len(bd.scalars(select(Gasto).where(Gasto.id_proyeccion == meta.id_proyeccion)).all()) == 0
    )


def test_limpieza_de_huerfanos_no_toca_gastos_normales(bd) -> None:
    """Los gastos sin meta padre se borran; los normales se conservan."""
    id_usuario = _id_admin(bd)
    # Huérfano histórico: apunta a una meta que ya no existe en la base.
    gasto_huerfano = Gasto(
        id_usuario=id_usuario,
        descripcion="Meta eliminada antes del correctivo",
        categoria="Ahorro",
        valor=Decimal("100000"),
        es_fijo=True,
        fecha=date.today(),
        quincena=2,
        id_proyeccion="metayaeliminada00000000000000000",
    )
    gasto_normal = Gasto(
        id_usuario=id_usuario,
        descripcion="Arriendo",
        categoria="Otros Gastos Fijos",
        valor=Decimal("1000000"),
        es_fijo=True,
        fecha=date.today(),
        quincena=2,
    )
    bd.add(gasto_normal)
    # Se simula un registro huérfano histórico: la llave foránea impide crearlo
    # con el motor actual, así que se inserta con la comprobación desactivada.
    bd.commit()
    bd.execute(text("PRAGMA foreign_keys=OFF"))
    bd.add(gasto_huerfano)
    bd.commit()
    bd.execute(text("PRAGMA foreign_keys=ON"))

    eliminados = ahorro.limpiar_gastos_huerfanos(bd, id_usuario)
    assert eliminados == 1
    assert bd.get(Gasto, gasto_huerfano.id_gasto) is None
    assert bd.get(Gasto, gasto_normal.id_gasto) is not None
    assert bd.scalar(select(ProyeccionAhorro)) is None
    assert bd.scalar(select(Abono)) is None
