"""Gate QA: volver a «Órdenes registradas» conservando scroll y diálogo (SRS v4.44)."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

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


def iniciar(pagina) -> None:
    """Inicia sesión con la cuenta QA de administración.

    Args:
        pagina: Página de Playwright.

    Returns:
        None.
    """
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", CORREO)
    pagina.fill("#campo-clave", CLAVE)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")


def main() -> None:
    """Recorre ida y vuelta a la factura en escritorio y móvil.

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
            iniciar(pagina)
            pagina.goto(f"{BASE}/olb-byte")
            pagina.wait_for_load_state("networkidle")

            dialogo_abierto = False
            if ancho < 768:
                # En móvil las acciones viven dentro del diálogo de la orden.
                pagina.locator('button.orden-movil[data-abrir-dialogo^="orden-"]').first.click()
                pagina.wait_for_timeout(200)
                dialogo_abierto = pagina.locator("dialog.detalle-orden[open]").count() == 1
                comprobar(f"{prefijo}: diálogo de orden abierto", dialogo_abierto)

            # Posición intermedia conocida, fija para ida y vuelta.
            pagina.evaluate("window.scrollTo({ top: 1400, behavior: 'instant' })")
            pagina.wait_for_timeout(250)
            antes = pagina.evaluate("window.scrollY")
            comprobar(f"{prefijo}: posición inicial mayor que cero", antes > 0, str(antes))

            enlace = pagina.locator("a[data-volver-ventas]:visible").first
            enlace.click()
            pagina.wait_for_load_state("networkidle")
            comprobar(
                f"{prefijo}: se abre la factura",
                "/olb-byte/factura/" in pagina.url,
                pagina.url,
            )

            volver = pagina.locator(".volver-ventas-factura")
            comprobar(
                f"{prefijo}: «Volver a Ventas» visible en la factura",
                volver.is_visible(),
            )
            comprobar(
                f"{prefijo}: sin X en la factura",
                pagina.locator(".factura-cerrar").count() == 0,
            )
            volver.click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(700)
            despues = pagina.evaluate("window.scrollY")
            comprobar(
                f"{prefijo}: vuelve a la misma posición",
                abs(despues - antes) <= 6,
                f"{antes} -> {despues}",
            )
            if dialogo_abierto:
                comprobar(
                    f"{prefijo}: se reabre el diálogo de la orden",
                    pagina.locator("dialog.detalle-orden[open]").count() == 1,
                )
            comprobar(
                f"{prefijo}: claves de retorno consumidas",
                pagina.evaluate(
                    "() => sessionStorage.getItem('misfinanzas_olb_ventas_scroll_y') === null"
                ),
            )

            # El botón de WhatsApp comparte el guardado (sin abrir el chat).
            pagina.evaluate(
                """() => {
              var boton = document.querySelector('[data-compartir-factura]');
              if (!boton) return;
              boton.addEventListener('click', function (evento) {
                evento.stopImmediatePropagation();
                evento.preventDefault();
              }, true);
              boton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            }"""
            )
            comprobar(
                f"{prefijo}: WhatsApp guarda la posición",
                pagina.evaluate(
                    "() => Number(sessionStorage.getItem('misfinanzas_olb_ventas_scroll_y')) > 0"
                ),
            )

            contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
