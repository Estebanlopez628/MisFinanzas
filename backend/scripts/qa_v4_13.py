"""Recorrido de QA de la SRS v4.13 en navegador real (Chromium).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_13
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

        # Tarjetas de corte: solo saldo, sueldo neto y gastos.
        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "sin filas de ley ni fijas",
            pagina.locator("[data-deducciones-quincena]").count() == 0
            and pagina.locator("[data-fijas-quincena]").count() == 0,
        )
        filas = pagina.locator(".panel--quincena").first.locator(
            ".lista-parametros--compacta li"
        ).all_inner_texts()
        comprobar("solo dos filas en la tarjeta", len(filas) == 2, str(filas))
        q2 = pagina.locator('[data-ingreso-quincena="2"]').first.inner_text().strip()
        comprobar("Q2 neto real $2.060.775", "2.060.775" in q2, q2)

        # Consejero: cifras reales y textos Claros.
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        texto = pagina.locator(".cierre-deuda").inner_text()
        comprobar("sin intereses ficticios", "interes" not in texto.lower())
        comprobar("sin frase más de 12 meses", "más de 12 meses" not in pagina.content())
        comprobar("sin titular viejo", "¡Ahorras" not in texto)
        comprobar(
            "plazo exacto en velocímetro",
            "meses" in texto and "Saldo actual:" in texto,
        )
        comprobar(
            "detalle real del mes",
            "Saldo Base:" in texto
            and "Saldo Optimizado:" in texto
            and "Reducción extra acumulada:" in texto,
        )
        comprobar(
            "meses completos en español",
            any(
                m in texto
                for m in (
                    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
                )
            ),
        )
        comprobar(
            "deudas con saldo y cuota",
            "saldo:" in pagina.locator(".consejero__pasos").inner_text()
            and "cuota:" in pagina.locator(".consejero__pasos").inner_text(),
        )

        # Escritorio: curva al 100 %, píldoras oscuras y sub-tarjetas.
        ancho_svg = pagina.locator(".cierre-deuda__grafica svg").evaluate(
            "(e) => getComputedStyle(e).width"
        )
        ancho_padre = pagina.locator(".cierre-deuda__grafica").evaluate(
            "(e) => getComputedStyle(e).width"
        )
        comprobar(
            "curva al 100 % en escritorio",
            ancho_svg == ancho_padre,
            f"{ancho_svg}/{ancho_padre}",
        )
        fondo_mes = pagina.locator(".cierre-deuda__mes").first.evaluate(
            "(e) => getComputedStyle(e).backgroundColor"
        )
        comprobar("píldora oscura", fondo_mes != "rgba(0, 0, 0, 0)", fondo_mes)
        borde_vel = pagina.locator(".cierre-deuda__velocimetro").first.evaluate(
            "(e) => getComputedStyle(e).borderTopWidth"
        )
        comprobar("sub-tarjeta velocímetro", borde_vel == "1px", borde_vel)

        # Móvil: distribución intacta (mismo ancho de SVG compacto y sin borde).
        pagina.set_viewport_size({"width": 390, "height": 844})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        svg_movil = pagina.locator(".cierre-deuda__velocimetro svg").first.evaluate(
            "(e) => [getComputedStyle(e).width, getComputedStyle(e).height]"
        )
        comprobar("móvil 120x68 intacto", svg_movil == ["120px", "68px"], str(svg_movil))
        borde_movil = pagina.locator(".cierre-deuda__velocimetro").first.evaluate(
            "(e) => getComputedStyle(e).borderTopWidth"
        )
        comprobar("móvil sin sub-tarjeta", borde_movil == "0px", borde_movil)

        for ancho in (360, 390, 768, 1280):
            pagina.set_viewport_size({"width": ancho, "height": 900})
            pagina.goto(f"{BASE}/presupuesto")
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
