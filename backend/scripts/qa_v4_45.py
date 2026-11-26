"""Gate QA de la SRS v4.44, sección 7: cartera del proveedor (web y móvil)."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

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


def main() -> None:
    """Recorre la cartera en 1280 y 375 px.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
            contexto = navegador.new_context(
                viewport={"width": ancho, "height": 900}, service_workers="block"
            )
            pagina = contexto.new_page()
            prefijo = f"{ancho}px"
            pagina.goto(f"{BASE}/login")
            pagina.fill("#campo-correo", CORREO)
            pagina.fill("#campo-clave", CLAVE)
            pagina.locator('form[action="/login"] button[type="submit"]').first.click()
            pagina.wait_for_load_state("networkidle")
            pagina.goto(f"{BASE}/olb-byte/cartera")
            pagina.wait_for_load_state("networkidle")

            # §7.1: Concepto antes que Monto.
            # La cartera tiene dos campos «concepto»: acotar al formulario de pago.
            concepto = pagina.locator('form[action$="/abonos"] input[name="concepto"]').bounding_box()
            monto = pagina.locator('form[action$="/abonos"] input[name="monto"]').bounding_box()
            comprobar(
                f"{prefijo}: Concepto antes que Monto",
                bool(concepto and monto) and concepto["y"] < monto["y"],
                f"concepto={concepto} monto={monto}",
            )

            # §7.2: mismas dimensiones en escritorio.
            paneles = pagina.locator(".rejilla-paneles--proveedor > .panel").all()
            if ancho >= 768 and len(paneles) == 2:
                a = paneles[0].bounding_box()
                b = paneles[1].bounding_box()
                comprobar(
                    f"{prefijo}: mismo ancho",
                    abs(a["width"] - b["width"]) <= 2,
                    f"{a['width']:.0f} vs {b['width']:.0f}",
                )
                comprobar(
                    f"{prefijo}: misma altura",
                    abs(a["height"] - b["height"]) <= 2,
                    f"{a['height']:.0f} vs {b['height']:.0f}",
                )

            # §7.3: siete columnas en orden exacto (escritorio).
            if ancho >= 768:
                cabeceras = [
                    texto.strip().title()
                    for texto in pagina.locator(".tabla-contenedor--movimientos thead th").all_inner_texts()
                ]
                esperado = ["Fecha", "Tipo", "Cliente", "Producto", "Concepto", "Monto", "Saldo"]
                comprobar(
                    f"{prefijo}: siete columnas en orden",
                    cabeceras == esperado,
                    str(cabeceras),
                )
                filas = pagina.locator(".tabla-contenedor--movimientos tbody tr").count()
                if filas > 4:
                    fila_alto = pagina.locator(".tabla-contenedor--movimientos tbody tr").first.bounding_box()["height"]
                    contenedor = pagina.locator(".tabla-contenedor--movimientos").bounding_box()["height"]
                    visibles = contenedor / fila_alto
                    comprobar(
                        f"{prefijo}: cuatro filas visibles con scroll",
                        3.5 <= visibles <= 5.2,
                        f"filas visibles≈{visibles:.1f}",
                    )
                else:
                    # No es una aprobación: con menos de 5 movimientos el límite de
                    # cuatro filas no se puede medir. Queda como nota, sin contar.
                    print(
                        f"NOTA {prefijo}: límite de cuatro filas no verificado "
                        f"(hay {filas} movimientos; se requieren 5 o más)",
                        flush=True,
                    )
            else:
                # §7.3: detalle móvil con X arriba a la derecha y orden de campos.
                abrir = pagina.locator("[data-abrir-dialogo]").first
                if abrir.count():
                    abrir.click()
                    pagina.wait_for_timeout(200)
                    dialogo = pagina.locator("dialog.detalle-orden[open]").first
                    etiquetas = dialogo.locator("dl dt").all_inner_texts()
                    esperado = ["Fecha", "Tipo", "Cliente", "Producto", "Concepto", "Monto", "Saldo"]
                    comprobar(
                        f"{prefijo}: detalle móvil en orden",
                        etiquetas == esperado,
                        str(etiquetas),
                    )
                    cerrar = dialogo.locator(".detalle-orden__cerrar").bounding_box()
                    caja = dialogo.bounding_box()
                    comprobar(
                        f"{prefijo}: X arriba a la derecha",
                        bool(cerrar and caja)
                        and cerrar["x"] > caja["x"] + caja["width"] * 0.7
                        and cerrar["y"] < caja["y"] + 60,
                    )
                    dialogo.locator(".detalle-orden__cerrar").click()
                    pagina.wait_for_timeout(150)
                    comprobar(
                        f"{prefijo}: la X cierra el detalle",
                        pagina.locator("dialog.detalle-orden[open]").count() == 0,
                    )

            contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
