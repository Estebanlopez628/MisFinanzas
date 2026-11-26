"""Gate QA: seis productos en Analítica y cinco órdenes en Ventas."""

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
    """Verifica límites de filas y cabeceras opacas.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        contexto = navegador.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        pagina = contexto.new_page()
        pagina.goto(f"{BASE}/login")
        pagina.fill("#campo-correo", CORREO)
        pagina.fill("#campo-clave", CLAVE)
        pagina.locator('form[action="/login"] button[type="submit"]').first.click()
        pagina.wait_for_load_state("networkidle")

        for ruta, selector, tope_esperado, etiqueta in (
            ("/olb-byte/analitica", ".tabla-contenedor--productos", "294px", "seis productos"),
            ("/olb-byte", ".tabla-contenedor--ordenes", "252px", "cinco órdenes"),
        ):
            pagina.goto(f"{BASE}{ruta}")
            pagina.wait_for_load_state("networkidle")
            caja = pagina.locator(selector)
            comprobar(f"{ruta}: tabla presente", caja.count() == 1)
            tope = caja.evaluate("e => getComputedStyle(e).maxHeight")
            fondo = caja.locator("thead th").first.evaluate("e => getComputedStyle(e).backgroundColor")
            comprobar(
                f"{ruta}: {etiqueta} con scroll vertical",
                tope == tope_esperado,
                f"max-height={tope}",
            )
            comprobar(
                f"{ruta}: cabecera opaca",
                fondo == "rgb(15, 23, 42)",
                fondo,
            )
        contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
