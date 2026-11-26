"""Gate QA: X uniforme y deudas a proveedores en Analítica (SRS v4.44)."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.servicios import comercial

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
                color_cartera == color_pendientes == "rgba(127, 29, 29, 0.94)",
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
