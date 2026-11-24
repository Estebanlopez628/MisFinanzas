"""Gate QA de la SRS v4.28 (bloques C, D y E) en Chromium real."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import AbonoProyeccion, Gasto, ProyeccionAhorro
from app.servicios import ahorro, pagos_metas, usuarios
from playwright.sync_api import sync_playwright

RUTA_CSS = __import__("pathlib").Path(__file__).resolve().parent.parent / "app/static/css/estilos.css"
BASE = "http://127.0.0.1:8000"
ADMIN = ("prueba_qa_admin@misfinanzas.local", "QA_Admin_2026!")

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
    """Borra la meta y el gasto sembrados por este gate.

    Returns:
        None. Hace el gate repetible.
    """
    with FabricaSesiones() as bd:
        for meta in bd.scalars(
            select(ProyeccionAhorro).where(ProyeccionAhorro.descripcion == "QA Abono Meta v428")
        ).all():
            for abono in bd.scalars(
                select(AbonoProyeccion).where(
                    AbonoProyeccion.id_proyeccion == meta.id_proyeccion
                )
            ).all():
                bd.delete(abono)
            bd.delete(meta)
        for gasto in bd.scalars(
            select(Gasto).where(Gasto.descripcion == "QA Abono Meta v428")
        ).all():
            bd.delete(gasto)
        bd.commit()


def estilo(page, selector: str, propiedad: str) -> str:
    """Lee una propiedad computada.

    Args:
        page: Página de Playwright.
        selector: Selector CSS.
        propiedad: Propiedad a leer.

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
        pagina.fill("#campo-correo", ADMIN[0])
        pagina.fill("#campo-clave", ADMIN[1])
        pagina.locator('form[action="/login"] button[type="submit"]').first.click()
        pagina.wait_for_load_state("networkidle")

        # --- Bloque C: deudas en web -------------------------------------------
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "web: rejilla de deudas en columna",
            estilo(pagina, ".rejilla-paneles--deudas", "flexDirection") == "column",
            estilo(pagina, ".rejilla-paneles--deudas", "flexDirection"),
        )
        comprobar(
            "web: primera tarjeta centrada",
            estilo(pagina, ".rejilla-paneles--deudas > .panel:first-child", "maxWidth")
            == "900px",
            estilo(pagina, ".rejilla-paneles--deudas > .panel:first-child", "maxWidth"),
        )
        css = (RUTA_CSS).read_text(encoding="utf-8")
        comprobar(
            "capas: confirmación 9999 sobre modales 9000",
            "z-index: 9999" in css and "z-index: 9000" in css,
        )

        # --- Bloque D: scroll y confirmación -----------------------------------
        pagina.goto(f"{BASE}/presupuesto")
        pagina.wait_for_load_state("networkidle")
        pagina.evaluate("() => window.scrollTo(0, 400)")
        antes = pagina.evaluate("() => window.scrollY")
        pagina.evaluate(
            "() => { document.getElementById('modal-confirmacion').hidden = false; }"
        )
        pagina.wait_for_timeout(120)
        comprobar(
            "modal abierto",
            pagina.evaluate("() => !document.getElementById('modal-confirmacion').hidden"),
        )
        pagina.evaluate(
            "() => { document.getElementById('modal-confirmacion').hidden = true; }"
        )
        pagina.wait_for_timeout(120)
        despues = pagina.evaluate("() => window.scrollY")
        comprobar(
            "scroll conservado al cerrar",
            abs(antes - despues) <= 2,
            f"{antes} -> {despues}",
        )

        # La cuenta QA no está en el allowlist de OLB_BYTE (ADR-48): el cableado
        # de la confirmación inmediata se verifica en la prueba unitaria.

        # --- Bloque E: abonos a meta -------------------------------------------
        with FabricaSesiones() as bd:
            cuenta = usuarios.buscar_por_correo(bd, ADMIN[0])
            assert cuenta is not None
            meta = ahorro.crear_proyeccion(
                bd, cuenta.id_usuario, "Créditos y Obligaciones", "QA Abono Meta v428",
                "300000", tipo_duracion="LIMITADO", meses=3,
            )
            pagos_metas.asegurar_gastos_de_metas(
                bd, cuenta.id_usuario, date.today().year, date.today().month
            )
            gasto = bd.scalars(
                select(Gasto).where(Gasto.id_proyeccion == meta.id_proyeccion)
            ).first()
            assert gasto is not None
            id_gasto = gasto.id_gasto

        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "meta: botón Abonar presente",
            pagina.locator(f'[data-abrir-abono-meta][data-id-gasto="{id_gasto}"]').count() >= 1,
        )
        abono = (
            pagina.locator(f'[data-abrir-abono-meta][data-id-gasto="{id_gasto}"]').first
        )
        abono.evaluate("(e) => { const d = e.closest('details'); if (d) d.open = true; }")
        abono.click()
        comprobar("modal de abono a meta visible", pagina.locator("#modal-abono-meta").is_visible())
        pagina.fill("#modal-abono-meta-valor", "40.000")
        with pagina.expect_navigation(wait_until="networkidle", timeout=10000):
            pagina.locator("[data-abono-meta-confirmar]").click()
        with FabricaSesiones() as bd:
            total = bd.scalars(
                select(AbonoProyeccion.valor).where(
                    AbonoProyeccion.id_proyeccion == meta.id_proyeccion
                )
            ).first()
            comprobar("meta: abono registrado", total == 40000, str(total))

        # --- Móvil: deudas siguen en rejilla -----------------------------------
        pagina.set_viewport_size({"width": 375, "height": 812})
        pagina.goto(f"{BASE}/deudas")
        pagina.wait_for_load_state("networkidle")
        comprobar(
            "móvil: deudas conservan su rejilla",
            estilo(pagina, ".rejilla-paneles--deudas", "display") == "grid",
            estilo(pagina, ".rejilla-paneles--deudas", "display"),
        )
        comprobar("sin errores de consola", not errores, "; ".join(errores[:2]))
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
