"""Gate QA de la SRS v4.37 en Chromium (web y móvil)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import Gasto, ProyeccionAhorro
from app.servicios import ahorro, gastos, pagos_metas, usuarios
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
META = "Viaje QA v437"
AVISO = (
    "No puedes eliminar una meta desde gastos fijos, "
    "debes hacerlo en el módulo de registro de metas."
)

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
    """Borra los datos sembrados.

    Returns:
        None. Hace el gate repetible.
    """
    with FabricaSesiones() as bd:
        for meta in bd.scalars(
            select(ProyeccionAhorro).where(ProyeccionAhorro.descripcion == META)
        ).all():
            bd.delete(meta)
        bd.commit()


def sembrar() -> None:
    """Crea la meta de prueba.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        ahorro.crear_proyeccion(
            bd, cuenta.id_usuario, "Créditos y Obligaciones", META, "300000",
            tipo_duracion="LIMITADO", meses=3,
        )
        pagos_metas.asegurar_gastos_de_metas(
            bd, cuenta.id_usuario, date.today().year, date.today().month
        )


def estilo(page, selector: str, propiedad: str) -> str:
    """Lee una propiedad computada.

    Args:
        page: Página de Playwright.
        selector: Selector CSS.
        propiedad: Propiedad.

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
    sembrar()
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
            contexto = navegador.new_context(
                viewport={"width": ancho, "height": 900}, service_workers="block"
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
            prefijo = f"{ancho}px"

            pagina.goto(f"{BASE}/finanzas")
            pagina.wait_for_load_state("networkidle")

            # Punto 1: X en meta abre el mismo modal, con Eliminar bloqueado.
            x_meta = pagina.locator(
                'button[data-omitir-gasto][data-es-meta="1"]'
            ).first
            comprobar(f"{prefijo}: X de meta presente", x_meta.count() >= 1)
            if x_meta.count():
                x_meta.click()
                pagina.wait_for_timeout(150)
                comprobar(
                    f"{prefijo}: modal unificado visible",
                    pagina.locator("#modal-omitir-gasto").is_visible(),
                )
                eliminar = pagina.locator("#modal-omitir-gasto [data-eliminar-confirmar]")
                comprobar(
                    f"{prefijo}: Eliminar bloqueado en meta",
                    eliminar.get_attribute("aria-disabled") == "true"
                    and "boton--deshabilitado" in (eliminar.get_attribute("class") or ""),
                    eliminar.get_attribute("class"),
                )
                comprobar(
                    f"{prefijo}: tooltip exacto",
                    eliminar.get_attribute("title") == AVISO,
                    eliminar.get_attribute("title"),
                )
                # `aria-disabled` no bloquea el clic real del usuario; Playwright
                # sí lo bloquea, por eso se fuerza el clic en el gate.
                eliminar.click(force=True)
                pagina.wait_for_timeout(150)
                cuerpo = " ".join(
                    pagina.locator("#modal-aviso-cuerpo").inner_text().split()
                )
                comprobar(f"{prefijo}: aviso al intentar", AVISO in cuerpo, cuerpo)
                # SRS v4.38: el aviso se cierra antes de seguir usando el modal.
                pagina.locator("#modal-aviso [data-aviso-entendido]").click()
                pagina.wait_for_timeout(150)

                # Punto 1b: Omitir pago en la meta.
                with pagina.expect_navigation(wait_until="networkidle", timeout=10000):
                    pagina.locator("#modal-omitir-gasto [data-omitir-confirmar]").click()

            # Punto 2: Habilitar reemplaza a Abonar y reactiva de inmediato.
            # El alcance es la meta del gate: otros datos de prueba pueden tener
            # ítems omitidos propios.
            selector_habilitar = (
                f'li.lista-gastos__item:has-text("{META}") [data-habilitar-gasto]'
            )
            habilitar = pagina.locator(selector_habilitar)
            comprobar(f"{prefijo}: botón Habilitar visible", habilitar.count() >= 1)
            if habilitar.count():
                with pagina.expect_navigation(wait_until="networkidle", timeout=10000):
                    habilitar.first.click()
                comprobar(
                    f"{prefijo}: meta reactivada",
                    pagina.locator(selector_habilitar).count() == 0,
                )

            # Punto 3: modal Editar gasto sólido y al frente.
            editar = pagina.locator('summary.boton-circular--editar').first
            if editar.count():
                editar.click()
                pagina.wait_for_timeout(150)
                tarjeta = pagina.locator(
                    "details.edicion-gasto--modal[open] .edicion-gasto__formulario"
                ).first
                comprobar(
                    f"{prefijo}: Editar gasto sólido",
                    estilo(pagina, "details.edicion-gasto--modal[open] .edicion-gasto__formulario", "backgroundColor")
                    == "rgb(30, 41, 59)",
                )
                comprobar(
                    f"{prefijo}: z-index 9002",
                    estilo(pagina, "details.edicion-gasto--modal[open] .edicion-gasto__formulario", "zIndex")
                    == "9002",
                )
                tarjeta.locator("[data-cancelar-edicion]").first.click()

            # Punto 4: íconos en títulos y pestañas limpias.
            for ruta in ("/presupuesto", "/chancucos", "/finanzas/historial"):
                pagina.goto(f"{BASE}{ruta}")
                pagina.wait_for_load_state("networkidle")
                comprobar(
                    f"{prefijo}: ícono en {ruta}",
                    pagina.locator(".heroe__titulo-icono").count() >= 1,
                )
                comprobar(
                    f"{prefijo}: pestañas limpias en {ruta}",
                    pagina.locator(".subnav-finanzas__icono").count() == 0,
                )

            comprobar(f"{prefijo}: sin errores", not errores, "; ".join(errores[:2]))
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
