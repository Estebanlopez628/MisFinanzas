"""Recorrido de QA de la SRS v4.17 en navegador real (Chromium).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_17
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado de la comprobación.
        detalle: Información extra.
    """
    resultados.append((nombre, bool(condicion), detalle))


def main() -> None:
    """Ejecuta el recorrido completo.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        contexto = navegador.new_context(
            viewport={"width": 1280, "height": 900}, service_workers="block"
        )
        errores: list[str] = []
        contexto.on(
            "page",
            lambda p: p.on(
                "console", lambda m: errores.append(m.text) if m.type == "error" else None
            ),
        )
        pagina = contexto.new_page()
        pagina.goto(f"{BASE}/login")
        pagina.fill("#campo-correo", CORREO)
        pagina.fill("#campo-clave", CLAVE)
        pagina.locator('form[action="/login"] button[type="submit"]').first.click()
        pagina.wait_for_load_state("networkidle")
        comprobar("login QA", "/login" not in pagina.url, pagina.url)

        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")

        comprobar(
            "dos velocímetros cockpit",
            pagina.locator(".mf-cockpit-dial").count() == 2
            and pagina.locator('[data-variant="minimo"]').count() == 1
            and pagina.locator('[data-variant="excedente"]').count() == 1,
        )
        marcas = pagina.locator(".mf-dial-ticks").first.evaluate("(e) => e.childElementCount")
        comprobar("41 micro-marcas", marcas == 41, str(marcas))

        svg_base = pagina.locator('[data-variant="minimo"] .mf-cockpit-dial')
        tamano = svg_base.evaluate(
            "(e) => [getComputedStyle(e).width, getComputedStyle(e).height]"
        )
        comprobar("tamaño escritorio 156x88", tamano == ["156px", "88px"], str(tamano))
        trazo = pagina.locator('[data-variant="minimo"] .mf-dial-progress').evaluate(
            "(e) => getComputedStyle(e).stroke"
        )
        brillo = pagina.locator('[data-variant="minimo"] .mf-dial-progress').evaluate(
            "(e) => getComputedStyle(e).filter"
        )
        comprobar("resplandor azul", "mfArcBlue" in trazo and "mfGlowBlue" in brillo, f"{trazo} | {brillo}")
        trazo_verde = pagina.locator('[data-variant="excedente"] .mf-dial-progress').evaluate(
            "(e) => getComputedStyle(e).stroke"
        )
        comprobar("resplandor esmeralda", "mfArcGreen" in trazo_verde, trazo_verde)

        texto_base = " ".join(
            pagina.locator('[data-variant="minimo"] .mf-gauge-meta').inner_text().split()
        )
        texto_opt = " ".join(
            pagina.locator('[data-variant="excedente"] .mf-gauge-meta').inner_text().split()
        )
        comprobar(
            "texto Pago mínimo",
            "Pago mínimo" in texto_base and "En " in texto_base and "Sin abono extra" in texto_base,
            texto_base,
        )
        comprobar(
            "texto Con excedente",
            "Con excedente" in texto_opt and "En " in texto_opt and "Abonando +" in texto_opt,
            texto_opt,
        )
        comprobar(
            "píldora meses antes",
            "meses antes" in pagina.locator(".mf-gauge-badge").inner_text(),
        )

        # No regresión de módulos blindados.
        comprobar("dona global intacta", "dona__desglose" in pagina.content())
        pagina.goto(f"{BASE}/finanzas")
        comprobar("tarjetas compactas intactas", "Sueldo devengado" in pagina.content())

        # Móvil: misma distribución y tamaños vigentes.
        pagina.set_viewport_size({"width": 390, "height": 844})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        tamano_movil = pagina.locator(".mf-cockpit-dial").first.evaluate(
            "(e) => [getComputedStyle(e).width, getComputedStyle(e).height]"
        )
        comprobar("tamaño móvil 120x68", tamano_movil == ["120px", "68px"], str(tamano_movil))
        medida = pagina.evaluate(
            "() => [window.innerWidth, document.documentElement.scrollWidth]"
        )
        comprobar("sin desborde móvil", medida[1] <= medida[0], f"{medida[1]}/{medida[0]}")

        comprobar("sin errores de consola", not errores, "; ".join(errores[:3]))
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    for nombre, ok, detalle in resultados:
        print(("PASS " if ok else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""))
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones en verde")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
