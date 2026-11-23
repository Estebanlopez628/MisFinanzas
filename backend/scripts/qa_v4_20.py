"""Recorrido de QA de la SRS v4.20 en navegador real (Chromium).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_20
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

        # Escritorio: proyección visible y Consejero con la nueva redacción.
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        visible = pagina.locator(".cierre-deuda__proyeccion").is_visible()
        comprobar("proyección visible en web", visible)
        tamano = pagina.locator(".consejero__liquidez").evaluate(
            "(e) => getComputedStyle(e).fontSize"
        )
        comprobar("liquidez 16px en web", tamano == "16px", tamano)

        consejo = " ".join(pagina.locator(".consejero").inner_text().split())
        comprobar("sin '(s)' en cuotas", "cuota(s)" not in consejo)
        comprobar(
            "pluralización correcta",
            "(1 cuota)" in consejo or any(f"({n} cuotas)" in consejo for n in range(2, 13)),
            consejo[:140],
        )
        comprobar("realizando el pago mínimo", "realizando el pago mínimo" in consejo)
        comprobar("deuda que tienes con", "la deuda que tienes con" in consejo)
        comprobar(
            "viñeta 3 exacta",
            "Al cerrar las deudas que te acabo de recomendar (" in consejo
            and ") podrás liberar " in consejo
            and "para tus próximas metas a pagar." in consejo,
        )
        comprobar("solo deudas recomendadas", "todas tus deudas recomendadas" in consejo)
        comprobar("sin plazo de hipoteca", "2040" not in consejo and "127 meses" not in consejo, consejo[:160])

        # Móvil: proyección oculta, banner centrado y cabeceras partidas.
        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "proyección oculta en móvil",
            not pagina.locator(".cierre-deuda__proyeccion").is_visible(),
        )
        alineacion = pagina.locator(".cierre-deuda__pill").evaluate(
            "(e) => getComputedStyle(e).textAlign"
        )
        comprobar("banner centrado", alineacion == "center", alineacion)
        liquidez_movil = pagina.locator(".consejero__liquidez").evaluate(
            "(e) => getComputedStyle(e).fontSize"
        )
        comprobar("liquidez 14px en móvil", liquidez_movil == "14px", liquidez_movil)

        pagina.goto(f"{BASE}/chancucos")
        pagina.wait_for_load_state("networkidle")
        if pagina.locator(".tabla--atajos").count():
            cabeceras = [
                " ".join(th.inner_text().split())
                for th in pagina.locator(".tabla--atajos thead th").all()
            ]
            comprobar("VALOR A PAGAR en dos líneas", "VALOR A PAGAR" in cabeceras, str(cabeceras))
            comprobar("DÍAS DE PAGO en dos líneas", "DÍAS DE PAGO" in cabeceras, str(cabeceras))
            saltos = pagina.locator(".tabla--atajos thead th br").count()
            comprobar("dos <br /> en cabeceras", saltos == 2, str(saltos))
        else:
            comprobar("tabla de atajos presente", False, "sin atajos QA")

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
