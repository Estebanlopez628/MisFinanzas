"""Gate QA: botón de número en Registrar venta, solo móvil (SRS v4.44)."""

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
    """Verifica rotulos, contactos y respaldo en web y móvil.

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
        boton.click()
        pagina_movil.wait_for_timeout(200)
        campo = pagina_movil.locator("input[data-cliente-telefono]")
        enfocado = campo.evaluate("e => document.activeElement === e")
        aviso = pagina_movil.locator("[data-nota-contactos]")
        comprobar(
            "375px: sin Contact Picker avisa sin abrir teclado",
            aviso.is_visible()
            and "WhatsApp" in (aviso.text_content() or "")
            and not enfocado
            and pagina_movil.locator("#modal-aviso:visible").count() == 0,
            (aviso.text_content() or "").strip(),
        )
        comprobar(
            "375px: ofrece Elegir contacto, WhatsApp y Pegar número",
            aviso.locator("[data-elegir-contacto]").is_visible()
            and aviso.locator("[data-abrir-whatsapp]").is_visible()
            and aviso.locator("[data-pegar-portapapeles]").is_visible(),
        )
        aviso.locator("[data-elegir-contacto]").click()
        pagina_movil.wait_for_timeout(100)
        comprobar(
            "375px: Elegir contacto enfoca el campo a propósito",
            campo.evaluate("e => document.activeElement === e"),
        )
        contexto_movil.close()

        contexto_contactos = navegador.new_context(viewport={"width": 375, "height": 900}, service_workers="block")
        contexto_contactos.add_init_script(
            """Object.defineProperty(navigator, 'contacts', {
              configurable: true,
              value: {
                select: function () {
                  return Promise.resolve([{ tel: ['+57 (300) 123-4567'] }]);
                }
              }
            });"""
        )
        pagina_contactos = contexto_contactos.new_page()
        iniciar(pagina_contactos)
        pagina_contactos.locator("button[data-pegar-numero]").click()
        pagina_contactos.wait_for_timeout(250)
        valor = pagina_contactos.locator("input[data-cliente-telefono]").input_value()
        comprobar(
            "375px: contacto se pega sin +57 ni formatos",
            valor == "3001234567",
            valor,
        )
        contexto_contactos.close()

        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
