"""Gate QA de la SRS v4.35 en Chromium (web y móvil)."""

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
NORMAL = "Arriendo QA v435"
OTRO = "Agua QA v435"
META = "Meta · Viaje QA v435"

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
            select(ProyeccionAhorro).where(ProyeccionAhorro.descripcion == "Viaje QA v435")
        ).all():
            bd.delete(meta)
        for gasto in bd.scalars(
            select(Gasto).where(Gasto.descripcion.in_((NORMAL, OTRO, META)))
        ).all():
            bd.delete(gasto)
        bd.commit()


def sembrar() -> None:
    """Crea los gastos y la meta de prueba.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        hoy = date.today()
        for nombre in (NORMAL, OTRO):
            gastos.crear_gasto(
                bd, cuenta.id_usuario, "Vivienda", nombre, "800000", hoy, es_fijo=True
            )
        meta = ahorro.crear_proyeccion(
            bd, cuenta.id_usuario, "Créditos y Obligaciones", "Viaje QA v435", "300000",
            tipo_duracion="LIMITADO", meses=3,
        )
        pagos_metas.asegurar_gastos_de_metas(bd, cuenta.id_usuario, hoy.year, hoy.month)


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

            # Punto 1: X en gasto normal abre el modal; meta conserva su X.
            x_normal = pagina.locator(f'[data-omitir-gasto][data-descripcion="{NORMAL}"]')
            x_meta = pagina.locator(
                'li.lista-gastos__item:has-text("Meta · Viaje") button[data-omitir-gasto][data-es-meta="1"]'
            )
            comprobar(f"{prefijo}: X normal con modal", x_normal.count() >= 1)
            comprobar(f"{prefijo}: meta incluida en el modal unificado", x_meta.count() >= 1)
            if x_normal.count():
                x_normal.first.click()
                pagina.wait_for_timeout(150)
                comprobar(
                    f"{prefijo}: modal omitir visible",
                    pagina.locator("#modal-omitir-gasto").is_visible(),
                )
                cuerpo = " ".join(
                    pagina.locator("#modal-omitir-gasto-titulo").inner_text().split()
                )
                comprobar(
                    f"{prefijo}: texto del modal",
                    "cuéntanos qué deseas hacer con este gasto fijo" in cuerpo.lower(),
                    cuerpo,
                )
                comprobar(
                    f"{prefijo}: modal con velo desenfocado y centrado",
                    estilo(pagina, "#modal-omitir-gasto", "backgroundColor")
                    == "rgba(15, 23, 42, 0.45)"
                    and estilo(pagina, "#modal-omitir-gasto", "backdropFilter")
                    == "blur(6px)"
                    and estilo(pagina, "#modal-omitir-gasto", "position") == "fixed",
                    estilo(pagina, "#modal-omitir-gasto", "backgroundColor"),
                )
                textos_botones = pagina.locator(
                    "#modal-omitir-gasto .app-modal__acciones"
                ).inner_text()
                comprobar(
                    f"{prefijo}: solo dos acciones",
                    "Omitir pago (10 dias)" in textos_botones
                    and "Eliminar Gasto" in textos_botones
                    and "Cancelar" not in textos_botones,
                    textos_botones,
                )
                comprobar(
                    f"{prefijo}: cierre X arriba",
                    pagina.locator(
                        "#modal-omitir-gasto .edicion-gasto__cerrar"
                    ).count() == 1,
                )
                if ancho >= 768:
                    with pagina.expect_navigation(wait_until="networkidle", timeout=10000):
                        pagina.locator("#modal-omitir-gasto [data-omitir-confirmar]").click()
                    fila = pagina.locator(f'li.lista-gastos__item:has-text("{NORMAL}")')
                    comprobar(
                        f"{prefijo}: pago omitido visible",
                        "Pago omitido hasta" in fila.inner_text(),
                        fila.inner_text()[:100],
                    )
                else:
                    pagina.locator("#modal-omitir-gasto [data-omitir-cancelar]").click()

            # Punto 2: editar un ítem inhabilitado/meta con modal sólido y cierre X.
            editar = pagina.locator(
                'li.lista-gastos__item:has-text("Meta · Viaje") summary.boton-circular--editar'
            )
            if editar.count():
                editar.first.click()
                pagina.wait_for_timeout(150)
                modal = pagina.locator(
                    'details.edicion-gasto--modal[open]'
                ).first
                comprobar(f"{prefijo}: editar meta abre modal", modal.count() >= 1)
                if modal.count():
                    tarjeta = modal.locator(".edicion-gasto__formulario").first
                    comprobar(
                        f"{prefijo}: fondo sólido",
                        estilo(pagina, "details.edicion-gasto--modal[open]", "backgroundColor")
                        == "rgba(15, 23, 42, 0.45)",
                    )
                    controles = tarjeta.locator(".campo__control")
                    desborde = controles.evaluate_all(
                        "(es) => es.filter(e => e.scrollWidth > e.clientWidth + 1).length"
                    )
                    comprobar(f"{prefijo}: campos sin desborde", desborde == 0, str(desborde))
                    # SRS v4.39: el cierre es la X de la cabecera, sin «Cancelar».
                    comprobar(
                        f"{prefijo}: sin Cancelar y con cierre X",
                        tarjeta.locator("button", has_text="Cancelar").count() == 0
                        and tarjeta.locator("[data-cancelar-edicion]").count() >= 1,
                    )
                    tarjeta.locator("button[data-cancelar-edicion]").first.click()

            # Punto 3: íconos en pestañas.
            pagina.goto(f"{BASE}/presupuesto")
            pagina.wait_for_load_state("networkidle")
            comprobar(
                f"{prefijo}: pestañas sin íconos",
                pagina.locator(".subnav-finanzas__icono").count() == 0,
            )
            comprobar(
                f"{prefijo}: ícono en el título",
                pagina.locator(".heroe__titulo-icono").count() >= 1,
            )

            # Punto 4: cabeceras de deudas.
            pagina.goto(f"{BASE}/deudas")
            pagina.wait_for_load_state("networkidle")
            cabeceras = " ".join(
                th.inner_text() for th in pagina.locator(".tabla--deudas thead th").all()
            )
            normalizado = " ".join(cabeceras.lower().split())
            comprobar(
                f"{prefijo}: cabeceras exactas",
                "no. de cuotas pendientes" in normalizado
                and "intervalo de pago" in normalizado
                and "vinculación" in normalizado,
                cabeceras[:120],
            )

            # Punto 5: atajos sin óvalo y vista móvil.
            pagina.goto(f"{BASE}/finanzas")
            pagina.wait_for_load_state("networkidle")
            dia = pagina.locator(".atajo-dia-texto").first
            if dia.count():
                comprobar(
                    f"{prefijo}: día sin óvalo",
                    dia.evaluate("(e) => getComputedStyle(e).borderTopWidth") == "0px"
                    and dia.evaluate("(e) => getComputedStyle(e).backgroundColor")
                    == "rgba(0, 0, 0, 0)",
                )
            if ancho < 768:
                filas_atajo = pagina.locator('li[data-atajo-fila]')
                if filas_atajo.count():
                    texto = filas_atajo.first.inner_text()
                    comprobar(
                        f"{prefijo}: vista inicial con tres datos",
                        "Valor a pagar" in texto
                        and "Pagar los :" in texto
                        and "días 15" in texto,
                        texto[:100],
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
