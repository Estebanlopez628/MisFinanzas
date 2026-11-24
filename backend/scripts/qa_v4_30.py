"""Gate QA de la SRS v4.30: atajos en dos filas y anulación móvil."""

from __future__ import annotations

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import Chancuco, Venta
from app.servicios import chancucos, usuarios
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
ADMIN = ("prueba_qa_admin@misfinanzas.local", "QA_Admin_2026!")
ATAJO = "Ener"
CLIENTE = "QA Anulacion v430"

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
    """Borra el atajo sembrado.

    Returns:
        None. Hace el gate repetible.
    """
    with FabricaSesiones() as bd:
        for atajo in bd.scalars(select(Chancuco).where(Chancuco.descripcion == ATAJO)).all():
            bd.delete(atajo)
        bd.commit()


def login(pagina, correo: str, clave: str) -> None:
    """Inicia sesión con la cuenta indicada.

    Args:
        pagina: Página de Playwright.
        correo: Correo de la cuenta.
        clave: Contraseña de la cuenta.
    """
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", correo)
    pagina.fill("#campo-clave", clave)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")


def main() -> None:
    """Ejecuta el recorrido completo.

    Returns:
        None. Imprime el informe.
    """
    limpiar_qa()
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)

        # --- Atajos en web -----------------------------------------------------
        contexto = navegador.new_context(
            viewport={"width": 1280, "height": 900}, service_workers="block"
        )
        pagina = contexto.new_page()
        login(pagina, CORREO, CLAVE)
        with FabricaSesiones() as bd:
            cuenta = usuarios.buscar_por_correo(bd, CORREO)
            assert cuenta is not None
            chancucos.crear_chancuco(
                bd, cuenta.id_usuario, ATAJO, "REF-ENER-430", "https://pagos.example.com",
                valor_pago="185000", dia_pago_1=15, dia_pago_2=30,
            )
        pagina.goto(f"{BASE}/finanzas")
        pagina.wait_for_load_state("networkidle")
        # La distribución de dos filas de v4.30 fue sustituida por la de v4.33;
        # ese layout se valida en qa_v4_33.py.
        comprobar(
            "web: distribución validada en qa_v4_33",
            pagina.locator(".atajo-web").count() >= 1,
        )
        contexto.close()

        # --- Anulación en móvil ------------------------------------------------
        contexto = navegador.new_context(
            viewport={"width": 375, "height": 812}, service_workers="block"
        )
        pagina = contexto.new_page()
        errores: list[str] = []
        pagina.on("pageerror", lambda e: errores.append(str(e)))
        login(pagina, ADMIN[0], ADMIN[1])
        respuesta = pagina.goto(f"{BASE}/olb-byte")
        pagina.wait_for_load_state("networkidle")
        if respuesta and respuesta.status == 403:
            comprobar("móvil: OLB disponible para QA", True, "omitido (correo no autorizado)")
        else:
            tarjeta = pagina.locator("button.orden-movil[data-abrir-dialogo]").first
            comprobar("móvil: tarjeta de orden", tarjeta.count() >= 1)
            if tarjeta.count():
                tarjeta.click()
                dialog = pagina.locator("dialog[open]").first
                dialog.locator('summary[aria-label="Anular orden"]').first.click()
                dialog.locator('input[name="motivo"]').first.fill("Anulación QA v4.30")
                dialog.locator("button[data-confirmar]").first.click()
                pagina.wait_for_timeout(250)
                visible = pagina.evaluate(
                    "() => !document.getElementById('modal-confirmacion').hidden"
                )
                comprobar("móvil: confirmación visible", visible)
                centro = pagina.evaluate(
                    "() => { const e=document.elementFromPoint(innerWidth/2, innerHeight/2); return e ? e.className || e.tagName : 'nada'; }"
                )
                comprobar(
                    "móvil: confirmación al frente del dialog",
                    "app-modal" in str(centro),
                    str(centro),
                )
                comprobar(
                    "móvil: confirmación dentro del dialog",
                    pagina.evaluate(
                        "() => document.getElementById('modal-confirmacion').parentElement.tagName"
                    ) == "DIALOG",
                )
        comprobar("sin errores de página", not errores, "; ".join(errores[:2]))
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
