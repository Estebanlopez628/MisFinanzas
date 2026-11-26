"""Gate QA: dos atajos visibles con scroll y alineación inferior en Mis Finanzas."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Usuario
from app.servicios import chancucos

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


def asegurar_atajos() -> None:
    """Garantiza tres atajos para comprobar el desplazamiento.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        usuario = bd.query(Usuario).filter(Usuario.correo == CORREO).first()
        if not usuario:
            return
        actuales = chancucos.listar_chancucos(bd, usuario.id_usuario)
        for numero in range(len(actuales) + 1, 4):
            chancucos.crear_chancuco(
                bd,
                usuario.id_usuario,
                f"Atajo de prueba {numero}",
                f"QA{numero}",
                valor_pago="100000",
                dia_pago_1=15,
            )
        bd.commit()


def abrir(pagina, ancho: int) -> None:
    """Inicia sesión y abre Mis Finanzas con el ancho indicado.

    Args:
        pagina: Página de Playwright.
        ancho: Ancho del viewport.

    Returns:
        None.
    """
    pagina.set_viewport_size({"width": ancho, "height": 900})
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", CORREO)
    pagina.fill("#campo-clave", CLAVE)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")
    pagina.goto(f"{BASE}/finanzas")
    pagina.wait_for_load_state("networkidle")


def main() -> None:
    """Verifica el límite de dos atajos y la alineación inferior en web.

    Returns:
        None. Imprime el informe.
    """
    asegurar_atajos()
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        contexto = navegador.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        pagina = contexto.new_page()
        abrir(pagina, 1280)

        lista = pagina.locator(".lista-atajos")
        comprobar("1280px: hay tres atajos en la lista", lista.locator("li").count() >= 3)
        alto, contenido = lista.evaluate("e => [e.clientHeight, e.scrollHeight]")
        comprobar("1280px: solo dos atajos visibles con scroll", alto == 254 and contenido > alto, f"{alto}/{contenido}")
        comprobar(
            "1280px: sin desplazamiento horizontal de la página",
            pagina.evaluate("document.documentElement.scrollWidth === window.innerWidth"),
        )

        atajos = pagina.locator(".panel--atajos").bounding_box()
        resultado = pagina.locator(".panel--resultado").bounding_box()
        final_atajos = atajos["y"] + atajos["height"]
        final_resultado = resultado["y"] + resultado["height"]
        comprobar(
            "1280px: atajos y resultado terminan a la misma altura",
            abs(final_atajos - final_resultado) <= 1,
            f"atajos={final_atajos} resultado={final_resultado}",
        )
        contexto.close()

        contexto_movil = navegador.new_context(viewport={"width": 375, "height": 900}, service_workers="block")
        pagina_movil = contexto_movil.new_page()
        abrir(pagina_movil, 375)
        lista_movil = pagina_movil.locator(".lista-atajos")
        alto, contenido = lista_movil.evaluate("e => [e.clientHeight, e.scrollHeight]")
        comprobar("375px: solo dos atajos visibles con scroll", alto == 290 and contenido > alto, f"{alto}/{contenido}")
        contexto_movil.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
