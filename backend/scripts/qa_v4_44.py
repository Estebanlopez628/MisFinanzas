"""Gate QA de la SRS v4.44: Deep Links, errores en modal y tarjeta móvil."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Chancuco
from app.servicios import chancucos, usuarios

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
DESC = "Atajo QA v444"
REF = "44440001"

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


def limpiar() -> None:
    """Elimina los atajos del gate.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        bd.query(Chancuco).filter(Chancuco.numero_referencia == REF).delete(
            synchronize_session=False
        )
        bd.commit()


def sembrar() -> None:
    """Crea el atajo de prueba con valor y día de pago.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        chancucos.crear_chancuco(
            bd, cuenta.id_usuario, DESC, REF, "https://pagos.entidad.com",
            dia_pago_1=15, dia_pago_2=30, valor_pago="110000",
        )


def leer_url() -> str | None:
    """Lee el enlace guardado del atajo de prueba.

    Returns:
        El enlace persistido o `None`.
    """
    with FabricaSesiones() as bd:
        atajo = bd.query(Chancuco).filter(Chancuco.numero_referencia == REF).first()
        return atajo.url_pago if atajo else None


def main() -> None:
    """Ejecuta el recorrido en Web y Móvil.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (375, 1280):
            limpiar()
            sembrar()
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

            if ancho < 768:
                # Sección 3: tarjeta móvil Ref a la izquierda, Valor a la derecha.
                pagina.goto(f"{BASE}/finanzas")
                pagina.wait_for_load_state("networkidle")
                tarjeta = pagina.locator(f'li.lista-atajos__item:has-text("{DESC}")').first
                ref = tarjeta.locator(".atajo-tarjeta-movil__ref").bounding_box()
                valor = tarjeta.locator(".atajo-tarjeta-movil__valor").bounding_box()
                copiar = tarjeta.locator(".atajo-tarjeta-movil [data-copiar]").bounding_box()
                pagar = tarjeta.locator(".atajo-tarjeta-movil [data-pagar-atajo]").bounding_box()
                comprobar(
                    f"{prefijo}: Ref a la izquierda y Valor a la derecha",
                    bool(ref and valor) and ref["x"] < valor["x"],
                    f"ref={ref} valor={valor}",
                )
                comprobar(
                    f"{prefijo}: Ref sobre Copiar y Valor sobre Pagar",
                    bool(ref and copiar and valor and pagar)
                    and abs((ref["x"]) - (copiar["x"])) <= 12
                    and abs((valor["x"] + valor["width"]) - (pagar["x"] + pagar["width"])) <= 12,
                )

            # Sección 2: error dentro del modal y guardado de Deep Link.
            pagina.goto(f"{BASE}/chancucos")
            pagina.wait_for_load_state("networkidle")
            if ancho < 768:
                pagina.locator(f'tr[data-chancuco-fila]:has-text("{DESC}")').first.click()
                pagina.wait_for_timeout(200)
            else:
                pagina.locator(
                    f'tr[data-chancuco-fila]:has-text("{DESC}") [data-abrir-atajo]'
                ).first.click()
                pagina.wait_for_timeout(200)

            formulario = pagina.locator("form[data-atajo-editar]:visible").first
            comprobar(f"{prefijo}: modal de edición abierto", formulario.count() == 1)
            formulario.locator('[name="url_pago"]').fill("javascript:alert(1)")
            formulario.locator('button[type="submit"]:has-text("Actualizar")').first.click()
            pagina.wait_for_timeout(400)
            banner = formulario.locator("[data-error-modal]")
            comprobar(
                f"{prefijo}: error visible dentro del modal",
                banner.is_visible() and "Enlace inválido" in (banner.text_content() or ""),
                banner.text_content() or "",
            )
            comprobar(
                f"{prefijo}: modal permanece abierto",
                pagina.locator("details.atajo-modal[open]").count() == 1,
            )
            comprobar(
                f"{prefijo}: sin error en el módulo de fondo",
                pagina.locator("main > .alerta--error:visible").count() == 0,
            )

            formulario.locator('[name="url_pago"]').fill("daviplata")
            formulario.locator('button[type="submit"]:has-text("Actualizar")').first.click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(300)
            comprobar(
                f"{prefijo}: 'daviplata' se guarda como 'daviplata://'",
                leer_url() == "daviplata://",
                str(leer_url()),
            )

            contexto.close()
        navegador.close()

    limpiar()
    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
