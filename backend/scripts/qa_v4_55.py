"""Gate QA: desglose de la deuda en la leyenda de la dona de cartera."""

from __future__ import annotations

import re

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
    """Verifica el desglose de la deuda en la leyenda, en web y móvil.

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
            pagina.goto(f"{BASE}/olb-byte/cartera")
            pagina.wait_for_load_state("networkidle")

            fila = pagina.locator('li[data-leyenda-etiqueta="Deuda con proveedor"]')
            comprobar(f"{etiqueta}: fila de deuda presente", fila.count() == 1)
            texto_fila = fila.inner_text().replace("\n", " ").strip()
            comprobar(
                f"{etiqueta}: total con valor y porcentaje de la dona",
                "$" in texto_fila and re.search(r"\d+(\.\d+)? %", texto_fila) is not None,
                texto_fila,
            )

            partes = fila.locator(".dona__desglose li")
            comprobar(f"{etiqueta}: dos líneas de desglose", partes.count() == 2)
            textos = [parte.inner_text().strip() for parte in partes.all()]
            comprobar(
                f"{etiqueta}: etiquetas del desglose",
                "Deudas anteriores al sistema" in textos[0]
                and "Deuda de ventas actuales" in textos[1],
                " | ".join(textos),
            )
            comprobar(
                f"{etiqueta}: cada parte con valor y % de la deuda",
                all("$" in texto and "% de la deuda" in texto for texto in textos),
                " | ".join(textos),
            )
            porcentajes = [
                float(valor)
                for texto in textos
                for valor in re.findall(r"(\d+(?:\.\d+)?) % de la deuda", texto)
            ]
            comprobar(
                f"{etiqueta}: los porcentajes suman 100",
                len(porcentajes) == 2 and abs(sum(porcentajes) - 100) <= 0.2,
                str(porcentajes),
            )
            contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
