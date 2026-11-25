"""Gate QA de la SRS v4.43: columnas móviles, portal del modal y scroll justo."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Chancuco
from app.servicios import chancucos, usuarios

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
DESC = "Atajo con descripcion larga para forzar scroll QA v443"
DESC_CORTA = "Corto"

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
    """Borra los atajos del gate.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        bd.query(Chancuco).filter(
            Chancuco.descripcion.in_((DESC, DESC_CORTA))
        ).delete(synchronize_session=False)
        bd.commit()


def sembrar(descripcion: str) -> None:
    """Crea un atajo de prueba.

    Args:
        descripcion: Texto a mostrar en la tabla.
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        chancucos.crear_chancuco(
            bd, cuenta.id_usuario, descripcion, "443001",
            "https://pagos.entidad.com", dia_pago_1=15, dia_pago_2=30,
            valor_pago="110000",
        )


def login(pagina) -> None:
    """Inicia sesión con el usuario QA.

    Args:
        pagina: Página de Playwright.
    """
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", CORREO)
    pagina.fill("#campo-clave", CLAVE)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")


def main() -> None:
    """Ejecuta el recorrido.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (375, 1280):
            limpiar()
            sembrar(DESC)
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
            login(pagina)
            prefijo = f"{ancho}px"
            pagina.goto(f"{BASE}/chancucos")
            pagina.wait_for_load_state("networkidle")

            visibles = pagina.locator(".tabla--atajos thead th:visible").count()
            comprobar(
                f"{prefijo}: columnas visibles",
                visibles == (3 if ancho < 768 else 5),
                f"visibles={visibles}",
            )
            if ancho < 768:
                comprobar(
                    f"{prefijo}: sin Acciones en móvil",
                    pagina.locator(".tabla--atajos thead th:nth-child(5)").is_visible()
                    is False,
                )
                fila = pagina.locator(f'tr[data-chancuco-fila]:has-text("{DESC}")').first
                fila.click()
                pagina.wait_for_timeout(200)
                modal = pagina.locator("details.atajo-modal[open]").first
                comprobar(f"{prefijo}: modal abierto", modal.count() == 1)
                comprobar(
                    f"{prefijo}: modal sobre body",
                    pagina.evaluate(
                        "() => !!document.querySelector('body > details.atajo-modal[open]')"
                    ),
                )
                tarjeta = modal.locator(".edicion-gasto__formulario").first
                caja = tarjeta.bounding_box()
                comprobar(
                    f"{prefijo}: modal centrado",
                    bool(caja)
                    and abs((caja["x"] + caja["width"] / 2) - ancho / 2) <= 12,
                    str(caja),
                )
                texto = tarjeta.text_content() or ""
                for campo in (
                    "Descripción", "Número de referencia", "Valor a pagar (COP)",
                    "Día de pago", "Enlace de pago", "Actualizar", "Eliminar",
                ):
                    comprobar(f"{prefijo}: campo {campo}", campo in texto)
                modal.locator("[data-cancelar-edicion]").first.click()
                pagina.wait_for_timeout(150)
                comprobar(
                    f"{prefijo}: modal vuelve a la fila",
                    pagina.locator("body > details.atajo-modal").count() == 0,
                )

            # El scroll aparece solo cuando el texto no cabe.
            medidas = pagina.evaluate(
                """() => {
                  var c = document.querySelector('.tabla-contenedor--atajos');
                  return { scroll: c.scrollWidth, client: c.clientWidth,
                           overflow: getComputedStyle(c).overflowX };
                }"""
            )
            if ancho < 768:
                comprobar(
                    f"{prefijo}: scroll con texto largo",
                    medidas["scroll"] > medidas["client"],
                    str(medidas),
                )
                limpiar()
                sembrar(DESC_CORTA)
                pagina.reload()
                pagina.wait_for_load_state("networkidle")
                medidas_cortas = pagina.evaluate(
                    """() => {
                      var c = document.querySelector('.tabla-contenedor--atajos');
                      return { scroll: c.scrollWidth, client: c.clientWidth };
                    }"""
                )
                comprobar(
                    f"{prefijo}: sin scroll con texto corto",
                    medidas_cortas["scroll"] <= medidas_cortas["client"],
                    str(medidas_cortas),
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
