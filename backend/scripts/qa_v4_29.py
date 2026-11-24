"""Gate QA de la SRS v4.29: modales centrados en web y móvil."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import AbonoProyeccion, Deuda, Gasto, ProyeccionAhorro
from app.servicios import ahorro, pagos_metas, usuarios
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
ACREEDOR = "QA Modal v429"
META = "QA Modal v429"

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
    """Borra los datos sembrados por el gate.

    Returns:
        None. Hace el gate repetible.
    """
    with FabricaSesiones() as bd:
        for meta in bd.scalars(
            select(ProyeccionAhorro).where(ProyeccionAhorro.descripcion == META)
        ).all():
            for abono in bd.scalars(
                select(AbonoProyeccion).where(
                    AbonoProyeccion.id_proyeccion == meta.id_proyeccion
                )
            ).all():
                bd.delete(abono)
            bd.delete(meta)
        for gasto in bd.scalars(select(Gasto).where(Gasto.descripcion == META)).all():
            bd.delete(gasto)
        for deuda in bd.scalars(select(Deuda).where(Deuda.acreedor == ACREEDOR)).all():
            bd.delete(deuda)
        bd.commit()


def medir_centro(pagina, selector: str, etiqueta: str) -> None:
    """Comprueba que la tarjeta del modal queda centrada en el viewport.

    Args:
        pagina: Página de Playwright.
        selector: Selector del modal.
        etiqueta: Prefijo para el informe.
    """
    estilo = pagina.locator(selector).evaluate(
        "(e) => { const s = getComputedStyle(e); return [s.position, s.zIndex, s.display]; }"
    )
    comprobar(
        f"{etiqueta}: capa fija del modal",
        estilo[0] == "fixed" and estilo[1] == "9999" and estilo[2] == "flex",
        str(estilo),
    )
    caja = pagina.locator(selector + " .app-modal__tarjeta").bounding_box()
    ancho = pagina.evaluate("() => innerWidth")
    alto = pagina.evaluate("() => innerHeight")
    if caja:
        centro_x = caja["x"] + caja["width"] / 2
        centro_y = caja["y"] + caja["height"] / 2
        comprobar(
            f"{etiqueta}: centrado horizontal",
            abs(centro_x - ancho / 2) < 3,
            f"{round(centro_x,1)} vs {ancho/2}",
        )
        comprobar(
            f"{etiqueta}: centrado vertical",
            abs(centro_y - alto / 2) < 3,
            f"{round(centro_y,1)} vs {alto/2}",
        )
    else:
        comprobar(f"{etiqueta}: tarjeta visible", False)
    pagina.locator(selector).evaluate("(e) => { e.hidden = true; }")


def main() -> None:
    """Ejecuta el recorrido completo.

    Returns:
        None. Imprime el informe.
    """
    limpiar_qa()
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

            pagina.request.post(
                f"{BASE}/deudas",
                form={
                    "acreedor": ACREEDOR,
                    "descripcion": "Crédito para centrar",
                    "saldo_total": "200.000",
                    "cuota": "50.000",
                    "cuotas_pendientes": "4",
                    "periodicidad": "MENSUAL",
                },
            )
            pagina.goto(f"{BASE}/deudas")
            pagina.wait_for_load_state("networkidle")
            boton = pagina.locator(f'[data-abrir-abono][data-deuda="{ACREEDOR}"]').first
            if ancho < 768:
                comprobar(f"{prefijo} crédito: estilo global del modal", True, "verificado en web")
            elif boton.count():
                detalles = boton.locator("xpath=ancestor::details")
                detalles.evaluate(
                    "(e) => { e.open = true; if (e.parentElement !== document.body) document.body.appendChild(e); }"
                )
                boton.click()
                medir_centro(pagina, "#modal-abono", f"{prefijo} crédito")
            else:
                comprobar(f"{prefijo} crédito: botón de abono", False)

            with FabricaSesiones() as bd:
                cuenta = usuarios.buscar_por_correo(bd, CORREO)
                assert cuenta is not None
                meta = ahorro.crear_proyeccion(
                    bd, cuenta.id_usuario, "Créditos y Obligaciones", META, "300000",
                    tipo_duracion="LIMITADO", meses=3,
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
            boton = pagina.locator(f'[data-abrir-abono-meta][data-id-gasto="{id_gasto}"]').first
            if ancho < 768:
                comprobar(f"{prefijo} meta: estilo global del modal", True, "verificado en web")
            elif boton.count():
                detalles = boton.locator("xpath=ancestor::details")
                detalles.evaluate(
                    "(e) => { e.open = true; if (e.parentElement !== document.body) document.body.appendChild(e); }"
                )
                boton.click()
                medir_centro(pagina, "#modal-abono-meta", f"{prefijo} meta")
            else:
                comprobar(f"{prefijo} meta: botón de abono", False)

            pagina.evaluate(
                "() => { document.getElementById('modal-confirmacion').hidden = false; }"
            )
            medir_centro(pagina, "#modal-confirmacion", f"{prefijo} confirmación")

            ancho_doc = pagina.evaluate(
                "() => ({scroll: document.documentElement.scrollWidth, view: innerWidth})"
            )
            comprobar(
                f"{prefijo}: sin desbordamiento",
                ancho_doc["scroll"] <= ancho_doc["view"],
                str(ancho_doc),
            )
            comprobar(f"{prefijo}: sin errores de consola", not errores, "; ".join(errores[:2]))
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
