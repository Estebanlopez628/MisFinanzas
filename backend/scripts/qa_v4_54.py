"""Gate QA: nomenclatura de pestañas y título principal de Analítica en OLB_BYTE."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa_admin@misfinanzas.local"
CLAVE = "QA_Admin_2026!"

PESTANAS = (
    "Registro de ventas",
    "Cuentas por cobrar",
    "Cartera y pagos a proveedores",
    "Soporte y garantías",
    "Analítica comercial",
)

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
    """Verifica las cinco pestañas y el encabezado de Analítica en web y móvil.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho, etiqueta in ((1280, "1280px"), (375, "375px")):
            contexto = navegador.new_context(
                viewport={"width": ancho, "height": 900}, service_workers="block"
            )
            pagina = contexto.new_page()
            pagina.goto(f"{BASE}/login")
            pagina.fill("#campo-correo", CORREO)
            pagina.fill("#campo-clave", CLAVE)
            pagina.locator('form[action="/login"] button[type="submit"]').first.click()
            pagina.wait_for_load_state("networkidle")

            pagina.goto(f"{BASE}/olb-byte/analitica")
            pagina.wait_for_load_state("networkidle")
            enlaces = pagina.locator(".subnav-finanzas__enlace").all_inner_texts()
            comprobar(
                f"{etiqueta}: cinco pestañas con la nomenclatura nueva",
                [texto.strip() for texto in enlaces] == list(PESTANAS),
                " | ".join(texto.strip() for texto in enlaces),
            )
            titulo = pagina.locator(".heroe__titulo").first.inner_text()
            comprobar(
                f"{etiqueta}: encabezado «Gestión de ventas y control»",
                titulo.strip() == "📈 Gestión de ventas y control",
                titulo.strip(),
            )
            comprobar(
                f"{etiqueta}: título del navegador actualizado",
                "Gestión de ventas y control" in pagina.title(),
                pagina.title(),
            )
            contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
