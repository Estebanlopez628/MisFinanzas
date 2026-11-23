"""Recorrido de QA de la SRS v4.19 en navegador real (Chromium).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_19
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

        # Amortización paralela: 36 + 8 + 10 → 36 meses.
        for nombre, total, cuota, cuotas in (
            ("QA Paralela Larga", "36000000", "1000000", 36),
            ("QA Paralela Corta", "800000", "100000", 8),
            ("QA Paralela Media", "1000000", "100000", 10),
        ):
            pagina.request.post(
                f"{BASE}/deudas",
                form={
                    "acreedor": nombre,
                    "descripcion": nombre,
                    "saldo_total": total,
                    "cuota": cuota,
                    "cuotas_pendientes": cuotas,
                    "periodicidad": "MENSUAL",
                },
            )
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        consejo = pagina.locator(".consejero").inner_text()
        comprobar("plazo paralelo 36 meses", "36 meses" in consejo, consejo[:160])
        comprobar("sin suma de plazos", "54 meses" not in consejo)
        comprobar("próximas metas", "próximas metas a pagar" in consejo)

        # Gráfica de 6 meses.
        pagina.goto(f"{BASE}/presupuesto")
        titulo = pagina.locator(".cierre-deuda__subtitulo--seis").inner_text()
        comprobar("título 6 meses", "Proyección de saldo (6 meses)" in titulo, titulo)
        comprobar(
            "badges Inicial y Mes 6",
            "Inicial:" in pagina.locator(".cierre-deuda__extremo--inicial").inner_text()
            and "Mes 6:" in pagina.locator(".cierre-deuda__extremo--final").inner_text(),
        )
        pildoras = pagina.locator(".cierre-deuda__mes").count()
        comprobar("6 píldoras", pildoras == 6, str(pildoras))
        comprobar(
            "un mes activo", pagina.locator(".cierre-deuda__mes--activo").count() == 1
        )
        dash = pagina.locator(".cierre-deuda__grafica polyline").first.get_attribute(
            "stroke-dasharray"
        )
        comprobar("curva base discontinua", dash == "7 7", str(dash))
        comprobar(
            "área diferencial", pagina.locator(".cierre-deuda__ahorro").count() == 1
        )
        display_meses = pagina.locator(".cierre-deuda__meses").evaluate(
            "(e) => getComputedStyle(e).display"
        )
        comprobar("6 columnas en escritorio", display_meses == "grid", display_meses)

        # Dona centrada en escritorio.
        justificacion = pagina.locator(".capacidad__resumen").evaluate(
            "(e) => getComputedStyle(e).justifyContent"
        )
        comprobar("dona centrada", justificacion == "center", justificacion)
        texto_justificado = pagina.locator(".consejero__pasos li").first.evaluate(
            "(e) => getComputedStyle(e).textAlign"
        )
        comprobar("texto justificado", texto_justificado == "justify", texto_justificado)

        # Móvil: banner, gráfica deslizable y tabla de atajos alineada.
        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        radio = pagina.locator(".cierre-deuda__pill").evaluate(
            "(e) => getComputedStyle(e).borderRadius"
        )
        comprobar("banner radio 14px", radio == "14px", radio)
        display_movil = pagina.locator(".cierre-deuda__meses").evaluate(
            "(e) => getComputedStyle(e).display"
        )
        comprobar("píldoras deslizables", display_movil == "flex", display_movil)

        pagina.request.post(
            f"{BASE}/chancucos",
            form={
                "descripcion": "Energía QA",
                "numero_referencia": "123456",
                "valor_pago": "74000",
                "dia_pago_1": "15",
            },
        )
        pagina.goto(f"{BASE}/chancucos")
        pagina.wait_for_load_state("networkidle")
        tabla = pagina.locator(".tabla--atajos")
        if tabla.count():
            display_tabla = tabla.evaluate("(e) => getComputedStyle(e).display")
            layout = tabla.evaluate("(e) => getComputedStyle(e).tableLayout")
            ancho2 = tabla.locator("thead th").nth(1).evaluate(
                "(e) => getComputedStyle(e).width"
            )
            comprobar(
                "tabla real table-fixed",
                display_tabla == "table" and layout == "fixed",
                f"{display_tabla}/{layout}",
            )
            ancho_tabla = tabla.evaluate("(e) => e.getBoundingClientRect().width")
            propcion = float(ancho2[:-2]) / ancho_tabla if ancho_tabla else 0
            comprobar(
                "columna descripción 38%",
                0.35 <= propcion <= 0.42,
                f"{ancho2} de {ancho_tabla:.0f}px ({propcion:.0%})",
            )
            padding = tabla.locator("thead th").nth(1).evaluate(
                "(e) => getComputedStyle(e).paddingLeft"
            )
            comprobar("padding 8px", padding == "8px", padding)
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
