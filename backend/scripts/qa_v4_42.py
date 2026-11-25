"""Gate QA de la SRS v4.42: Deep Links, scroll y tarjetas directas."""

from __future__ import annotations

from datetime import date

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Chancuco
from app.servicios import chancucos, usuarios

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
DESC = "Cred. Remodelacion 1 QA v442"
REF = "10948271"
REF_WEB = "99887767"
URL = "daviplata://pagar/10948271"
URL_WEB = "https://pagos.entidad.com/abc"
DESC_WEB = "Pasarela web QA"

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
    """Borra los atajos sembrados.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        bd.query(Chancuco).filter(
            Chancuco.numero_referencia.in_((REF, REF_WEB, "99887766"))
        ).delete(
            synchronize_session=False
        )
        bd.commit()


def sembrar() -> None:
    """Crea un atajo con Deep Link y dos días de pago.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        cuenta = usuarios.buscar_por_correo(bd, CORREO)
        assert cuenta is not None
        chancucos.crear_chancuco(
            bd, cuenta.id_usuario, DESC, REF, URL,
            dia_pago_1=15, dia_pago_2=30, valor_pago="110000",
        )
        chancucos.crear_chancuco(
            bd, cuenta.id_usuario, DESC_WEB, REF_WEB, URL_WEB,
            dia_pago_1="15", valor_pago="85000",
        )


def main() -> None:
    """Ejecuta el recorrido en Web y Móvil.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
            limpiar()
            sembrar()
            contexto = navegador.new_context(
                viewport={"width": ancho, "height": 900}, service_workers="block"
            )
            contextoweb = contexto
            contextoweb.add_init_script(
                """window.__opens = [];
                   window.open = function () {
                     window.__opens.push(Array.from(arguments));
                     return null;
                   };"""
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

            # Sección 1: formulario acepta Deep Links.
            pagina.goto(f"{BASE}/chancucos")
            pagina.wait_for_load_state("networkidle")
            campo = pagina.locator('form:has([data-url-pago]) [data-url-pago]')
            comprobar(
                f"{prefijo}: campo de URL es texto",
                campo.count() >= 1 and campo.first.get_attribute("type") == "text",
            )
            comprobar(
                f"{prefijo}: placeholder con daviplata",
                campo.first.get_attribute("placeholder") == "https://... o daviplata://",
            )
            pagina.fill('input[name="descripcion"]', "Deep link web QA")
            pagina.fill('input[name="numero_referencia"]', "99887766")
            pagina.fill('input[name="dia_pago_1"]', "15")
            campo.first.fill(URL)
            pagina.get_by_role("button", name="Guardar atajo").click()
            pagina.wait_for_load_state("networkidle")
            comprobar(
                f"{prefijo}: Deep Link guardado",
                pagina.locator(".alerta--exito").count() >= 1
                and pagina.locator(
                    'tr[data-chancuco-fila]:has-text("Deep link web QA")'
                ).count() >= 1,
            )

            # Sección 2: tabla móvil con scroll horizontal.
            medidas = pagina.evaluate(
                """() => {
                  var c = document.querySelector('.tabla-contenedor--atajos');
                  var t = document.querySelector('.tabla--atajos');
                  return {
                    scroll: c.scrollWidth,
                    client: c.clientWidth,
                    overflow: getComputedStyle(c).overflowX,
                    minWidth: getComputedStyle(t).minWidth
                  };
                }"""
            )
            if ancho < 768:
                comprobar(
                    f"{prefijo}: tabla desplazable",
                    medidas["overflow"] == "auto" and medidas["scroll"] > medidas["client"],
                    str(medidas),
                )
                comprobar(
                    f"{prefijo}: ancho mínimo 440px",
                    medidas["minWidth"] == "440px",
                    medidas["minWidth"],
                )
                pagina.evaluate(
                    """() => {
                      document.querySelector('.tabla-contenedor--atajos').scrollLeft = 999;
                    }"""
                )
                pagina.wait_for_timeout(100)
                comprobar(
                    f"{prefijo}: días completos tras deslizar",
                    "Día 15 · Día 30" in pagina.locator(".tabla--atajos").inner_text(),
                )
            else:
                comprobar(
                    f"{prefijo}: escritorio sin scroll forzado",
                    medidas["overflow"] != "auto" or medidas["scroll"] <= medidas["client"],
                    str(medidas),
                )
            cabeceras = pagina.locator(".tabla--atajos thead").inner_html()
            comprobar(
                f"{prefijo}: cabeceras en dos líneas",
                "Valor a<br" in cabeceras and "Días de<br" in cabeceras,
                cabeceras[:160],
            )

            # Sección 3: tarjetas directas en Mis Finanzas (móvil).
            pagina.goto(f"{BASE}/finanzas")
            pagina.wait_for_load_state("networkidle")
            tarjeta = pagina.locator(f'li.lista-atajos__item:has-text("{DESC}")').first
            comprobar(f"{prefijo}: tarjeta de atajo visible", tarjeta.count() == 1)
            if ancho < 768:
                comprobar(
                    f"{prefijo}: descripción completa",
                    DESC in tarjeta.locator(".atajo-tarjeta-movil__descripcion").inner_text(),
                )
                comprobar(
                    f"{prefijo}: píldora de días",
                    "Pagar los días: 15 · 30"
                    in tarjeta.locator(".atajo-tarjeta-movil__dias").inner_text(),
                )
                comprobar(
                    f"{prefijo}: valor y referencia visibles",
                    "Valor a pagar:" in tarjeta.inner_text()
                    and "Ref: 10948271" in tarjeta.inner_text(),
                )
                comprobar(
                    f"{prefijo}: sin modal de atajo",
                    pagina.locator(".atajo-finanzas-modal").count() == 0,
                )
                pagina.evaluate("window.__opens = []")
                pagina.locator(
                    f'li.lista-atajos__item:has-text("{DESC}") '
                    '.atajo-tarjeta-movil [data-pagar-atajo]'
                ).click()
                pagina.wait_for_timeout(300)
                comprobar(
                    f"{prefijo}: Deep Link sin pestaña nueva",
                    len(pagina.evaluate("window.__opens")) == 0,
                    str(pagina.evaluate("window.__opens")),
                )
            else:
                comprobar(
                    f"{prefijo}: vista web intacta",
                    tarjeta.locator(".atajo-web").first.is_visible(),
                )
                pagina.evaluate("window.__opens = []")
                pagina.locator(
                    f'li.lista-atajos__item:has-text("{DESC_WEB}") '
                    '.atajo-web [data-pagar-atajo]'
                ).click()
                pagina.wait_for_timeout(200)
                comprobar(
                    f"{prefijo}: web abre pestaña nueva",
                    len(pagina.evaluate("window.__opens")) == 1,
                    str(pagina.evaluate("window.__opens")),
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
