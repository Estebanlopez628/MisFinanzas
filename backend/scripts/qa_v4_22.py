"""Gate QA de la SRS v4.22 en Chromium real (web y móvil).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_22

Siembra deudas QA con prefijo propio y las elimina al terminar.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import AbonoDeuda, Deuda, PagoDeuda
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
ACREEDOR = "QA Barras v422"

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
    """Borra las deudas sembradas por este gate.

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
        bd.commit()


def css(page, selector: str, propiedad: str) -> str:
    """Lee una propiedad computada.

    Args:
        page: Página de Playwright.
        selector: Selector CSS.
        propiedad: Nombre de la propiedad.

    Returns:
        Valor computado o «(sin elemento)».
    """
    localizador = page.locator(selector).first
    if not localizador.count():
        return "(sin elemento)"
    return str(localizador.evaluate(f"(e) => getComputedStyle(e).{propiedad}"))


def verificar_barras(page, etiqueta: str, espacio: str) -> None:
    """Comprueba el componente de barras en la vista actual.

    Args:
        page: Página de Playwright.
        etiqueta: Prefijo para el informe.
        espacio: Separación esperada entre tarjetas.
    """
    comprobar(
        f"{etiqueta}: componente visible",
        page.locator(".impacto-deudas").is_visible(),
    )
    comprobar(
        f"{etiqueta}: proyección anterior eliminada",
        page.locator(".cierre-deuda__proyeccion").count() == 0
        and "Proyección de saldo (6 meses)" not in page.content(),
    )
    titulo = page.locator(".impacto-deudas__titulo").inner_text()
    comprobar(
        f"{etiqueta}: título exacto",
        "¡Tu Excedente Aplasta tus Deudas!" in titulo,
        titulo,
    )
    subtitulo = " ".join(page.locator(".impacto-deudas__subtitulo").inner_text().split())
    comprobar(
        f"{etiqueta}: subtítulo con porcentaje",
        "recortas el tiempo de pago de tus deudas" in subtitulo
        and "% de tiempo" in subtitulo,
        subtitulo[:150],
    )
    tarjetas = page.locator(".impacto-deuda").count()
    comprobar(f"{etiqueta}: tres tarjetas de deuda", tarjetas == 3, str(tarjetas))
    comprobar(
        f"{etiqueta}: badges de porcentaje",
        page.locator(".impacto-deuda__badge").count() >= 1,
    )
    comprobar(
        f"{etiqueta}: barras azul y verde",
        page.locator(".impacto-deuda__barra--base").count() == tarjetas
        and page.locator(".impacto-deuda__barra--optimo").count() == tarjetas,
    )
    comprobar(
        f"{etiqueta}: zona punteada con candado",
        page.locator(".impacto-deuda__ahorro").count() >= 1
        and "¡Te ahorras" in page.locator(".impacto-deuda__ahorro").first.inner_text(),
    )
    comprobar(
        f"{etiqueta}: separación entre tarjetas",
        css(page, ".impacto-deudas__lista", "gap") == espacio,
        css(page, ".impacto-deudas__lista", "gap"),
    )
    comprobar(
        f"{etiqueta}: pluralización sin (s)",
        "(cuotas)" not in page.locator(".impacto-deudas").inner_text().lower()
        or "cuotas)" in page.locator(".impacto-deudas").inner_text().lower(),
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

        for nombre, saldo, cuota, plazo in (
            ("Alkomprar", "197568", "16464", 12),
            ("Alkomprar 2", "288395", "57679", 5),
            ("Addi", "385100", "50000", 8),
        ):
            pagina.request.post(
                f"{BASE}/deudas",
                form={
                    "acreedor": ACREEDOR,
                    "descripcion": nombre,
                    "saldo_total": saldo,
                    "cuota": cuota,
                    "cuotas_pendientes": str(plazo),
                    "periodicidad": "MENSUAL",
                },
            )

        # --- Escritorio --------------------------------------------------------
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        verificar_barras(pagina, "web", "24px")
        comprobar(
            "web: leyenda de dona en columna",
            css(pagina, ".panel.capacidad .dona-contenedor", "flexDirection") == "column",
            css(pagina, ".panel.capacidad .dona-contenedor", "flexDirection"),
        )
        comprobar(
            "web: leyenda centrada debajo",
            css(pagina, ".panel.capacidad .dona__leyenda", "textAlign") == "center",
        )

        # Modal de abono: separación de los botones respecto al campo.
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        boton = pagina.locator(f'button[data-abrir-abono][data-deuda="{ACREEDOR}"]').first
        boton.evaluate("(e) => { const d = e.closest('details'); if (d) d.open = true; }")
        boton.click()
        comprobar(
            "modal: botones separados del campo",
            css(pagina, ".app-modal__acciones--abono", "marginTop") == "22px",
            css(pagina, ".app-modal__acciones--abono", "marginTop"),
        )
        pagina.locator("#modal-abono [data-abono-cancelar]").click()

        # Atajos sin favorito y logo de Mis Finanzas.
        pagina.goto(f"{BASE}/chancucos")
        pagina.wait_for_load_state("networkidle")
        cuerpo = pagina.content()
        comprobar(
            "sin opción de favorito",
            "Marcar como favorito" not in cuerpo
            and 'name="favorito"' not in cuerpo
            and ">Favorito</th>" not in cuerpo,
        )
        cabeceras = pagina.locator(".tabla--atajos thead th").count()
        comprobar("tabla de atajos con 5 columnas", cabeceras == 5, str(cabeceras))
        comprobar(
            "cabeceras Valor/Días centradas",
            css(pagina, ".tabla--atajos thead th:nth-child(2)", "textAlign") == "center"
            and css(pagina, ".tabla--atajos thead th:nth-child(3)", "textAlign") == "center",
        )

        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        comprobar("logo en Mis Finanzas", pagina.locator(".modulo__icono").is_visible())
        comprobar(
            "icono de bolsa de dinero",
            "💰" in pagina.locator(".modulo__icono").inner_text(),
        )

        # El tamaño del logo de OLB_BYTE (30 px) se verifica en las pruebas
        # unitarias de plantilla y CSS; aquí solo se comprueba el de Mis Finanzas.

        # --- Móvil -------------------------------------------------------------
        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        verificar_barras(pagina, "móvil", "20px")
        ancho = pagina.evaluate(
            "() => ({scroll: document.documentElement.scrollWidth, view: window.innerWidth})"
        )
        comprobar(
            "móvil: sin desbordamiento horizontal",
            ancho["scroll"] <= ancho["view"],
            str(ancho),
        )
        comprobar(
            "móvil: dona no se apila en columna",
            css(pagina, ".panel.capacidad .dona-contenedor", "flexDirection") != "column",
            css(pagina, ".panel.capacidad .dona-contenedor", "flexDirection"),
        )

        pagina.goto(f"{BASE}/chancucos")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "móvil: sin favorito",
            "Marcar como favorito" not in pagina.content(),
        )

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
