"""Recorrido de QA de la SRS v4.10 en navegador real (Chromium).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_10
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

        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "sin fila duplicada de ley",
            pagina.locator("[data-deducciones-quincena]").count() == 0,
        )
        q2 = pagina.locator('[data-ingreso-quincena="2"]').first.inner_text().strip()
        comprobar("Q2 neto de ley", "2.060.775" in q2, q2)
        comprobar(
            "etiqueta TOTAL DEVENGADO",
            "TOTAL DEVENGADO" in pagina.locator(".resultado-principal__etiqueta").inner_text(),
        )
        nota = pagina.locator(".resultado-principal__nota").inner_text()
        comprobar(
            "nota en dos líneas",
            "Ingresos totales menos deducciones de ley e incapacidad." in nota
            and "Total de Gastos del mes:" in nota,
            " | ".join(nota.split("\n")),
        )

        campos = pagina.locator(
            ".panel--resultado ul.lista-parametros .lista-parametros__separador ~ li [data-campo]"
        ).count()
        comprobar("bloque de deducciones tras separador", campos == 4, str(campos))
        campos_totales = pagina.locator(
            ".panel--resultado ul.lista-parametros [data-campo]"
        ).evaluate_all("(ns) => ns.map(n => n.getAttribute('data-campo'))")
        esperado = [
            "valor_hora",
            "total_recargos",
            "total_devengado",
            "auxilio_transporte",
            "total_ingresos",
            "deduccion_salud",
            "deduccion_pension",
            "deduccion_incapacidad",
            "total_deducciones",
        ]
        comprobar("orden exacto de las 9 filas", campos_totales == esperado, str(campos_totales))

        # Dona global blindada.
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        comprobar("dona global intacta", "dona__desglose" in pagina.content())
        comprobar("Total libre intacto", 'data-leyenda-etiqueta="Total libre"' in pagina.content())

        # No regresión responsive.
        for ancho in (360, 390, 768, 1280):
            pagina.set_viewport_size({"width": ancho, "height": 900})
            pagina.goto(f"{BASE}/finanzas")
            medida = pagina.evaluate(
                "() => [window.innerWidth, document.documentElement.scrollWidth]"
            )
            comprobar(f"sin desborde {ancho}px", medida[1] <= medida[0], f"{medida[1]}/{medida[0]}")

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
