"""Recorrido de QA de la SRS v4.5 en navegador real (Chromium).

Responsabilidad
---------------
Verificar en web y móvil la dona global con desglose apilado, la edición de la
descripción de deudas y el tamaño de los velocímetros solo en escritorio.

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_5
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
TAMANOS = (360, 390, 768, 1280)

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado de la comprobación.
        detalle: Información extra para el informe.
    """
    resultados.append((nombre, bool(condicion), detalle))


def sin_desborde(pagina, etiqueta: str) -> None:
    """Comprueba que no haya desplazamiento horizontal.

    Args:
        pagina: Página abierta.
        etiqueta: Nombre de la vista.
    """
    ancho, desborde = pagina.evaluate(
        "() => [window.innerWidth, document.documentElement.scrollWidth]"
    )
    comprobar(f"sin desborde {etiqueta}", desborde <= ancho, f"{desborde}/{ancho}")


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

        # ---- Dona global y desglose apilado ----
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        html = pagina.content()
        comprobar("dona con sub-desglose", "dona__desglose" in html)
        comprobar("desglose Mis Finanzas", "↳ Mis Finanzas:" in html)
        comprobar("desglose Trabajos Extras", "↳ Trabajos Extras:" in html)
        comprobar("ingreso global", "Ingreso global del mes:" in html)
        comprobar("una sola tajada de libre", 'data-leyenda-etiqueta="Total libre"' in html)
        comprobar("sin tajadas viejas de libre", "Base mínima de liquidez:" not in html.split("Comparativa")[0])
        comprobar(" Consejero activo", "Consejero financiero" in html)
        comprobar("colchón en Consejero", "base mínima de liquidez" in html.lower())

        # ---- Velocímetros: escritorio 156x88, móvil 120x68 ----
        svg = pagina.locator(".cierre-deuda__velocimetro svg").first
        if svg.count():
            ancho, alto = svg.evaluate("(e) => [getComputedStyle(e).width, getComputedStyle(e).height]")
            maximo = pagina.locator(".cierre-deuda__velocimetros").evaluate(
                "(e) => getComputedStyle(e).maxWidth"
            )
            comprobar("SVG escritorio 156x88", ancho == "156px" and alto == "88px", f"{ancho}x{alto}")
            comprobar("contenedor 640px", maximo == "640px", maximo)
            cajas = pagina.locator(".cierre-deuda__velocimetro").all()
            if len(cajas) == 2:
                y1 = cajas[0].bounding_box()["y"]
                y2 = cajas[1].bounding_box()["y"]
                comprobar("velocímetros lado a lado", abs(y1 - y2) < 4, f"y={y1}/{y2}")
        else:
            comprobar("SVG escritorio 156x88", False, "sin comparativa")

        pagina.set_viewport_size({"width": 390, "height": 844})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        svg_movil = pagina.locator(".cierre-deuda__velocimetro svg").first
        if svg_movil.count():
            ancho, alto = svg_movil.evaluate("(e) => [getComputedStyle(e).width, getComputedStyle(e).height]")
            comprobar("SVG móvil 120x68 intacto", ancho == "120px" and alto == "68px", f"{ancho}x{alto}")

        # ---- Edición de descripción ----
        pagina.set_viewport_size({"width": 1280, "height": 900})
        pagina.goto(f"{BASE}/deudas")
        deuda = pagina.locator("[data-id-deuda]").first
        id_deuda = deuda.get_attribute("data-id-deuda")
        # Se siembra una descripción conocida para comprobar el precargado.
        pagina.request.patch(
            f"{BASE}/api/deudas/{id_deuda}", form={"descripcion": "Descripción previa QA"}
        )
        pagina.goto(f"{BASE}/deudas")
        deuda = pagina.locator("[data-id-deuda]").first
        modal = deuda.locator("details.edicion-gasto--modal")
        modal.locator('summary').first.click() if modal.locator("summary").count() else modal.evaluate("(e) => e.open = true")
        campo = pagina.locator(f'[data-id-deuda="{id_deuda}"] input[name="descripcion"]')
        comprobar("descripción editable", campo.count() == 1 and campo.get_attribute("type") == "text")
        comprobar("descripción pre-cargada", bool(campo.input_value()), campo.input_value())

        campo.fill("Descripción QA v4.5")
        modal.locator("[data-actualizar-deuda]").click()
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "descripción guardada",
            "Descripción QA v4.5" in pagina.content(),
        )

        respuesta = pagina.request.patch(
            f"{BASE}/api/deudas/{id_deuda}", form={"descripcion": "Descripción vía API"}
        )
        datos = respuesta.json()
        comprobar(
            "PATCH API persiste descripción",
            respuesta.ok and datos["deuda"]["descripcion"] == "Descripción vía API",
            str(datos)[:120],
        )

        # ---- Recorrido responsive ----
        for ancho in TAMANOS:
            pagina.set_viewport_size({"width": ancho, "height": 900})
            for ruta in ("/", "/presupuesto", "/deudas", "/finanzas"):
                pagina.goto(f"{BASE}{ruta}")
                sin_desborde(pagina, f"{ruta} {ancho}px")

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
