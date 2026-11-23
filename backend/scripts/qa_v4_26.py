"""Gate QA de la SRS v4.26 en Chromium real (web y móvil).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_26
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import AbonoDeuda, Deuda, DeduccionFija, Gasto, PagoDeuda
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
ACREEDOR = "QA Grilla v426"
GASTO = "QA Check v426"
DEDUCCION = "QA Deduccion v426"

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado de la comprobación.
        detalle: Información extra para el informe.
    """
    resultados.append((nombre, bool(condicion), detalle))


def limpiar_qa() -> None:
    """Borra los registros sembrados por este gate.

    Returns:
        None. Hace el recorrido repetible.
    """
    with FabricaSesiones() as bd:
        for deuda in bd.scalars(select(Deuda).where(Deuda.acreedor == ACREEDOR)).all():
            for abono in bd.scalars(
                select(AbonoDeuda).where(AbonoDeuda.id_deuda == deuda.id_deuda)
            ).all():
                bd.delete(abono)
            for pago in bd.scalars(
                select(PagoDeuda).where(PagoDeuda.id_deuda == deuda.id_deuda)
            ).all():
                bd.delete(pago)
            bd.delete(deuda)
        for gasto in bd.scalars(select(Gasto).where(Gasto.descripcion == GASTO)).all():
            bd.delete(gasto)
        for deduccion in bd.scalars(
            select(DeduccionFija).where(DeduccionFija.descripcion == DEDUCCION)
        ).all():
            bd.delete(deduccion)
        bd.commit()


def verificar_grilla(page, etiqueta: str, selector: str) -> None:
    """Comprueba la grilla 2 + 1 de un modal.

    Args:
        page: Página de Playwright.
        etiqueta: Prefijo para el informe.
        selector: Selector del contenedor de acciones.
    """
    contenedor = page.locator(selector).first
    columnas = contenedor.evaluate("(e) => getComputedStyle(e).gridTemplateColumns")
    huecos = len(columnas.split())
    comprobar(f"{etiqueta}: dos columnas", huecos == 2, columnas)
    comprobar(
        f"{etiqueta}: gap 12px",
        contenedor.evaluate("(e) => getComputedStyle(e).gap") == "12px",
    )
    botones = contenedor.locator("button")
    comprobar(f"{etiqueta}: tres botones", botones.count() == 3, str(botones.count()))
    if botones.count() == 3:
        uno = botones.nth(0).bounding_box()
        dos = botones.nth(1).bounding_box()
        tres = botones.nth(2).bounding_box()
        comprobar(
            f"{etiqueta}: fila superior lado a lado",
            uno is not None and dos is not None and abs(uno["y"] - dos["y"]) < 2,
        )
        comprobar(
            f"{etiqueta}: inferior a ancho completo",
            tres is not None
            and uno is not None
            and tres["width"] >= uno["width"] * 2 + 10,
            f"{tres['width'] if tres else 0} vs {uno['width'] if uno else 0}",
        )


def verificar_check(page, etiqueta: str) -> None:
    """Mide el cambio optimista del check y su persistencia.

    Args:
        page: Página de Playwright.
        etiqueta: Prefijo para el informe.
    """
    # Marca de sesión que desaparecería si la página se recargara.
    estado_inicial = page.locator("li.lista-gastos__item--pagado").count()
    page.evaluate("() => { window.__sinRecarga = 1; }")
    resultado = page.evaluate(
        """() => {
          const form = document.querySelector('form[data-check-gasto]');
          const boton = form.querySelector('button[type="submit"]');
          const inicio = performance.now();
          let cambio = null;
          const obs = new MutationObserver(() => {
            if (cambio === null) cambio = performance.now();
          });
          obs.observe(boton, { attributes: true, attributeFilter: ['class'] });
          form.requestSubmit();
          return new Promise(resolve => setTimeout(() => {
            obs.disconnect();
            resolve(cambio === null ? -1 : cambio - inicio);
          }, 250));
        }"""
    )
    comprobar(
        f"{etiqueta}: check responde < 50 ms",
        0 <= resultado < 50,
        f"{round(resultado, 1)} ms",
    )
    comprobar(
        f"{etiqueta}: sin recarga de página",
        page.evaluate("() => window.__sinRecarga === 1"),
    )
    estado_despues = page.locator("li.lista-gastos__item--pagado").count()
    comprobar(
        f"{etiqueta}: estado del check invertido",
        estado_despues != estado_inicial,
        f"{estado_inicial} -> {estado_despues}",
    )
    page.reload()
    page.wait_for_load_state("networkidle")
    comprobar(
        f"{etiqueta}: persistencia tras recargar",
        page.locator("li.lista-gastos__item--pagado").count() == estado_despues,
    )


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
        comprobar("login QA", "/login" not in pagina.url, pagina.url)

        pagina.request.post(
            f"{BASE}/deudas",
            form={
                "acreedor": ACREEDOR,
                "descripcion": "Deuda para grilla",
                "saldo_total": "200.000",
                "cuota": "50.000",
                "cuotas_pendientes": "4",
                "periodicidad": "MENSUAL",
            },
        )
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        id_deuda = (
            pagina.locator('button[data-abrir-abono][data-deuda="' + ACREEDOR + '"]')
            .first.get_attribute("data-id-deuda")
            or ""
        )
        pagina.request.post(
            f"{BASE}/gastos",
            form={
                "categoria": "Vivienda",
                "descripcion": GASTO,
                "valor": "800.000",
                "fecha": date.today().isoformat(),
                "es_fijo": "1",
                "quincena": "1",
            },
        )
        pagina.request.post(
            f"{BASE}/presupuesto/deducciones",
            form={
                "descripcion": DEDUCCION,
                "valor": "50.000",
                "quincena": "1",
                "id_deuda": id_deuda,
                "categoria": "Créditos y Obligaciones",
            },
        )

        # --- Escritorio --------------------------------------------------------
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        detalles = pagina.locator("details.edicion-gasto--modal").filter(has_text="Editar deuda")
        detalles.first.locator("summary").click()
        verificar_grilla(
            pagina, "web editar deuda",
            "details.edicion-gasto--modal[open] .acciones-formulario--grilla",
        )

        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        detalles = pagina.locator("details.edicion-gasto--modal").filter(has_text="Editar deducción")
        detalles.first.locator("summary").click()
        verificar_grilla(
            pagina, "web editar deducción",
            "details.edicion-gasto--modal[open] .acciones-formulario--grilla",
        )

        # Un check de gasto fijo debe responder al instante y persistir.
        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        verificar_check(pagina, "web")

        # --- Móvil -------------------------------------------------------------
        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        detalles = pagina.locator("details.edicion-gasto--modal").filter(has_text="Editar deuda")
        detalles.first.evaluate("(e) => { e.open = true; }")
        verificar_grilla(
            pagina, "móvil editar deuda",
            "details.edicion-gasto--modal[open] .acciones-formulario--grilla",
        )

        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        verificar_check(pagina, "móvil")

        comprobar("sin errores de consola", not errores, "; ".join(errores[:3]))
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
