"""Gate QA: PASIVO ANTIGUO en Analítica y X uniforme (SRS v4.44, decisión final)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Venta, VentaDetalle
from app.servicios import analitica

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa_admin@misfinanzas.local"
CLAVE = "QA_Admin_2026!"

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado.
        detalle: Información adicional.
    """
    resultados.append((nombre, bool(condicion), detalle))
    print(("PASS " if condicion else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""), flush=True)


def a_pesos(texto: str) -> int:
    """Convierte una celda con formato COP a entero.

    Args:
        texto: Celda con símbolo y separadores.

    Returns:
        Valor numérico sin formato.
    """
    return int("".join(c for c in texto if c.isdigit()) or "0")


def main() -> None:
    """Recorre Analítica y comprueba la X uniforme en 1280 y 375 px.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
            contexto = navegador.new_context(
                viewport={"width": ancho, "height": 900}, service_workers="block"
            )
            pagina = contexto.new_page()
            prefijo = f"{ancho}px"
            pagina.goto(f"{BASE}/login")
            pagina.fill("#campo-correo", CORREO)
            pagina.fill("#campo-clave", CLAVE)
            pagina.locator('form[action="/login"] button[type="submit"]').first.click()
            pagina.wait_for_load_state("networkidle")
            pagina.goto(f"{BASE}/olb-byte/analitica")
            pagina.wait_for_load_state("networkidle")

            borde = pagina.evaluate(
                "() => getComputedStyle(document.querySelector('.formulario--filtros-analitica')).borderTopWidth"
            )
            comprobar(f"{prefijo}: sin línea sobre Año", borde == "0px", borde)

            html = pagina.content()
            comprobar(
                f"{prefijo}: sin módulo de registro en Analítica",
                "Deudas con proveedores" not in html
                and 'name="proveedor"' not in html
                and "/analitica/deudas-proveedor" not in html,
            )
            metricas = ["Mes a mes", "Ganancia neta", "Gastos operativos", "Año tras año"]
            comprobar(
                f"{prefijo}: métricas existentes intactas",
                all(texto in html for texto in metricas),
            )

            cabeceras = [
                texto.strip().title()
                for texto in pagina.locator(".panel--tabla thead th").all_inner_texts()
            ]
            comprobar(
                f"{prefijo}: columna PASIVO ANTIGUO en ambas tablas",
                cabeceras.count("Pasivo Antiguo") >= 2,
                str(cabeceras[:12]),
            )

            meses = (
                "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
            )
            fila_mes = pagina.locator(
                f".panel--tabla tbody tr:has-text('{meses[date.today().month - 1]}')"
            ).first
            if fila_mes.count():
                celdas = [c.strip() for c in fila_mes.locator("td").all_inner_texts()]
                with FabricaSesiones() as bd:
                    anio, mes = date.today().year, date.today().month
                    ids = [
                        venta.id_venta
                        for venta in bd.query(Venta).all()
                        if venta.estado_orden == "ACTIVA"
                        and venta.fecha_venta.year == anio
                        and venta.fecha_venta.month == mes
                    ]
                    costo = sum(
                        (
                            detalle.costo_unitario * detalle.cantidad
                            for detalle in bd.query(VentaDetalle).all()
                            if detalle.id_venta in ids
                        ),
                        Decimal("0"),
                    )
                    saldos = analitica._saldos_pasivo_antiguo(bd)
                    pasivo = analitica._pasivo_antiguo_en(saldos, anio, mes)
                comprobar(
                    f"{prefijo}: Costos sin deuda y PASIVO ANTIGUO aparte",
                    a_pesos(celdas[3]) == int(costo) and a_pesos(celdas[5]) == int(pasivo),
                    f"costos={celdas[3]} esperado={costo} pasivo={celdas[5]} esperado={pasivo}",
                )

            # KPI del panel: pasivo antiguo y ganancia global con la fórmula dada.
            pagina.goto(
                f"{BASE}/olb-byte/analitica?anio={date.today().year}&mes={date.today().month}"
            )
            pagina.wait_for_load_state("networkidle")
            tarjetas = pagina.locator(".panel--kpis .kpi").all()
            etiquetas = [t.locator(".kpi__etiqueta").inner_text() for t in tarjetas]
            valores = [a_pesos(t.locator(".kpi__valor").inner_text()) for t in tarjetas]
            comprobar(
                f"{prefijo}: KPI de Pasivo antiguo y Ganancia global",
                any("Pasivo antiguo" in e for e in etiquetas)
                and any("Ganancia global" in e for e in etiquetas),
                str(etiquetas),
            )
            with FabricaSesiones() as bd:
                anio, mes = date.today().year, date.today().month
                ids = [
                    venta.id_venta
                    for venta in bd.query(Venta).all()
                    if venta.estado_orden == "ACTIVA"
                    and venta.fecha_venta.year == anio
                    and venta.fecha_venta.month == mes
                ]
                costo_mes = sum(
                    (
                        detalle.costo_unitario * detalle.cantidad
                        for detalle in bd.query(VentaDetalle).all()
                        if detalle.id_venta in ids
                    ),
                    Decimal("0"),
                )
            comprobar(
                f"{prefijo}: Ganancia global = Pasivo + Costos − Neta",
                len(valores) >= 4 and valores[3] == valores[2] + int(costo_mes) - valores[1],
                f"pasivo={valores[2]} costos={costo_mes} neta={valores[1]} global={valores[3]}",
            )

            for tabla in ("mensual", "anual"):
                csv_respuesta = contexto.request.get(
                    f"{BASE}/olb-byte/analitica/exportar/{tabla}.csv"
                )
                cuerpo = csv_respuesta.body()
                comprobar(
                    f"{prefijo}: CSV {tabla} con PASIVO ANTIGUO, BOM y tildes",
                    analitica.PASIVO_ANTIGUO_LABEL.encode("utf-8") in cuerpo
                    and cuerpo.startswith(b"\xef\xbb\xbf")
                    and "Variación".encode("utf-8") in cuerpo,
                )

            pagina.goto(f"{BASE}/olb-byte")
            pagina.wait_for_load_state("networkidle")
            comprobar(
                f"{prefijo}: órdenes sin «Volver a todas las órdenes» y con X",
                "Volver a todas las órdenes" not in pagina.content()
                and pagina.locator("dialog.detalle-orden .detalle-orden__cerrar").count() > 0,
            )

            pagina.goto(f"{BASE}/olb-byte/cartera")
            pagina.wait_for_load_state("networkidle")
            color_cartera = pagina.locator(".detalle-orden__cerrar").first.evaluate(
                "e => getComputedStyle(e).backgroundColor"
            )
            pagina.goto(f"{BASE}/olb-byte/pendientes")
            pagina.wait_for_load_state("networkidle")
            color_pendientes = pagina.locator(".pendiente-cerrar").first.evaluate(
                "e => getComputedStyle(e).backgroundColor"
            )
            comprobar(
                f"{prefijo}: X de cartera y pendientes del mismo color",
                color_cartera == color_pendientes == "rgba(239, 68, 68, 0.14)",
                f"{color_cartera} / {color_pendientes}",
            )
            if ancho < 768:
                pagina.locator("button.orden-movil[data-abrir-dialogo^='pendiente-']").first.click()
                pagina.wait_for_timeout(150)
                color_modal = pagina.locator("dialog.detalle-orden[open] .pendiente-cerrar").evaluate(
                    "e => getComputedStyle(e).backgroundColor"
                )
                comprobar(
                    f"{prefijo}: X del modal abierta del mismo color",
                    color_modal == color_cartera,
                    color_modal,
                )
            contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
