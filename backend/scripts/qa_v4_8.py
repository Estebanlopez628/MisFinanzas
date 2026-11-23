"""Recorrido de QA de la SRS v4.8 en navegador real (Chromium).

Responsabilidad
---------------
Verificar los 7 conceptos 2026, la liquidación real de quincenas con auxilio de
transporte y las etiquetas limpias, además de la no regresión de módulos blindados.

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_8
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
        detalle: Información extra para el informe.
    """
    resultados.append((nombre, bool(condicion), detalle))


def texto(pagina, selector: str) -> str:
    """Devuelve el texto visible de un selector.

    Args:
        pagina: Página abierta.
        selector: Selector CSS.

    Returns:
        Texto normalizado.
    """
    localizador = pagina.locator(selector)
    return " ".join(localizador.first.inner_text().split()) if localizador.count() else ""


def main() -> None:
    """Ejecuta el recorrido completo.

    Returns:
        None. Imprime el informe por consola.
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

        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        html = pagina.content()

        claves = (
            "EXTRA_DIURNA_NORMAL",
            "EXTRA_NOCTURNA",
            "EXTRA_DIURNA_DOMINICAL_FESTIVA",
            "EXTRA_NOCTURNA_DOMINICAL_FESTIVA",
            "RECARGO_NOCTURNO",
            "RECARGO_DOMINICAL_FESTIVO",
            "RECARGO_NOCTURNO_DOMINICAL_FESTIVO",
        )
        comprobar(
            "7 conceptos en el formulario",
            all(f'name="horas_{clave}"' in html for clave in claves),
        )
        comprobar("etiqueta Sueldo devengado", "Sueldo devengado" in html)
        comprobar("etiqueta Total devengado", "Total devengado" in html)
        comprobar("sin etiquetas con guion", "Sueldo-percibido" not in html and "Ingreso proyectado" not in html)
        comprobar("base de 220 horas", "220 horas mensuales" in html)

        q1 = texto(pagina, '[data-ingreso-quincena="1"]')
        q2 = texto(pagina, '[data-ingreso-quincena="2"]')
        total = texto(pagina, '[data-campo="total_devengado_consolidado"]')
        comprobar("Q1 = $1.393.600", "1.393.600" in q1, q1)
        comprobar("Q2 = $2.339.495 (con auxilio)", "2.339.495" in q2, q2)
        comprobar("Total devengado = $3.454.375", "3.454.375" in total, total)

        # Los 7 factores llegan al navegador y 10,4 h del nuevo concepto se liquidan.
        respuesta = pagina.request.post(
            f"{BASE}/finanzas/calcular",
            data={
                "sueldo_basico": "3.484.000",
                "deduccion_incapacidad": "0",
                "horas_RECARGO_NOCTURNO_DOMINICAL_FESTIVO": "10.4",
            },
        )
        datos = respuesta.json()
        detalle = datos.get("detalle", [])
        comprobar(
            "10,4 h del 7.º concepto se liquidan",
            respuesta.ok
            and len(detalle) == 1
            and detalle[0]["etiqueta"] == "Recargo nocturno dominical/festivo"
            and detalle[0]["horas"] == "10,40",
            str(detalle)[:140],
        )
        comprobar(
            "Total devengado reactivo presente",
            "total_devengado_consolidado" in datos.get("datos", {}),
        )

        # No regresión de módulos blindados.
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        comprobar("dona global intacta", "dona__desglose" in pagina.content())
        svg = pagina.locator(".cierre-deuda__velocimetro svg").first
        if svg.count():
            ancho, alto = svg.evaluate(
                "(e) => [getComputedStyle(e).width, getComputedStyle(e).height]"
            )
            comprobar("velocímetro web 156x88", ancho == "156px" and alto == "88px", f"{ancho}x{alto}")
        pagina.goto(f"{BASE}/deudas")
        comprobar(
            "edición de descripción intacta",
            'data-actualizar-deuda' in pagina.content(),
        )

        for ancho in (360, 390, 768, 1280):
            pagina.set_viewport_size({"width": ancho, "height": 900})
            pagina.goto(f"{BASE}/finanzas")
            pagina.goto(f"{BASE}/presupuesto")
            dimens = pagina.evaluate(
                "() => [window.innerWidth, document.documentElement.scrollWidth]"
            )
            comprobar(f"sin desborde {ancho}px", dimens[1] <= dimens[0], f"{dimens[1]}/{dimens[0]}")

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
