"""Gate QA: botón móvil abre WhatsApp y el campo limpia el número pegado."""

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


def iniciar(pagina) -> None:
    """Inicia sesión con la cuenta QA de administración.

    Args:
        pagina: Página de Playwright.

    Returns:
        None.
    """
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", CORREO)
    pagina.fill("#campo-clave", CLAVE)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")
    pagina.goto(f"{BASE}/olb-byte")
    pagina.wait_for_load_state("networkidle")


def main() -> None:
    """Verifica rótulos, apertura de WhatsApp y limpieza del campo en web y móvil.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)

        contexto_web = navegador.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        pagina_web = contexto_web.new_page()
        iniciar(pagina_web)
        boton_web = pagina_web.locator("button[data-pegar-numero]")
        texto_web = boton_web.inner_text()
        comprobar(
            "1280px: el botón sigue diciendo «Pegar número»",
            "Pegar número" in texto_web and "Agregar Numero" not in texto_web,
            texto_web,
        )
        comprobar(
            "1280px: un solo rótulo en el DOM",
            boton_web.locator("[data-rotulo-numero]").count() == 1
            and boton_web.text_content().count("Pegar número") == 1
            and "Agregar Numero" not in (boton_web.text_content() or ""),
        )
        contexto_web.close()

        contexto_movil = navegador.new_context(viewport={"width": 375, "height": 900}, service_workers="block")
        pagina_movil = contexto_movil.new_page()
        iniciar(pagina_movil)
        boton = pagina_movil.locator("button[data-pegar-numero]")
        texto = boton.inner_text()
        comprobar(
            "375px: el botón dice «Agregar Numero»",
            "Agregar Numero" in texto and "Pegar número" not in texto,
            texto,
        )
        comprobar(
            "375px: un solo rótulo en el DOM",
            boton.locator("[data-rotulo-numero]").count() == 1
            and (boton.text_content() or "").count("Agregar Numero") == 1
            and "Pegar número" not in (boton.text_content() or ""),
        )
        aviso = pagina_movil.locator("[data-nota-contactos]")
        comprobar(
            "375px: sin botones de respaldo en el aviso",
            aviso.locator("[data-elegir-contacto]").count() == 0
            and aviso.locator("[data-abrir-whatsapp]").count() == 0
            and aviso.locator("[data-pegar-portapapeles]").count() == 0,
        )
        boton.click()
        pagina_movil.wait_for_timeout(200)
        campo = pagina_movil.locator("input[data-cliente-telefono]")
        comprobar(
            "375px: al pulsar no se abre el teclado ni aparece aviso",
            not campo.evaluate("e => document.activeElement === e") and not aviso.is_visible(),
        )

        campo.fill("+57 (300) 123-4567")
        pagina_movil.wait_for_timeout(100)
        comprobar(
            "375px: al pegar queda solo el número de 10 dígitos",
            campo.input_value() == "3001234567",
            campo.input_value(),
        )
        campo.fill("300 456 7890")
        pagina_movil.wait_for_timeout(100)
        comprobar(
            "375px: al pegar sin indicativo también queda limpio",
            campo.input_value() == "3004567890",
            campo.input_value(),
        )
        contexto_movil.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
