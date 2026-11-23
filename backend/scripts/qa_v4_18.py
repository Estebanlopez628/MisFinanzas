"""Recorrido de QA de la SRS v4.18 en navegador real (Chromium).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_18
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

        # Espaciado compacto real.
        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        relleno = pagina.locator(".panel--quincena .lista-parametros--compacta li").first.evaluate(
            "(e) => getComputedStyle(e).paddingTop"
        )
        margen = pagina.locator(".panel--quincena .lista-parametros--compacta li").first.evaluate(
            "(e) => getComputedStyle(e).marginTop"
        )
        comprobar("filas 6px sin margen", relleno == "6px" and margen == "0px", f"{relleno}/{margen}")
        separacion = pagina.locator(".bloque-gastos-quincena").first.evaluate(
            "(e) => getComputedStyle(e).marginTop"
        )
        comprobar("divisoria a 8px", separacion == "8px", separacion)

        # Consejero: redacción y coherencia.
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        consejo = pagina.locator(".consejero").inner_text()
        comprobar("terminología pago mínimo", "pago mínimo" in consejo.lower())
        comprobar("sin frase coloquial", "pagando solo lo mínimo" not in consejo.lower())
        comprobar("sin 'por más tiempo'", "por más tiempo" not in consejo)
        comprobar("plazo de deuda objetivo", "cancelarás esta deuda" in consejo)
        comprobar("alcance de deudas activas", "todas tus deudas activas" in consejo)
        comprobar("alcance del plan", "deudas de tu plan" in consejo)
        sub_verde = pagina.locator('[data-variant="excedente"] .mf-gauge-sub').inner_text()
        comprobar("saldo proyectado en verde", "saldo proyectado" in sub_verde, sub_verde)

        # Gráfica: etiquetas legibles, una sola línea de resumen y mes activo.
        etiqueta = pagina.locator(".cierre-deuda__eje").first.evaluate(
            "(e) => [getComputedStyle(e).fill, getComputedStyle(e).fontSize]"
        )
        comprobar("etiquetas claras", etiqueta[0] == "rgb(226, 232, 240)" and etiqueta[1] == "14px", str(etiqueta))
        comprobar("sin tooltip duplicado", pagina.locator("[data-cierre-tooltip]").count() == 0)
        activos = pagina.locator(".cierre-deuda__mes--activo").count()
        comprobar("un solo mes activo", activos == 1, str(activos))
        ahora = len(pagina.locator(".cierre-deuda__detalle").inner_text())
        pagina.locator(".cierre-deuda__mes").nth(3).click()
        despues = pagina.locator(".cierre-deuda__detalle").inner_text()
        comprobar("detalle se actualiza", ahora > 0 and despues != "" and "Saldo Base:" in despues)

        # Escritorio: diseño y tamaño de velocímetros intactos.
        tamano = pagina.locator(".mf-cockpit-dial").first.evaluate(
            "(e) => [getComputedStyle(e).width, getComputedStyle(e).height]"
        )
        comprobar("web 156x88 intacto", tamano == ["156px", "88px"], str(tamano))
        columnas = pagina.locator(".cierre-deuda__velocimetros").evaluate(
            "(e) => getComputedStyle(e).gridTemplateColumns"
        )
        comprobar("web dos columnas", len(columnas.split()) == 2, columnas)

        # Móvil: apilado y gráfica ampliada.
        pagina.set_viewport_size({"width": 390, "height": 844})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        columnas_movil = pagina.locator(".cierre-deuda__velocimetros").evaluate(
            "(e) => getComputedStyle(e).gridTemplateColumns"
        )
        comprobar("móvil una columna", len(columnas_movil.split()) == 1, columnas_movil)
        cajas = pagina.locator(".cierre-deuda__velocimetro").all()
        y1 = cajas[0].bounding_box()["y"]
        y2 = cajas[1].bounding_box()["y"]
        comprobar("primero pago mínimo", y1 < y2, f"{y1}/{y2}")
        alto = pagina.locator(".cierre-deuda__grafica svg").evaluate(
            "(e) => getComputedStyle(e).height"
        )
        comprobar("gráfica móvil 220px", alto == "220px", alto)
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
