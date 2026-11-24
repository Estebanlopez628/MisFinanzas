"""Gate QA de la SRS v4.38: emojis de color y scroll exacto (web y móvil)."""

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
META = "Meta scroll QA v438"
META_X = "Meta X QA v438"
SUSPENDIDO = "Gasto suspendido QA v438"
ELIMINAR = "Gasto eliminar QA v438"
DESCRIPCIONES = (META, META_X, SUSPENDIDO, ELIMINAR)
AVISO = (
    "No puedes eliminar una meta desde gastos fijos, "
    "debes hacerlo en el módulo de registro de metas."
)
EMOJIS = {
    "/presupuesto": "🧾",
    "/chancucos": "🔗",
    "/finanzas/historial": "📜",
}

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación del gate.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado de la comprobación.
        detalle: Información adicional para el informe.
    """
    resultados.append((nombre, bool(condicion), detalle))
    print(("PASS " if condicion else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""), flush=True)


def limpiar() -> None:
    """Elimina los datos sembrados para que el gate sea repetible.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        bd.query(Gasto).filter(Gasto.descripcion.in_(DESCRIPCIONES)).delete(
            synchronize_session=False
        )
        bd.query(ProyeccionAhorro).filter(
            ProyeccionAhorro.descripcion.in_((META, META_X))
        ).delete(synchronize_session=False)
        bd.commit()


def sembrar() -> None:
    """Crea la meta inhabilitada y los gastos de prueba.

    Returns:
        None.
    """
    hoy = date.today()
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        ahorro.crear_proyeccion(
            bd, cuenta.id_usuario, "Créditos y Obligaciones", META, "300000",
            tipo_duracion="LIMITADO", meses=3,
        )
        meta = bd.scalars(
            select(ProyeccionAhorro).where(ProyeccionAhorro.descripcion == META)
        ).first()
        assert meta is not None
        pagos_metas.asegurar_gastos_de_metas(
            bd, cuenta.id_usuario, hoy.year, hoy.month
        )
        gasto_meta = bd.scalars(
            select(Gasto).where(Gasto.id_proyeccion == meta.id_proyeccion)
        ).first()
        assert gasto_meta is not None
        pagos_metas.omitir_pago(bd, cuenta.id_usuario, gasto_meta.id_gasto, hoy)

        ahorro.crear_proyeccion(
            bd, cuenta.id_usuario, "Créditos y Obligaciones", META_X, "180000",
            tipo_duracion="LIMITADO", meses=2,
        )
        meta_x = bd.scalars(
            select(ProyeccionAhorro).where(ProyeccionAhorro.descripcion == META_X)
        ).first()
        assert meta_x is not None
        pagos_metas.asegurar_gastos_de_metas(
            bd, cuenta.id_usuario, hoy.year, hoy.month
        )

        suspendido = gastos.crear_gasto(
            bd, cuenta.id_usuario, "Vivienda", SUSPENDIDO, "450000", hoy,
            es_fijo=True,
        )
        pagos_metas.omitir_pago(
            bd, cuenta.id_usuario, suspendido.id_gasto, hoy
        )
        gastos.crear_gasto(
            bd, cuenta.id_usuario, "Vivienda", ELIMINAR, "320000", hoy,
            es_fijo=True,
        )


def estilo(pagina, selector: str, propiedad: str) -> str:
    """Lee una propiedad computada del primer elemento.

    Args:
        pagina: Página de Playwright.
        selector: Selector CSS.
        propiedad: Propiedad a consultar.

    Returns:
        Valor computado o «(sin elemento)».
    """
    localizador = pagina.locator(selector).first
    if not localizador.count():
        return "(sin elemento)"
    return str(localizador.evaluate(f"(e) => getComputedStyle(e).{propiedad}"))


def scroll_y(pagina) -> int:
    """Devuelve la posición vertical actual.

    Args:
        pagina: Página de Playwright.

    Returns:
        Desplazamiento vertical en píxeles.
    """
    return int(pagina.evaluate("() => Math.round(window.scrollY || 0)"))


def desplazar(pagina, y: int) -> None:
    """Coloca la página en una posición intermedia de forma instantánea.

    Args:
        pagina: Página de Playwright.
        y: Posición vertical deseada.
    """
    pagina.evaluate(
        "(y) => window.scrollTo({ top: y, left: 0, behavior: 'instant' })", y
    )
    pagina.wait_for_timeout(120)


def antes_del_clic(pagina, localizador) -> int:
    """Deja el control visible y devuelve la posición real antes del clic.

    Args:
        pagina: Página de Playwright.
        localizador: Control que se va a pulsar.

    Returns:
        Posición vertical inmediatamente anterior al clic.
    """
    localizador.scroll_into_view_if_needed()
    pagina.wait_for_timeout(100)
    return scroll_y(pagina)


