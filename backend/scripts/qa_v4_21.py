"""Recorrido de QA de la SRS v4.21 (abonos a deudas) en Chromium real.

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_21

Cubre web (1280 px) y móvil (375 px). Siembra una deuda, un gasto y una
deducción de prueba con prefijo QA y los elimina al terminar.
"""

from __future__ import annotations

from datetime import date

from playwright.sync_api import sync_playwright
from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import AbonoDeuda, Deuda, DeduccionFija, Gasto, PagoDeuda

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
ACREEDOR = "QA Abonos v421"
GASTO = "QA Cuota v421"
DEDUCCION = "QA Libranza v421"

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
    """Borra de la base los registros QA de este recorrido.

    Returns:
        None. Hace el gate repetible sin dejar datos residuales.
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


def _id_de_accion(accion: str | None) -> str:
    """Extrae el identificador de una URL de formulario.

    Args:
        accion: Valor del atributo `action` o `None`.

    Returns:
        El último segmento de la ruta, o cadena vacía.
    """
    if not accion:
        return ""
    return accion.rstrip("/").split("/")[-1]


def _centro(page, selector: str) -> str:
    """Lee el `text-align` computado de un elemento.

    Args:
        page: Página de Playwright.
        selector: Selector CSS.

    Returns:
        Valor computado de `text-align`, o `None` si no existe.
    """
    localizador = page.locator(selector).first
    if not localizador.count():
        return "(sin elemento)"
    return str(localizador.evaluate("(e) => getComputedStyle(e).textAlign"))


def abrir_abono(page, id_deuda: str) -> None:
    """Abre el modal de abono desde el botón de una deuda.

    Args:
        page: Página de Playwright.
        id_deuda: Identificador de la deuda.
    """
    boton = page.locator(f'button[data-abrir-abono][data-id-deuda="{id_deuda}"]').first
    boton.evaluate("(e) => { const d = e.closest('details'); if (d) d.open = true; }")
    boton.click()


def verificar_donas(page, etiqueta: str) -> None:
    """Comprueba el centrado del panel de capacidad en la vista actual.

    Args:
        page: Página de Playwright.
        etiqueta: Prefijo para las comprobaciones.
    """
    comprobar(
        f"{etiqueta}: título centrado",
        _centro(page, ".panel.capacidad .panel__titulo") == "center",
        _centro(page, ".panel.capacidad .panel__titulo"),
    )
    comprobar(
        f"{etiqueta}: descripción centrada",
        _centro(page, ".panel.capacidad > .ayuda") == "center",
        _centro(page, ".panel.capacidad > .ayuda"),
    )
    if page.locator(".panel.capacidad .dona-contenedor").count():
        comprobar(
            f"{etiqueta}: leyenda centrada",
            _centro(page, ".panel.capacidad .dona__leyenda li") == "center",
            _centro(page, ".panel.capacidad .dona__leyenda li"),
        )
        justificar = page.locator(".panel.capacidad .dona-contenedor").first.evaluate(
            "(e) => getComputedStyle(e).justifyContent"
        )
        comprobar(
            f"{etiqueta}: dona centrada",
            justificar == "center",
            justificar,
        )
    else:
        # Sin ingresos del mes el panel muestra solo el aviso; el centrado del
        # texto ya quedó comprobado arriba.
        comprobar(f"{etiqueta}: panel sin dona (aviso)", True, "sin ingresos del mes")


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

        # --- Siembra controlada -------------------------------------------------
        pagina.request.post(
            f"{BASE}/deudas",
            form={
                "acreedor": ACREEDOR,
                "descripcion": "Deuda de prueba abonos",
                "saldo_total": "200.000",
                "cuota": "50.000",
                "cuotas_pendientes": "4",
                "periodicidad": "MENSUAL",
            },
        )
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        fila_deuda = pagina.locator(f'button[data-abrir-abono][data-deuda="{ACREEDOR}"]')
        comprobar("deuda QA sembrada", fila_deuda.count() >= 1, str(fila_deuda.count()))
        id_deuda = fila_deuda.first.get_attribute("data-id-deuda") or ""
        comprobar("id de deuda capturado", bool(id_deuda), id_deuda)

        pagina.request.post(
            f"{BASE}/gastos",
            form={
                "categoria": "Créditos y Obligaciones",
                "descripcion": GASTO,
                "valor": "50.000",
                "fecha": date.today().isoformat(),
                "es_fijo": "1",
                "quincena": "1",
                "id_deuda": id_deuda,
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

        # --- Puntos de entrada del botón Abonar ---------------------------------
        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "Abonar en gastos fijos de Finanzas",
            pagina.locator(f'button[data-abrir-abono][data-id-deuda="{id_deuda}"]').count() >= 1,
        )

        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "Abonar en deducciones de Créditos",
            pagina.locator(f'li[data-deduccion-fila]:has-text("{DEDUCCION}") button[data-abrir-abono]').count() >= 1,
        )
        verificar_donas(pagina, "web /presupuesto")

        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "Abonar en deudas registradas",
            pagina.locator(f'button[data-abrir-abono][data-id-deuda="{id_deuda}"]').count() >= 1,
        )

        pagina.goto(f"{BASE}/trabajos-extras")
        pagina.wait_for_load_state("networkidle")
        verificar_donas(pagina, "web /trabajos-extras")

        # --- Cabeceras de atajos centradas --------------------------------------
        pagina.goto(f"{BASE}/chancucos")
        pagina.wait_for_load_state("networkidle")
        if pagina.locator(".tabla--atajos").count():
            th3 = pagina.locator(".tabla--atajos thead th:nth-child(3)").first.evaluate(
                "(e) => getComputedStyle(e).textAlign"
            )
            th4 = pagina.locator(".tabla--atajos thead th:nth-child(4)").first.evaluate(
                "(e) => getComputedStyle(e).textAlign"
            )
            comprobar("VALOR A PAGAR centrado", th3 == "center", th3)
            comprobar("DÍAS DE PAGO centrado", th4 == "center", th4)
            comprobar("saltos de línea intactos", pagina.locator(".tabla--atajos thead th br").count() == 2)
        else:
            comprobar("tabla de atajos presente", False, "sin atajos QA")

        # --- Flujo real de abono -------------------------------------------------
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        abrir_abono(pagina, id_deuda)
        comprobar("modal de abono visible", pagina.locator("#modal-abono").is_visible())
        cuerpo = " ".join(pagina.locator("#modal-abono-cuerpo").inner_text().split())
        comprobar("texto del modal", "Digita el valor que deseas abonar a tu deuda" in cuerpo, cuerpo)
        comprobar(
            "tres botones del modal",
            pagina.locator("#modal-abono [data-abono-solo]").inner_text().strip() == "Registrar abono"
            and pagina.locator("#modal-abono [data-abono-cuota]").inner_text().strip() == "Registrar abono + cuota"
            and pagina.locator("#modal-abono [data-abono-cancelar]").inner_text().strip() == "Cancelar",
        )
        pagina.fill("#modal-abono-valor", "50.000")
        with pagina.expect_navigation(wait_until="networkidle"):
            pagina.locator("#modal-abono [data-abono-solo]").click()
        deudas_api = pagina.request.get(f"{BASE}/api/deudas").json()["deudas"]
        fila = next((d for d in deudas_api if d["id_deuda"] == id_deuda), {})
        comprobar(
            "abono descuenta el saldo",
            fila.get("saldo_total") == "150000.00",
            str(fila.get("saldo_total")),
        )
        comprobar(
            "cuotas recalculadas",
            fila.get("cuotas_pendientes") == 3,
            str(fila.get("cuotas_pendientes")),
        )

        # --- Móvil ---------------------------------------------------------------
        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        verificar_donas(pagina, "móvil /presupuesto")
        ancho = pagina.evaluate(
            "() => ({scroll: document.documentElement.scrollWidth, view: window.innerWidth})"
        )
        comprobar(
            "sin desbordamiento horizontal /presupuesto",
            ancho["scroll"] <= ancho["view"],
            str(ancho),
        )

        pagina.goto(f"{BASE}/trabajos-extras")
        pagina.wait_for_load_state("networkidle")
        verificar_donas(pagina, "móvil /trabajos-extras")

        pagina.goto(f"{BASE}/chancucos")
        pagina.wait_for_load_state("networkidle")
        if pagina.locator(".tabla--atajos").count():
            th3m = pagina.locator(".tabla--atajos thead th:nth-child(3)").first.evaluate(
                "(e) => getComputedStyle(e).textAlign"
            )
            comprobar("cabeceras centradas en móvil", th3m == "center", th3m)

        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        abrir_abono(pagina, id_deuda)
        comprobar("modal abierto en móvil", pagina.locator("#modal-abono").is_visible())
        caja = pagina.locator("#modal-abono .app-modal__tarjeta").bounding_box()
        if caja:
            centro_caja = caja["x"] + caja["width"] / 2
            comprobar(
                "modal centrado en móvil",
                abs(centro_caja - 375 / 2) < 6,
                str(centro_caja),
            )
        pagina.locator("#modal-abono [data-abono-cancelar]").click()
        comprobar("cancelar cierra el modal", not pagina.locator("#modal-abono").is_visible())

        comprobar("sin errores de consola", not errores, "; ".join(errores[:3]))

        # --- Limpieza ------------------------------------------------------------
        if id_deuda:
            pagina.request.delete(f"{BASE}/api/deudas/{id_deuda}")
        for url, texto in (
            (f"{BASE}/finanzas", GASTO),
            (f"{BASE}/presupuesto", DEDUCCION),
        ):
            pagina.goto(url)
            pagina.wait_for_load_state("networkidle")
            if texto == GASTO:
                fila_gasto = pagina.locator(f"li.lista-gastos__item:has-text('{texto}')").first
                accion = fila_gasto.locator('form[action*="/editar"]').first.get_attribute("action")
            else:
                fila_deduccion = pagina.locator(f"li[data-deduccion-fila]:has-text('{texto}')").first
                accion = fila_deduccion.locator('form[action*="/editar"]').first.get_attribute("action")
            id_registro = _id_de_accion(accion)
            if id_registro:
                if texto == GASTO:
                    pagina.request.post(f"{BASE}/gastos/{id_registro}/eliminar")
                else:
                    pagina.request.post(f"{BASE}/presupuesto/deducciones/{id_registro}/eliminar")

        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    for nombre, ok, detalle in resultados:
        print(("PASS " if ok else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""))
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
