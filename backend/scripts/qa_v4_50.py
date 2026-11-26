"""Gate QA: X uniforme y deudas a proveedores en Analítica (SRS v4.44)."""

from __future__ import annotations

from datetime import date

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.servicios import analitica, comercial

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

            bloque = pagina.locator("section:has(#titulo-deudas-proveedor)")
            comprobar(f"{prefijo}: bloque de deudas a proveedores", bloque.count() == 1)
            metricas = ["Mes a mes", "Ganancia neta", "Gastos operativos", "Año tras año"]
            html = pagina.content()
            comprobar(
                f"{prefijo}: métricas existentes intactas",
                all(texto in html for texto in metricas),
            )

            with FabricaSesiones() as bd:
                antes = comercial.deuda_proveedor(bd)
            formulario = pagina.locator('form[action$="/analitica/deudas-proveedor"]')
            formulario.locator('input[name="proveedor"]').fill("Proveedor QA Analítica")
            formulario.locator('input[name="monto"]').fill("45000")
            formulario.locator('button[type="submit"]').click()
            pagina.wait_for_load_state("networkidle")
            comprobar(
                f"{prefijo}: aviso de deuda registrada",
                pagina.locator(".alerta--exito:has-text('Deuda con proveedor registrada')").count() == 1,
            )
            with FabricaSesiones() as bd:
                despues = comercial.deuda_proveedor(bd)
            comprobar(
                f"{prefijo}: deuda persistida en el libro",
                despues == antes + 45000,
                f"{antes} -> {despues}",
            )
            comprobar(
                f"{prefijo}: el concepto aparece en el historial",
                "Proveedor QA Analítica" in pagina.content(),
            )

            # Las deudas aparecen como columna propia en Mes a mes y Año tras año.
            cabeceras = [
                texto.strip().title()
                for texto in pagina.locator(".panel--tabla thead th").all_inner_texts()
            ]
            comprobar(
                f"{prefijo}: columna de deudas en ambas tablas",
                cabeceras.count("Deudas Proveedor") >= 2,
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
                deuda_tabla = int("".join(c for c in celdas[5] if c.isdigit()) or "0")
                with FabricaSesiones() as bd:
                    deuda_bd = analitica._deudas_proveedor_por_mes(bd, date.today().year)[
                        date.today().month
                    ]
                comprobar(
                    f"{prefijo}: deuda del mes reflejada en la tabla",
                    deuda_tabla == int(deuda_bd),
                    f"tabla={deuda_tabla} bd={deuda_bd}",
                )

            for tabla in ("mensual", "anual"):
                csv_respuesta = contexto.request.get(
                    f"{BASE}/olb-byte/analitica/exportar/{tabla}.csv"
                )
                cuerpo = csv_respuesta.body()
                comprobar(
                    f"{prefijo}: CSV {tabla} con etiqueta exacta, BOM y tildes",
                    analitica.DEUDAS_PROVEEDOR_LABEL.encode("utf-8") in cuerpo
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

            # Comparar la X de órdenes con la de cartera y la de pendientes.
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