def marcar_scroll_al_clic(pagina, selector: str, texto: str = "") -> None:
    """Registra la posición real en el instante del clic.

    Args:
        pagina: Página de Playwright.
        selector: Selector CSS válido en el navegador.
        texto: Fragmento opcional para elegir el control dentro de su fila.
    """
    pagina.evaluate(
        """(args) => {
          var controles = Array.from(document.querySelectorAll(args.selector));
          var control = args.texto
            ? controles.find(function (boton) {
                var fila = boton.closest("li");
                return fila && fila.textContent.indexOf(args.texto) !== -1;
              }) || controles[0]
            : controles[0];
          if (!control) return;
          control.addEventListener("click", function () {
            sessionStorage.setItem(
              "qa_scroll_click_y", String(Math.round(window.scrollY || 0))
            );
          }, { capture: true, once: true });
        }""",
        {"selector": selector, "texto": texto},
    )


def scroll_marcado(pagina) -> int:
    """Lee y limpia la posición registrada en el clic.

    Args:
        pagina: Página de Playwright.

    Returns:
        Posición vertical marcada, o cero si no hubo marca.
    """
    return int(
        pagina.evaluate(
            """() => {
              var valor = sessionStorage.getItem("qa_scroll_click_y") || "0";
              sessionStorage.removeItem("qa_scroll_click_y");
              return valor;
            }"""
        )
    )


def comprobar_scroll(
    nombre: str, pagina, antes: int, despues: int, tolerancia: int = 8
) -> None:
    """Comprueba que se restauró la posición, con el tope real de la página.

    Args:
        nombre: Etiqueta de la comprobación.
        pagina: Página de Playwright.
        antes: Posición antes de la acción.
        despues: Posición después de la acción.
        tolerancia: Margen permitido por la acción de clic del automatismo.
    """
    maximo = pagina.evaluate(
        "() => Math.max(0, document.scrollingElement.scrollHeight - innerHeight)"
    )
    esperado = min(antes, maximo)
    comprobar(
        nombre,
        despues > 0 and abs(despues - esperado) <= tolerancia,
        f"{antes} -> {despues} (tope {maximo})",
    )


