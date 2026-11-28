"""Pruebas de la SRS de Migración de Cartera, grilla 2 × 2 y corrección de metas.

Cubre los cinco bloques: pestaña nueva con sus dos formularios, impacto en métricas
y CSV, reubicación de las tarjetas de cartera, salto automático a WhatsApp tras
registrar una venta y borrado integral de los gastos de una meta en ambas quincenas.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.modelos import Abono, Gasto, MovimientoProveedor, ProyeccionAhorro, Venta, VentaDetalle
from app.servicios import ahorro, analitica, comercial, pagos_metas, usuarios

RUTA = Path(__file__).resolve().parent.parent / "app"


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


def test_venta_migrada_sin_abono_se_ve_con_saldo_en_productos(bd) -> None:
    """Sin cobro no suma ingresos, pero la deuda aparece identificada en la tabla."""
    venta = comercial.registrar_venta_migrada(
        bd, "Deuda Sin Cobrar", "3008888888", "150000", date(2025, 7, 7)
    )
    fila = next(
        fila for fila in analitica.tabla_ventas(bd, analitica.Filtro(), date(2025, 8, 1))
        if fila["id_cliente"] == venta.id_cliente
    )
    assert fila["origen"] == comercial.ORIGEN_MIGRACION_CARTERA
    assert fila["total_migrado"] == Decimal("0")
    assert fila["ganancia_migrada"] == Decimal("0")
    assert fila["saldo_migrado"] == Decimal("150000")
    assert fila["fecha_compra"] == date(2025, 7, 7)
    julio = analitica.reporte_mensual(bd, 2025)[6]
    assert julio["ventas_migradas"] == 1
    assert julio["pendiente_migrado"] == Decimal("150000")
    assert julio["ingresos_migrados"] == Decimal("0")


def test_total_de_cartera_aparece_en_pendientes(cliente_admin: TestClient, bd) -> None:
    """El total de cuentas por cobrar se muestra en verde junto al buscador."""
    comercial.registrar_venta(
        bd,
        "Cliente Cartera",
        "3004444444",
        [comercial.LineaVenta("Cable", 1, "70000", "20000")],
    )
    html = cliente_admin.get("/olb-byte/pendientes").text
    assert "TOTAL Cuentas por cobrar" in html
    bloque = html.split("cartera-total\">", 1)[1].split("</span>", 1)[0]
    assert "valor-positivo" in bloque
    assert "$70.000" in bloque


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
    assert 'class="heroe__titulo">🧾 Migración de Cartera</h1>' in html
    assert 'class="heroe__titulo form-header-white"' not in html
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


def test_el_boton_guardar_acepta_campos_vacios() -> None:
    """Sin datos, Guardar agrega la fila de saldo global en lugar de no hacer nada."""
    js = (RUTA / "static/js/migracion.js").read_text(encoding="utf-8")
    bloque = js.split("function guardarProducto()", 1)[1].split("var valores", 1)[0]
    assert "Saldo pendiente migrado" in bloque
    assert "yaEsta" in bloque
    assert "Saldo global agregado" in bloque
    assert "return true" in bloque


def test_el_panel_de_producto_de_migracion_es_completo_y_opcional(
    cliente_admin: TestClient,
) -> None:
    """Aparecen cantidad, costo, precio y garantía, sin ser obligatorios."""
    html = cliente_admin.get("/olb-byte/migracion").text
    panel = html.split('data-panel-producto>', 1)[1].split("</fieldset>", 1)[0]
    for campo in (
        "categoria",
        "producto_nombre",
        "cantidad",
        "costo_unitario",
        "precio_unitario",
        "garantia_meses",
    ):
        assert f'data-campo-panel="{campo}"' in panel
    for etiqueta in (
        "Categoría",
        "Nombre del producto",
        "Cantidad",
        "Costo (proveedor)",
        "Precio de venta",
        "Garantía (meses)",
        "Subtotal del producto",
    ):
        assert etiqueta in panel
    assert "required" not in panel
    assert panel.count("(Opcional)") == 6
    assert "(Llenar campos, solo si conoces el dato, si no dejalos vacios)" in panel
    assert "Todos los campos son opcionales" not in html
    assert 'data-estado-panel hidden' in html
    assert "Productos de esta venta (opcional)" not in html
    assert "data-guardar-producto" in panel
    assert "+ Agregar otro producto" in html
    assert 'name="garantia_meses"' in html.split("data-plantilla-producto>", 1)[1]


def test_la_garantia_nace_en_blanco_en_ventas_y_migracion() -> None:
    """Ninguno de los dos paneles precarga meses de garantía."""
    for nombre in ("index.html", "migracion.html"):
        texto = (RUTA / "templates/olb_byte" / nombre).read_text(encoding="utf-8")
        campo = texto.split('data-campo-panel="garantia_meses"', 1)[0]
        inicio = campo.rfind("<input")
        etiqueta = campo[inicio:]
        assert "value=" not in etiqueta
        assert 'placeholder="0"' in etiqueta


def test_producto_migrado_con_garantia_se_almacena(cliente_admin: TestClient, bd) -> None:
    """El detalle opcional viaja a `venta_detalle` con su garantía."""
    respuesta = cliente_admin.post(
        "/olb-byte/migracion/ventas",
        data={
            "cliente_nombre": "Detalle Completo",
            "cliente_telefono": "3201234567",
            "fecha_compra": "2025-05-05",
            "total": "180.000",
            "producto_nombre": ["Audífonos"],
            "categoria": ["Audífonos"],
            "cantidad": ["2"],
            "costo_unitario": ["40.000"],
            "precio_unitario": ["90.000"],
            "garantia_meses": ["6"],
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    detalle = bd.scalar(select(VentaDetalle))
    assert detalle is not None
    assert detalle.cantidad == 2
    assert detalle.costo_unitario == Decimal("40000")
    assert detalle.precio_unitario == Decimal("90000")
    assert detalle.garantia_texto == "6 meses por defectos de fábrica"
    assert detalle.garantia_fecha_fin == date(2025, 11, 5)


def test_subnav_de_olb_va_en_tres_columnas() -> None:
    """Las seis pestañas de OLB BYTE se acomodan en 3 × 2 sin scroll lateral."""
    html = (RUTA / "templates/olb_byte/_subnav.html").read_text(encoding="utf-8")
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    assert 'class="subnav-finanzas subnav-finanzas--olb"' in html
    bloque = css.split(".subnav-finanzas--olb {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in bloque
    assert "overflow-x: visible" in bloque


def test_historial_de_gastos_cabe_en_la_tarjeta() -> None:
    """Fecha, monto y acciones quedan juntos y sin desplazamiento horizontal."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    contenedor = css.split(".tabla-contenedor.historial-gastos-scroll,", 1)[1].split("}", 1)[0]
    assert "overflow-x: hidden" in contenedor
    tabla = css.split(".tabla.historial-gastos-table {", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in tabla
    assert "table-layout: fixed" in tabla
    celdas = css.split(".tabla.historial-gastos-table th,", 1)[1].split("}", 1)[0]
    assert "padding: 6px 8px" in celdas
    acciones = css.split(".tabla.historial-gastos-table .tabla-gastos__acciones {", 1)[1].split("}", 1)[0]
    assert "justify-content: center" in acciones
    cabecera_acciones = css.split(".tabla.historial-gastos-table thead th.col-acciones,", 1)[1].split("}", 1)[0]
    assert "text-align: center" in cabecera_acciones


def test_el_gesto_tactil_se_confina_en_tablas_de_analitica() -> None:
    """Las tablas de dos ejes no encadenan el gesto a la página en móvil."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    js = (RUTA / "static/js/app.js").read_text(encoding="utf-8")
    bloque = css.split("@media (max-width: 767px) {\n  .tabla-contenedor--productos,", 1)[1].split("}", 1)[0]
    assert "touch-action: pan-x pan-y" in bloque
    assert "overscroll-behavior-y: contain" in bloque
    assert "-webkit-overflow-scrolling: touch" in bloque
    assert "contain: paint" in bloque
    assert ".tabla-contenedor--productos, .tabla-contenedor--costos" in js
    assert "evento.preventDefault()" in js
    assert "caja.scrollLeft" in js and "caja.scrollTop" in js
    assert 'objetivo.closest("thead")' in js
    assert "empiezaEnCabecera && !horizontal" in js


def test_fila_de_saldo_no_duplica_el_detalle_al_registrar(cliente_admin: TestClient, bd) -> None:
    """La fila vacía de Guardar no genera una segunda línea de detalle."""
    respuesta = cliente_admin.post(
        "/olb-byte/migracion/ventas",
        data={
            "cliente_nombre": "Saldo Desde Guardar",
            "cliente_telefono": "3001234567",
            "fecha_compra": "2025-06-06",
            "total": "65.000",
            "producto_nombre": ["Saldo pendiente migrado"],
            "categoria": [""],
            "cantidad": ["1"],
            "costo_unitario": ["0"],
            "precio_unitario": ["0"],
            "garantia_meses": ["0"],
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    venta = bd.scalar(select(Venta))
    assert venta is not None and venta.total == Decimal("65000")
    detalles = bd.scalars(select(VentaDetalle)).all()
    assert len(detalles) == 1
    assert detalles[0].producto_nombre == comercial.NOMBRE_SALDO_MIGRADO
    assert detalles[0].precio_unitario == Decimal("0")
    assert detalles[0].subtotal_item == Decimal("65000")
    assert detalles[0].garantia_fecha_fin is None


def test_solo_total_conocido_deja_vacios_cantidad_y_precio(bd) -> None:
    """Sin detalle, no se inventa precio: solo se suma lo cobrado como ganancia."""
    venta = comercial.registrar_venta_migrada(
        bd, "Saldo Global", "3005555555", "180000", date(2025, 2, 3)
    )
    detalle = bd.scalar(select(VentaDetalle))
    assert detalle is not None
    assert detalle.producto_nombre == "Saldo pendiente migrado"
    assert detalle.precio_unitario == Decimal("0")
    assert detalle.subtotal_item == Decimal("180000")

    comercial.registrar_abono(
        bd,
        venta.id_venta,
        "90000",
        fecha_abono=datetime(2025, 3, 5, 12, tzinfo=comercial.ZONA_TIENDA),
    )
    fila = analitica.tabla_ventas(bd, analitica.Filtro(), date(2025, 3, 1))[0]
    assert fila["cantidad_migrada"] == 0
    assert fila["precio_migrado"] == Decimal("0")
    assert fila["total_migrado"] == Decimal("90000")
    assert fila["costo_reconocido_migrado"] == Decimal("0")
    assert fila["ganancia_migrada"] == Decimal("90000")

    febrero = analitica.reporte_mensual(bd, 2025)[1]
    assert febrero["ingresos_migrados"] == Decimal("0")
    marzo = analitica.reporte_mensual(bd, 2025)[2]
    assert marzo["ingresos_migrados"] == Decimal("90000")
    assert marzo["costos_migrados"] == Decimal("0")
    assert marzo["ganancia_migrada"] == Decimal("90000")
    assert marzo["ganancia_neta"] == Decimal("90000")


def test_las_columnas_de_migracion_aparecen_en_tablas_y_csv(bd) -> None:
    """Las cifras migradas van en columnas propias, también en las descargas."""
    encabezados_mes, filas_mes = analitica.tabla_csv(bd, "mensual", analitica.Filtro(), date(2025, 4, 1))
    for titulo in (
        "Ventas - D. migración",
        "Pendiente por pagar - D. migración",
        "Ingresos - D. migración",
        "Costo - D. migración",
        "Ganancia - D. migración",
        "Ganancia total",
    ):
        assert titulo in encabezados_mes
    assert all(len(fila) == len(encabezados_mes) for fila in filas_mes)

    venta = comercial.registrar_venta_migrada(
        bd,
        "Producto Conocido",
        "3009999999",
        "180000",
        date(2025, 1, 10),
        [comercial.LineaVenta("Audífonos", 2, "90000", "20000", garantia_meses=6)],
    )
    comercial.registrar_abono(bd, venta.id_venta, "90000")
    detalle = analitica.tabla_ventas(bd, analitica.Filtro(), date(2026, 4, 1))[0]
    assert detalle["origen"] == comercial.ORIGEN_MIGRACION_CARTERA
    assert detalle["cantidad_migrada"] == 2
    assert detalle["precio_migrado"] == Decimal("90000")
    assert detalle["costo_unitario_migrado"] == Decimal("20000")
    assert "Vencida" in detalle["garantia_migrada"]
    assert detalle["total_migrado"] == Decimal("90000")
    assert detalle["ganancia"] == Decimal("0")
    encabezados, filas = analitica.tabla_csv(bd, "ventas", analitica.Filtro(), date(2026, 4, 1))
    assert "Garantía - D. migración" in encabezados
    assert all(len(fila) == len(encabezados) for fila in filas)


def test_el_ultimo_costo_muestra_cinco_productos_con_scroll() -> None:
    """La tabla de último costo limita a cinco filas visibles y cabecera fija."""
    css = (RUTA / "static/css/estilos.css").read_text(encoding="utf-8")
    html = (RUTA / "templates/olb_byte/analitica.html").read_text(encoding="utf-8")
    bloque = css.split(".tabla-contenedor--costos {", 1)[1].split("}", 1)[0]
    assert "max-height: 252px" in bloque
    assert "overflow-y: auto" in bloque
    assert "tabla-contenedor--costos" in html


def test_limpieza_por_descripcion_retira_gastos_de_metas_borradas(bd) -> None:
    """Los gastos históricos sin vínculo y con prefijo de meta se saneen."""
    id_usuario = _id_admin(bd)
    gato_huerfano = Gasto(
        id_usuario=id_usuario,
        descripcion=ahorro.PREFIJO_META + "Viaje a San Andrés",
        categoria="Otros Gastos Fijos",
        valor=Decimal("100000"),
        es_fijo=True,
        fecha=date.today(),
        quincena=2,
    )
    bd.add(gato_huerfano)
    bd.commit()

    assert ahorro.limpiar_gastos_huerfanos(bd, id_usuario) == 1
    assert bd.get(Gasto, gato_huerfano.id_gasto) is None


def test_limpieza_por_descripcion_conserva_las_metas_activas(bd) -> None:
    """Un gasto con prefijo se conserva si su meta sigue activa."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Viaje a San Andrés",
        "100.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses="2",
        fecha_inicio=date.today(),
        quincena=2,
    )
    gasto = Gasto(
        id_usuario=id_usuario,
        descripcion=ahorro.PREFIJO_META + meta.descripcion,
        categoria="Otros Gastos Fijos",
        valor=Decimal("100000"),
        es_fijo=True,
        fecha=date.today(),
        quincena=2,
    )
    bd.add(gasto)
    bd.commit()

    assert ahorro.limpiar_gastos_huerfanos(bd, id_usuario) == 0
    assert bd.get(Gasto, gasto.id_gasto) is not None


