"""Gate QA de la SRS v4.24 en Chromium real (web y móvil).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_24
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import AbonoDeuda, Deuda, PagoDeuda
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
ACREEDOR = "QA Barras v424"

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
    """Borra la deuda sembrada por este gate.

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


def estilo(page, selector: str, propiedad: str) -> str:
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
                "descripcion": "Deuda de prueba badges",
                "saldo_total": "197.568",
                "cuota": "16.464",
                "cuotas_pendientes": "12",
                "periodicidad": "MENSUAL",
            },
        )
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")

        descripcion = " ".join(
            pagina.locator(".impacto-deuda__nombre").first.inner_text().split()
        )
        comprobar("sin «/mes» en la cuota", "/mes" not in descripcion, descripcion)

        comprobar(
            "web: badge en cabecera",
            pagina.locator(".impacto-deuda__badge--web").first.is_visible(),
        )
        comprobar(
            "web: badge móvil oculto",
            not pagina.locator(".impacto-deuda__badge--movil").first.is_visible(),
        )

        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "móvil: badge junto a «Pago mínimo»",
            pagina.locator(
                ".impacto-deuda__etiqueta-grupo .impacto-deuda__badge--movil"
            ).first.is_visible(),
        )
        comprobar(
            "móvil: badge de cabecera oculto",
            not pagina.locator(".impacto-deuda__badge--web").first.is_visible(),
        )

        propiedades = ("backgroundColor", "color", "fontSize", "borderRadius", "textAlign")
        for propiedad in propiedades:
            pill = estilo(pagina, ".cierre-deuda__pill", propiedad)
            subtitulo = estilo(pagina, ".impacto-deudas__subtitulo", propiedad)
            comprobar(
                f"móvil: subtítulo = banner ({propiedad})",
                pill == subtitulo,
                f"{pill} vs {subtitulo}",
            )

        ancho_vel = pagina.locator(".cierre-deuda__velocimetros").first.evaluate(
            "(e) => Math.round(e.getBoundingClientRect().width)"
        )
        ancho_grafica = pagina.locator(".impacto-deudas").first.evaluate(
            "(e) => Math.round(e.getBoundingClientRect().width)"
        )
        comprobar(
            "móvil: gráfica y velocímetros alineados",
            ancho_vel == ancho_grafica,
            f"{ancho_vel} vs {ancho_grafica}",
        )
        ancho = pagina.evaluate(
            "() => ({scroll: document.documentElement.scrollWidth, view: window.innerWidth})"
        )
        comprobar(
            "móvil: sin desbordamiento horizontal",
            ancho["scroll"] <= ancho["view"],
            str(ancho),
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
