"""Gate QA de la SRS v4.41: paridad de acciones en Trabajos Extras."""

from __future__ import annotations

from datetime import date

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Gasto, TrabajoExtra
from app.servicios import trabajos, usuarios

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
TRABAJO = "Trabajo QA v441"
GASTO = "Gasto fijo QA v441"

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado.
        detalle: Información adicional.
    """
    resultados.append((nombre, bool(condicion), detalle))
    print(("PASS " if condicion else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""), flush=True)


def limpiar() -> None:
    """Elimina los datos sembrados.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        bd.query(Gasto).filter(Gasto.descripcion == GASTO).delete(
            synchronize_session=False
        )
        bd.query(TrabajoExtra).filter(TrabajoExtra.descripcion == TRABAJO).delete(
            synchronize_session=False
        )
        bd.commit()


def sembrar() -> None:
    """Crea el contrato y su gasto fijo.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        trabajo = trabajos.crear_trabajo(
            bd, cuenta.id_usuario, TRABAJO, "1200000", date.today()
        )
        trabajos.crear_gasto_trabajo(
            bd, cuenta.id_usuario, trabajo.id_trabajo, "Vivienda", GASTO, "180000"
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

            pagina.goto(f"{BASE}/trabajos-extras")
            pagina.wait_for_load_state("networkidle")
            fila = pagina.locator(f'li.lista-gastos__item:has-text("{GASTO}")').first
            comprobar(f"{prefijo}: fila del gasto visible", fila.count() == 1)
            comprobar(
                f"{prefijo}: lápiz de editar",
                fila.locator("summary.boton-circular--editar").count() == 1,
            )
            comprobar(
                f"{prefijo}: X de omitir/eliminar",
                fila.locator("button[data-omitir-gasto]").count() == 1,
            )
            comprobar(
                f"{prefijo}: check de pago",
                fila.locator("form[data-check-gasto] button[type=submit]").count() == 1,
            )
            comprobar(
                f"{prefijo}: limpiar checks del trabajo",
                pagina.locator('button:has-text("Limpiar checks de este trabajo")').count()
                >= 1,
            )

            # Editar abre el mismo modal de Mis Finanzas.
            lapiz = fila.locator("summary.boton-circular--editar").first
            lapiz.scroll_into_view_if_needed()
            lapiz.click()
            pagina.wait_for_timeout(150)
            modal = pagina.locator(
                "details.edicion-gasto--modal[open] > .edicion-gasto__formulario"
            ).first
            comprobar(f"{prefijo}: modal Editar", modal.is_visible())
            texto = modal.inner_text()
            comprobar(
                f"{prefijo}: modal con Actualizar y sin Cancelar",
                "Actualizar" in texto and "Cancelar" not in texto,
                texto[:120],
            )
            modal.locator("[data-cancelar-edicion]").first.click()
            pagina.wait_for_timeout(150)

            # Marcar ✔ y limpiar checks, sin salir de Trabajos Extras.
            fila = pagina.locator(f'li.lista-gastos__item:has-text("{GASTO}")').first
            check = fila.locator('form[data-accion="marcar"] button[type="submit"]').first
            if check.count():
                # Optimistic UI: cambia el DOM al instante, sin navegar.
                check.click()
                pagina.wait_for_timeout(400)
                comprobar(
                    f"{prefijo}: ✔ marcado",
                    pagina.locator(
                        f'li.lista-gastos__item:has-text("{GASTO}") form[data-accion="desmarcar"]'
                    ).count()
                    == 1,
                )
            limpiar_checks = pagina.locator(
                'button:has-text("Limpiar checks de este trabajo")'
            ).first
            if limpiar_checks.count():
                limpiar_checks.click()
                pagina.wait_for_timeout(150)
                pagina.locator("#modal-confirmacion [data-confirm-aceptar]").click()
                pagina.wait_for_load_state("networkidle")
                comprobar(
                    f"{prefijo}: checks limpios",
                    pagina.locator(
                        f'li.lista-gastos__item:has-text("{GASTO}") form[data-accion="marcar"]'
                    ).count()
                    == 1,
                )
                comprobar(
                    f"{prefijo}: permanece en Trabajos Extras",
                    "/trabajos-extras" in pagina.url,
                    pagina.url,
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
