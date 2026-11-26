"""Gate QA: filas visibles, cabeceras opacas y modal de gasto (SRS v4.44)."""

from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.servicios import comercial

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa_admin@misfinanzas.local"
CLAVE = "QA_Admin_2026!"

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


def iniciar(pagina, ruta: str) -> None:
    """Inicia sesión y abre una ruta de OLB_BYTE.

    Args:
        pagina: Página de Playwright.
        ruta: Ruta destino.

    Returns:
        None.
    """
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", CORREO)
    pagina.fill("#campo-clave", CLAVE)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")
    pagina.goto(f"{BASE}{ruta}")
    pagina.wait_for_load_state("networkidle")


def main() -> None:
    """Recorre ranking e historial en web y móvil.

    Returns:
        None. Imprime el informe.
    """
    with FabricaSesiones() as bd:
        comercial.registrar_gasto_operativo(bd, "10000", "2026-11-01")

    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)

        contexto_web = navegador.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        pagina = contexto_web.new_page()
        iniciar(pagina, "/olb-byte/garantias")
        caja = pagina.locator(".tabla-contenedor--ranking")
        tope = caja.evaluate("e => getComputedStyle(e).maxHeight")
        fondo = caja.locator("thead th").first.evaluate("e => getComputedStyle(e).backgroundColor")
        comprobar(
            "1280px: ranking con siete filas visibles",
            tope == "336px",
            f"max-height={tope}",
        )
        comprobar(
            "1280px: cabecera del ranking opaca",
            fondo == "rgb(15, 23, 42)",
            fondo,
        )

        pagina.goto(f"{BASE}/olb-byte/cartera")
        pagina.wait_for_load_state("networkidle")
        caja = pagina.locator(".tabla-contenedor--gastos")
        tope = caja.evaluate("e => getComputedStyle(e).maxHeight")
        fondo = caja.locator("thead th").first.evaluate("e => getComputedStyle(e).backgroundColor")
        comprobar(
            "1280px: historial con cinco filas visibles",
            tope == "252px",
            f"max-height={tope}",
        )
        comprobar(
            "1280px: cabecera del historial opaca",
            fondo == "rgb(15, 23, 42)",
            fondo,
        )
        contexto_web.close()

        contexto_movil = navegador.new_context(viewport={"width": 375, "height": 900}, service_workers="block")
        pagina = contexto_movil.new_page()
        iniciar(pagina, "/olb-byte/cartera")
        lista = pagina.locator(".ordenes-moviles--gastos")
        cabecera = lista.locator("li.orden-movil--cabecera").first.inner_text()
        comprobar(
            "375px: encabezado FECHA | MONTO",
            [parte.strip().upper() for parte in cabecera.split()] == ["FECHA", "MONTO"],
            cabecera,
        )
        fila = lista.locator("button.orden-movil").first
        texto_fila = fila.inner_text()
        comprobar(
            "375px: fila limpia sin prefijos ni recorte",
            "Fecha:" not in texto_fila
            and "Valor del gasto:" not in texto_fila
            and re.search(r"\b\d{2}/\d{2}/\d{4}\b", texto_fila) is not None
            and "$" in texto_fila,
            texto_fila,
        )
        color = fila.locator(".orden-movil__monto").evaluate("e => getComputedStyle(e).color")
        comprobar("375px: monto en verde esmeralda", color == "rgb(16, 185, 129)", color)
        recorte = fila.locator("span").first.evaluate("e => getComputedStyle(e).textOverflow")
        comprobar("375px: sin truncate en la fila", recorte == "clip", recorte)
        tope = lista.evaluate("e => getComputedStyle(e).maxHeight")
        comprobar(
            "375px: historial con cinco filas visibles",
            tope == "210px",
            f"max-height={tope}",
        )
        lista.locator("button.orden-movil").first.click()
        pagina.wait_for_timeout(200)
        dialogo = pagina.locator("dialog.detalle-orden[open]").first
        comprobar("375px: la fila abre el modal", dialogo.count() == 1)
        botones = [b.strip() for b in dialogo.locator(".gasto-operativo__acciones button").all_inner_texts()]
        comprobar(
            "375px: modal con Actualizar y Eliminar",
            "Actualizar" in botones and "Eliminar" in botones and "Guardar" not in botones,
            str(botones),
        )
        capa = dialogo.evaluate("e => getComputedStyle(e).zIndex")
        comprobar("375px: modal por encima de todo", capa == "9999", capa)
        x = dialogo.locator(".detalle-orden__cerrar")
        color_x = x.evaluate("e => getComputedStyle(e).backgroundColor")
        comprobar(
            "375px: X del modal con el rojo uniforme",
            color_x == "rgba(239, 68, 68, 0.14)",
            color_x,
        )
        x.click()
        pagina.wait_for_timeout(150)
        comprobar(
            "375px: la X cierra el modal",
            pagina.locator("dialog.detalle-orden[open]").count() == 0,
        )
        contexto_movil.close()

        contexto_700 = navegador.new_context(viewport={"width": 700, "height": 900}, service_workers="block")
        pagina_700 = contexto_700.new_page()
        iniciar(pagina_700, "/olb-byte/cartera")
        visibilidad = (
            pagina_700.locator(".tabla-contenedor--gastos").is_visible(),
            pagina_700.locator(".ordenes-moviles--gastos").is_visible(),
        )
        comprobar(
            "700px: tabla de dos columnas (corte <768 px)",
            visibilidad == (False, True),
            str(visibilidad),
        )
        contexto_700.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
