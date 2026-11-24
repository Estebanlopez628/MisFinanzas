"""Gate QA de la SRS v4.31 en Chromium: ancho KPI y grilla 3 × 3."""

from __future__ import annotations

from playwright.sync_api import sync_playwright
from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import Deuda

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


def limpiar_qa() -> None:
    """Borra la deuda sembrada por el gate.

    Returns:
        None. Hace el gate repetible.
    """
    with FabricaSesiones() as bd:
        for deuda in bd.scalars(
            select(Deuda).where(Deuda.acreedor == "QA KPI v431")
        ).all():
            bd.delete(deuda)
        bd.commit()


def main() -> None:
    """Ejecuta el recorrido completo.

    Returns:
        None. Imprime el informe.
    """
    limpiar_qa()
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
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")

        ancho_kpi = pagina.locator(".rejilla-tarjetas--deudas").evaluate(
            "(e) => Math.round(e.getBoundingClientRect().width)"
        )
        ancho_panel = pagina.locator(".rejilla-paneles--deudas > .panel").first.evaluate(
            "(e) => Math.round(e.getBoundingClientRect().width)"
        )
        comprobar(
            "web: Nueva deuda=ancho de las 3 KPI",
            ancho_kpi == ancho_panel,
            f"{ancho_panel} vs {ancho_kpi}",
        )

        grilla = pagina.locator(".fila-campos--deuda-nueva")
        columnas = grilla.evaluate("(e) => getComputedStyle(e).gridTemplateColumns")
        filas = grilla.evaluate("(e) => getComputedStyle(e).gridTemplateRows")
        comprobar(
            "web: grilla 3 × 3",
            len(columnas.split()) == 3 and len(filas.split()) == 2,
            f"{columnas} / {filas}",
        )
        comprobar(
            "web: base alineada",
            grilla.evaluate("(e) => getComputedStyle(e).alignItems") == "end",
        )

        nombres = ["acreedor", "descripcion", "periodicidad", "saldo_total", "cuota", "cuotas_pendientes"]
        cajas = [
            pagina.locator(f'[name="{nombre}"]').first.bounding_box() for nombre in nombres
        ]
        kpis = [
            caja.bounding_box()
            for caja in pagina.locator(".rejilla-tarjetas--deudas > .tarjeta").all()
        ]
        if all(cajas) and all(kpis):
            centros_campos = [c["x"] + c["width"] / 2 for c in cajas[:3]]
            centros_kpi = [c["x"] + c["width"] / 2 for c in kpis]
            comprobar(
                "web: fila 1 alineada con KPI con margen interior",
                all(abs(centros_campos[i] - centros_kpi[i]) <= 12 for i in range(3)),
                f"{[round(c) for c in centros_campos]} vs {[round(c) for c in centros_kpi]}",
            )
            x_panel = pagina.locator(".rejilla-paneles--deudas > .panel").first.bounding_box()["x"]
            margen_izq = cajas[0]["x"] - x_panel
            comprobar(
                "web: campos separados de los bordes",
                margen_izq >= 10
                and (x_panel + ancho_panel - (cajas[2]["x"] + cajas[2]["width"])) >= 10,
                f"izq={round(margen_izq)} der={round(x_panel + ancho_panel - (cajas[2]['x'] + cajas[2]['width']))}",
            )
            comprobar(
                "web: cajas de texto más bajas",
                cajas[0]["height"] <= 44,
                f"{round(cajas[0]['height'])} px",
            )
            comprobar(
                "web: fila 2 debajo de la fila 1",
                cajas[3]["y"] > cajas[0]["y"] + 20
                and abs(cajas[3]["x"] - cajas[0]["x"]) < 2,
                str([round(c["y"]) for c in cajas]),
            )
        else:
            comprobar("web: seis campos visibles", False)

        pie = pagina.locator(".acciones-formulario--deuda-nueva")
        comprobar(
            "web: pie con divisoria y botón",
            pie.evaluate("(e) => getComputedStyle(e).borderTopWidth") == "1px"
            and pie.locator("button", has_text="Guardar deuda").count() == 1,
        )

        # Registrar una deuda confirma que el formulario sigue funcionando.
        pagina.fill('input[name="acreedor"]', "QA KPI v431")
        pagina.fill('input[name="descripcion"]', "Deuda de prueba grilla")
        pagina.fill('input[name="saldo_total"]', "200.000")
        pagina.fill('input[name="cuota"]', "50.000")
        pagina.fill('input[name="cuotas_pendientes"]', "4")
        pagina.locator("select[name=periodicidad]").select_option("MENSUAL")
        with pagina.expect_navigation(wait_until="networkidle"):
            pagina.locator("[data-guardar-deuda]").click()
        comprobar(
            "web: deuda registrada",
            "Deuda registrada." in pagina.locator("body").inner_text()
            or "QA KPI v431" in pagina.content(),
        )

        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        anchos = pagina.evaluate(
            "() => ({scroll: document.documentElement.scrollWidth, view: innerWidth})"
        )
        comprobar(
            "móvil: sin desbordamiento",
            anchos["scroll"] <= anchos["view"],
            str(anchos),
        )
        comprobar(
            "móvil: rejilla intacta",
            pagina.locator(".fila-campos--deuda-nueva").count() == 1,
        )
        comprobar("sin errores de consola", not errores, "; ".join(errores[:2]))
        contexto.close()
        navegador.close()

    limpiar_qa()
    fallos = [fila for fila in resultados if not fila[1]]
    for nombre, ok, detalle in resultados:
        print(("PASS " if ok else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""))
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
