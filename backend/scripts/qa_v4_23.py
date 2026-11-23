"""Gate QA breve de la SRS v4.23 en Chromium real (web y móvil).

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_23
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import AbonoDeuda, Deuda, PagoDeuda
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
ACREEDOR = "QA Barras v423"

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


def verificar(page, etiqueta: str) -> None:
    """Comprueba fecha compacta, texto sin recorte y fondo en la vista actual.

    Args:
        page: Página de Playwright.
        etiqueta: Prefijo para el informe.
    """
    fecha = page.locator(".impacto-deuda__fecha").first.inner_text()
    comprobar(
        f"{etiqueta}: fecha compacta MM/AAAA",
        bool(re.fullmatch(r"\d{2}/\d{4}", fecha.strip())),
        fecha,
    )
    comprobar(
        f"{etiqueta}: sin nombre de mes largo",
        not any(
            mes in fecha
            for mes in (
                "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
            )
        ),
        fecha,
    )
    recorte = page.locator(".impacto-deuda__fecha").first.evaluate(
        "(e) => ({scroll: e.scrollWidth, client: e.clientWidth})"
    )
    comprobar(
        f"{etiqueta}: fecha sin recorte",
        recorte["scroll"] <= recorte["client"] + 1,
        str(recorte),
    )
    barra = page.locator(".impacto-deuda__barra--base").first.evaluate(
        "(e) => ({scroll: e.scrollWidth, client: e.clientWidth})"
    )
    comprobar(
        f"{etiqueta}: barra sin recorte",
        barra["scroll"] <= barra["client"] + 1,
        str(barra),
    )
    fondo = page.locator(".impacto-deudas").first.evaluate(
        "(e) => getComputedStyle(e).backgroundColor"
    )
    comprobar(
        f"{etiqueta}: fondo de velocímetros",
        fondo == "rgba(15, 23, 42, 0.55)",
        fondo,
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
                "descripcion": "Deuda de prueba barras",
                "saldo_total": "197.568",
                "cuota": "16.464",
                "cuotas_pendientes": "12",
                "periodicidad": "MENSUAL",
            },
        )

        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        verificar(pagina, "web")

        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        verificar(pagina, "móvil")
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