def main() -> None:
    """Ejecuta el recorrido completo del gate.

    Returns:
        None. Imprime el informe y falla si hay comprobaciones malas.
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

            # Punto 4: emojis a todo color en los títulos grandes.
            for ruta, emoji in EMOJIS.items():
                pagina.goto(f"{BASE}{ruta}")
                pagina.wait_for_load_state("networkidle")
                icono = pagina.locator(".heroe__titulo-icono").first
                comprobar(
                    f"{prefijo}: emoji en {ruta}",
                    icono.count() == 1 and icono.inner_text().strip() == emoji,
                    icono.inner_text().strip() if icono.count() else "(sin icono)",
                )
                comprobar(
                    f"{prefijo}: sin SVG en {ruta}",
                    pagina.locator(".heroe__titulo-icono svg").count() == 0,
                )
                comprobar(
                    f"{prefijo}: pestañas limpias en {ruta}",
                    pagina.locator(".subnav-finanzas__icono").count() == 0,
                )

            pagina.goto(f"{BASE}/finanzas")
            pagina.wait_for_load_state("networkidle")
            comprobar(
                f"{prefijo}: Mis Finanzas conserva 💰",
                "💰" in pagina.locator(".heroe__titulo").first.inner_text(),
            )

            maximo = pagina.evaluate(
                "() => Math.max(0, document.scrollingElement.scrollHeight - innerHeight)"
            )
            y = min(900, max(120, int(maximo * 0.55)))
            desplazar(pagina, y)
            antes = scroll_y(pagina)
            comprobar(f"{prefijo}: scroll inicial > 0", antes > 0, str(antes))

            # Ajuste adicional: Editar gasto sobre meta inhabilitada.
            lapiz = pagina.locator(
                f'li.lista-gastos__item--inhabilitado:has-text("{META}") '
                'details.edicion-gasto--modal > summary'
            ).first
            comprobar(f"{prefijo}: lápiz de meta inhabilitada", lapiz.count() == 1)
            if lapiz.count():
                antes = antes_del_clic(pagina, lapiz)
                lapiz.click()
                pagina.wait_for_timeout(200)
                tarjeta = pagina.locator(
                    "details.edicion-gasto--modal[open] > .edicion-gasto__formulario"
                ).first
                comprobar(f"{prefijo}: Editar sólido", estilo(
                    pagina,
                    "details.edicion-gasto--modal[open] > .edicion-gasto__formulario",
                    "backgroundColor",
                ) == "rgb(30, 41, 59)")
                comprobar(f"{prefijo}: Editar al frente", estilo(
                    pagina,
                    "details.edicion-gasto--modal[open] > .edicion-gasto__formulario",
                    "zIndex",
                ) == "9002")
                caja = tarjeta.bounding_box()
                contenidos = True
                for selector in (".campo:nth-of-type(1)", ".campo:nth-of-type(2)", ".campo:nth-of-type(3)"):
                    campo = tarjeta.locator(selector)
                    if campo.count() and caja:
                        rect = campo.first.bounding_box()
                        if rect and (rect["x"] < caja["x"] - 1 or
                                     rect["x"] + rect["width"] > caja["x"] + caja["width"] + 1):
                            contenidos = False
                comprobar(f"{prefijo}: campos dentro del modal", contenidos)
                texto = tarjeta.inner_text()
                comprobar(
                    f"{prefijo}: botones Actualizar/Abonar/Cancelar",
                    all(b in texto for b in ("Actualizar", "Abonar", "Cancelar")),
                )
                tarjeta.locator("[data-cancelar-edicion]").first.click()
                pagina.wait_for_timeout(250)
                comprobar_scroll(
                    f"{prefijo}: scroll al cerrar Editar",
                    pagina, antes, scroll_y(pagina),
                )

            # Punto 5: X de meta con aviso exacto y omisión sin salto de scroll.
            x_meta = pagina.locator(
                f'li.lista-gastos__item:has-text("{META_X}") button[data-omitir-gasto][data-es-meta="1"]'
            ).first
            if x_meta.count():
                antes = antes_del_clic(pagina, x_meta)
                x_meta.click()
                pagina.wait_for_timeout(150)
                eliminar = pagina.locator("#modal-omitir-gasto [data-eliminar-confirmar]")
                comprobar(
                    f"{prefijo}: Eliminar bloqueado en meta",
                    eliminar.get_attribute("aria-disabled") == "true",
                )
                comprobar(f"{prefijo}: tooltip exacto", eliminar.get_attribute("title") == AVISO)
                eliminar.click(force=True)
                pagina.wait_for_timeout(150)
                cuerpo = " ".join(
                    pagina.locator("#modal-aviso-cuerpo").inner_text().split()
                )
                comprobar(f"{prefijo}: aviso exacto", AVISO in cuerpo, cuerpo)
                pagina.locator("#modal-aviso [data-aviso-entendido]").first.click()
                pagina.wait_for_timeout(150)
                comprobar(
                    f"{prefijo}: modal de la X sigue abierto",
                    pagina.locator("#modal-omitir-gasto").is_visible(),
                )
                pagina.locator("#modal-omitir-gasto [data-omitir-cancelar]").click()
                pagina.wait_for_timeout(150)
                comprobar_scroll(
                    f"{prefijo}: scroll al cerrar aviso",
                    pagina, antes, scroll_y(pagina),
                )

            # Punto 5: Habilitar recarga sin devolver al inicio.
            selector_habilitar = (
                f'li.lista-gastos__item:has-text("{SUSPENDIDO}") [data-habilitar-gasto]'
            )
            habilitar = pagina.locator(selector_habilitar).first
            comprobar(f"{prefijo}: Habilitar presente", habilitar.count() == 1)
            if habilitar.count():
                marcar_scroll_al_clic(
                    pagina, "[data-habilitar-gasto]", SUSPENDIDO
                )
                with pagina.expect_navigation(wait_until="networkidle", timeout=15000):
                    habilitar.click()
                comprobar_scroll(
                    f"{prefijo}: scroll tras Habilitar",
                    pagina, scroll_marcado(pagina), scroll_y(pagina), 200,
                )
                comprobar(
                    f"{prefijo}: Habilitar desaparece",
                    pagina.locator(
                        f'li.lista-gastos__item:has-text("{SUSPENDIDO}") [data-habilitar-gasto]'
                    ).count() == 0,
                )

            # Punto 5: Eliminar recarga sin devolver al inicio.
            x_eliminar = pagina.locator(
                f'li.lista-gastos__item:has-text("{ELIMINAR}") button[data-omitir-gasto]'
            ).first
            comprobar(f"{prefijo}: X de gasto normal", x_eliminar.count() == 1)
            if x_eliminar.count():
                antes = antes_del_clic(pagina, x_eliminar)
                x_eliminar.click()
                pagina.wait_for_timeout(150)
                selector_confirmar = "#modal-omitir-gasto [data-eliminar-confirmar]"
                confirmar = pagina.locator(selector_confirmar)
                marcar_scroll_al_clic(pagina, selector_confirmar)
                with pagina.expect_navigation(wait_until="networkidle", timeout=15000):
                    confirmar.click()
                comprobar_scroll(
                    f"{prefijo}: scroll tras Eliminar",
                    pagina, scroll_marcado(pagina), scroll_y(pagina), 200,
                )
                comprobar(
                    f"{prefijo}: gasto eliminado",
                    pagina.locator(f'li.lista-gastos__item:has-text("{ELIMINAR}")').count() == 0,
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