def test_eliminar_meta_archivada_tambien_limpia_sus_gastos(bd) -> None:
    """Una meta archivada deja de generar gastos en ninguna quincena."""
    id_usuario = _id_admin(bd)
    meta = ahorro.crear_proyeccion(
        bd,
        id_usuario,
        "Ahorro",
        "Meta archivada vieja",
        "100.000",
        tipo_duracion=ahorro.DURACION_LIMITADA,
        meses="2",
        fecha_inicio=date.today(),
        quincena=ahorro.QUINCENA_AMBAS,
    )
    pagos_metas.asegurar_gastos_de_metas(bd, id_usuario, date.today().year, date.today().month)
    meta.activo = False
    meta.archivada_en = date.today()
    bd.commit()

    assert ahorro.limpiar_gastos_huerfanos(bd, id_usuario) == 4
    assert (
        len(bd.scalars(select(Gasto).where(Gasto.id_proyeccion == meta.id_proyeccion)).all()) == 0
    )


def test_migracion_no_infla_reportes_hasta_el_recaudo(bd) -> None:
    """Los reportes mensual/anual solo reconocen lo cobrado de una venta migrada."""
    sin_costo = comercial.registrar_venta_migrada(
        bd, "Historial Global", "3001111111", "100000", date(2025, 3, 10)
    )
    con_costo = comercial.registrar_venta_migrada(
        bd,
        "Historial Detallado",
        "3002222222",
        "200000",
        date(2025, 3, 11),
        [comercial.LineaVenta("Producto", 1, "200000", "50000")],
    )
    antes = analitica.reporte_mensual(bd, 2025)[2]
    assert antes["ventas"] == 0 and antes["ingresos"] == Decimal("0") and antes["ganancia"] == Decimal("0")
    assert antes["ventas_migradas"] == 2
    assert antes["pendiente_migrado"] == Decimal("300000")
    assert antes["ganancia_migrada"] == Decimal("0")

    comercial.registrar_abono(
        bd,
        sin_costo.id_venta,
        "60000",
        fecha_abono=datetime(2025, 4, 5, 12, tzinfo=comercial.ZONA_TIENDA),
    )
    comercial.registrar_abono(
        bd,
        con_costo.id_venta,
        "80000",
        fecha_abono=datetime(2025, 4, 6, 12, tzinfo=comercial.ZONA_TIENDA),
    )
    abril = analitica.reporte_mensual(bd, 2025)[3]
    assert abril["ventas"] == 0 and abril["ingresos"] == Decimal("0")
    assert abril["ventas_migradas"] == 2
    assert analitica.reporte_mensual(bd, 2025)[2]["pendiente_migrado"] == Decimal("160000")
    assert abril["ingresos_migrados"] == Decimal("140000")
    assert abril["costos_migrados"] == Decimal("20000")
    assert abril["ganancia_migrada"] == Decimal("120000")
    assert abril["ganancia_neta"] == Decimal("120000")
    anual = analitica.reporte_anual(bd)[0]
    assert anual["ingresos_totales"] == Decimal("140000")
    assert anual["ganancia_total"] == Decimal("120000")


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
