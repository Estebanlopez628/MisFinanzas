"""Gate QA: buscador sin línea y modal de pendientes con X rojiza (SRS v4.44)."""

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


def main() -> None:
    """Recorre pendientes en escritorio y móvil.

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
            pagina.goto(f"{BASE}/olb-byte/pendientes")
            pagina.wait_for_load_state("networkidle")

            borde = pagina.evaluate(
                "() => getComputedStyle(document.querySelector('.formulario--buscar')).borderTopWidth"
            )
            comprobar(
                f"{prefijo}: sin línea sobre el buscador",
                borde == "0px",
                borde,
            )

            if ancho < 768:
                pagina.evaluate("window.scrollTo({ top: 700, behavior: 'instant' })")
                pagina.wait_for_timeout(200)
                antes = pagina.evaluate("window.scrollY")
                pagina.locator("button.orden-movil[data-abrir-dialogo^='pendiente-']").first.click()
                pagina.wait_for_timeout(200)
                dialogo = pagina.locator("dialog.detalle-orden[open]").first
                comprobar(f"{prefijo}: modal de cliente abierto", dialogo.count() == 1)
                comprobar(
                    f"{prefijo}: solo queda «Registrar Pago»",
                    dialogo.locator('a:has-text("Registrar Pago")').count() == 1
                    and dialogo.locator('button:has-text("Volver a pendientes")').count() == 0,
                )
                x = dialogo.locator(".pendiente-cerrar")
                estilo = x.evaluate(
                    "e => ({ fondo: getComputedStyle(e).backgroundColor, texto: getComputedStyle(e).color })"
                )
                caja = x.bounding_box()
                dialogo_caja = dialogo.bounding_box()
                comprobar(
                    f"{prefijo}: X rojisa arriba a la derecha",
                    estilo["fondo"] == "rgba(239, 68, 68, 0.14)"
                    and estilo["texto"] == "rgb(254, 202, 202)"
                    and caja["x"] > dialogo_caja["x"] + dialogo_caja["width"] * 0.7
                    and caja["y"] < dialogo_caja["y"] + 60,
                    str(estilo),
                )
                x.click()
                pagina.wait_for_timeout(200)
                comprobar(
                    f"{prefijo}: la X cierra el modal",
                    pagina.locator("dialog.detalle-orden[open]").count() == 0,
                )
                despues = pagina.evaluate("window.scrollY")
                comprobar(
                    f"{prefijo}: vuelve a la misma posición",
                    abs(despues - antes) <= 4,
                    f"{antes} -> {despues}",
                )
            contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
