"""Gate QA de la SRS v4.40: modal sin Cancelar, X y «Limpiar checks» visible."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Gasto
from app.servicios import gastos, usuarios

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
DESC = "Gasto QA v440"

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado.
        detalle: Información extra.
    """
    resultados.append((nombre, bool(condicion), detalle))
    print(("PASS " if condicion else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""), flush=True)


def limpiar() -> None:
    """Borra el gasto sembrado.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        bd.query(Gasto).filter(Gasto.descripcion == DESC).delete(
            synchronize_session=False
        )
        bd.commit()


def sembrar() -> None:
    """Crea el gasto de prueba.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        gastos.crear_gasto(
            bd, cuenta.id_usuario, "Vivienda", DESC, "175000", date.today(),
            es_fijo=True,
        )


def main() -> None:
    """Ejecuta el recorrido en Web y Móvil.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
            limpiar()
            sembrar()
            contexto = navegador.new_context(
                viewport={"width": ancho, "height": 900}, service_workers="block"
            )
            errores: list[str] = []
            contexto.on(
                "page",
                lambda p: p.on(
                    "console",
                    lambda m: errores.append(m.text) if m.type == "error" else None,
                ),
            )
            pagina = contexto.new_page()
            pagina.goto(f"{BASE}/login")
            pagina.fill("#campo-correo", CORREO)
            pagina.fill("#campo-clave", CLAVE)
            pagina.locator('form[action="/login"] button[type="submit"]').first.click()
            pagina.wait_for_load_state("networkidle")
            prefijo = f"{ancho}px"

            pagina.goto(f"{BASE}/finanzas")
            pagina.wait_for_load_state("networkidle")

            # SRS v4.40: «Limpiar checks» visible en la primera carga.
            limpiar_checks = pagina.locator('button:has-text("Limpiar checks")')
            comprobar(
                f"{prefijo}: Limpiar checks visible al entrar",
                limpiar_checks.count() >= 1 and limpiar_checks.first.is_visible(),
                f"botones={limpiar_checks.count()}",
            )

            # SRS v4.39: modal sin Cancelar, X arriba a la derecha y Actualizar centrado.
            x = pagina.locator(
                f'li.lista-gastos__item:has-text("{DESC}") button[data-omitir-gasto]'
            ).first
            x.scroll_into_view_if_needed()
            pagina.wait_for_timeout(100)
            antes = pagina.evaluate("() => Math.round(scrollY)")
            x.click()
            pagina.wait_for_timeout(150)
            modal = pagina.locator("#modal-omitir-gasto")
            comprobar(f"{prefijo}: modal de la X visible", modal.is_visible())
            pagina.locator("#modal-omitir-gasto [data-omitir-cancelar]").click()
            pagina.wait_for_timeout(150)

            lapiz = pagina.locator(
                f'li.lista-gastos__item:has-text("{DESC}") summary.boton-circular--editar'
            ).first
            lapiz.scroll_into_view_if_needed()
            pagina.wait_for_timeout(100)
            antes = pagina.evaluate("() => Math.round(scrollY)")
            lapiz.click()
            pagina.wait_for_timeout(150)
            tarjeta = pagina.locator(
                "details.edicion-gasto--modal[open] > .edicion-gasto__formulario"
            ).first
            texto = tarjeta.inner_text()
            comprobar(
                f"{prefijo}: sin Cancelar en Editar",
                "Cancelar" not in texto,
                texto[:140],
            )
            cerrar_x = tarjeta.locator("[data-cancelar-edicion]").first
            caja = tarjeta.bounding_box()
            cierre = cerrar_x.bounding_box()
            comprobar(
                f"{prefijo}: X de cierre arriba a la derecha",
                bool(caja and cierre)
                and cierre["x"] > caja["x"] + caja["width"] / 2
                and cierre["y"] < caja["y"] + 60,
                f"cierre={cierre} caja={caja}",
            )
            actualizar = tarjeta.locator('button[type="submit"]').first
            pie = tarjeta.locator(".acciones-formulario--gasto").first
            centro_pie = pie.bounding_box()
            centro_boton = actualizar.bounding_box()
            comprobar(
                f"{prefijo}: Actualizar centrado",
                bool(centro_pie and centro_boton)
                and abs(
                    (centro_boton["x"] + centro_boton["width"] / 2)
                    - (centro_pie["x"] + centro_pie["width"] / 2)
                )
                <= 40,
                f"boton={centro_boton} pie={centro_pie}",
            )
            cerrar_x.click()
            pagina.wait_for_timeout(200)
            comprobar(
                f"{prefijo}: scroll al cerrar Editar",
                abs(pagina.evaluate("() => Math.round(scrollY)") - antes) <= 8,
                f"{antes} -> {pagina.evaluate('() => Math.round(scrollY)')}",
            )

            # SRS v4.40: Eliminar conserva la posición exacta.
            pagina.evaluate(
                "(y) => window.scrollTo({ top: y, left: 0, behavior: 'instant' })",
                antes,
            )
            pagina.wait_for_timeout(100)
            x = pagina.locator(
                f'li.lista-gastos__item:has-text("{DESC}") button[data-omitir-gasto]'
            ).first
            x.scroll_into_view_if_needed()
            pagina.wait_for_timeout(100)
            x.click()
            pagina.wait_for_timeout(150)
            pagina.evaluate(
                """() => {
                  document.querySelector(
                    '#modal-omitir-gasto [data-eliminar-confirmar]'
                  ).addEventListener('click', function () {
                    sessionStorage.setItem(
                      'qa_scroll_click_y', String(Math.round(scrollY))
                    );
                  }, { capture: true, once: true });
                }"""
            )
            with pagina.expect_navigation(wait_until="networkidle", timeout=15000):
                pagina.locator(
                    "#modal-omitir-gasto [data-eliminar-confirmar]"
                ).click()
            marcado = int(
                pagina.evaluate("() => sessionStorage.getItem('qa_scroll_click_y') || '0'")
            )
            despues = pagina.evaluate("() => Math.round(scrollY)")
            comprobar(
                f"{prefijo}: scroll exacto tras Eliminar",
                despues > 0 and abs(despues - marcado) <= 8,
                f"{marcado} -> {despues}",
            )

            comprobar(f"{prefijo}: sin errores", not errores, "; ".join(errores[:2]))
            contexto.close()
        navegador.close()

    limpiar()
    fallos = [fila for fila in resultados if not fila[1]]
    for nombre, ok, detalle in resultados:
        print(("PASS " if ok else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""))
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
