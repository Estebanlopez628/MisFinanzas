"""Gate QA de la SRS v4.33: atajo web y modal móvil con distribución exacta."""

from __future__ import annotations

from sqlalchemy import select

from app.core.base_datos import FabricaSesiones
from app.modelos import Chancuco
from app.servicios import chancucos, usuarios
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CORREO = "prueba_qa@misfinanzas.local"
CLAVE = "QA_MisFinanzas_2026!"
DESCRIPCION = "Energia"
REFERENCIA = "171726271"

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
        for atajo in bd.scalars(
            select(Chancuco).where(Chancuco.numero_referencia == REFERENCIA)
        ).all():
            bd.delete(atajo)
        bd.commit()


def verificar_detalle(page, prefijo: str, selector: str) -> None:
    """Comprueba la distribución de tres filas dentro del selector dado.

    Args:
        page: Página de Playwright.
        prefijo: Prefijo para el informe.
        selector: Contenedor del fragmento `.atajo-detalle`.
    """
    raiz = page.locator(selector).first
    comprobar(f"{prefijo}: fragmento visible", raiz.is_visible())

    filas = raiz.locator(".atajo-detalle__fila")
    comprobar(f"{prefijo}: tres filas", filas.count() == 3, str(filas.count()))

    desc = raiz.locator(".atajo-detalle__descripcion").inner_text()
    fecha = raiz.locator(".atajo-detalle__fecha")
    comprobar(f"{prefijo}: descripción", desc == DESCRIPCION, desc)
    comprobar(
        f"{prefijo}: texto Fecha pago",
        "Fecha pago:" in fecha.inner_text() and "Día" in fecha.inner_text(),
        fecha.inner_text(),
    )
    comprobar(
        f"{prefijo}: línea inferior azul",
        fecha.evaluate("(e) => getComputedStyle(e).borderBottomWidth") == "2px"
        and fecha.evaluate("(e) => getComputedStyle(e).borderBottomColor")
        == "rgb(2, 132, 199)",
        fecha.evaluate("(e) => getComputedStyle(e).borderBottomColor"),
    )
    ref = raiz.locator(".atajo-detalle__ref").inner_text()
    valor = raiz.locator(".atajo-detalle__valor").inner_text()
    comprobar(f"{prefijo}: REF a la izquierda", ref == f"REF: {REFERENCIA}", ref)
    comprobar(
        f"{prefijo}: Valor a Pagar",
        "Valor a Pagar:" in valor and "$74.000" in valor,
        valor,
    )

    botones = raiz.locator(".atajo-detalle__fila--acciones > .boton")
    comprobar(f"{prefijo}: dos botones", botones.count() == 2, str(botones.count()))
    if botones.count() == 2:
        copiar = botones.nth(0).bounding_box()
        pagar = botones.nth(1).bounding_box()
        ref_caja = raiz.locator(".atajo-detalle__ref").bounding_box()
        valor_caja = raiz.locator(".atajo-detalle__valor").bounding_box()
        comprobar(
            f"{prefijo}: Copiar bajo REF",
            copiar and ref_caja and abs(copiar["x"] - ref_caja["x"]) < 4,
        )
        comprobar(
            f"{prefijo}: Pagar bajo Valor",
            pagar and valor_caja and abs(
                (pagar["x"] + pagar["width"]) - (valor_caja["x"] + valor_caja["width"])
            ) < 6,
        )
        comprobar(
            f"{prefijo}: botones lado a lado",
            copiar and pagar and abs(copiar["y"] - pagar["y"]) < 2,
        )


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

            with FabricaSesiones() as bd:
                cuenta = usuarios.buscar_por_correo(bd, CORREO)
                assert cuenta is not None
                chancucos.crear_chancuco(
                    bd, cuenta.id_usuario, DESCRIPCION, REFERENCIA,
                    "https://pagos.example.com", valor_pago="74000",
                    dia_pago_1=15, dia_pago_2=None,
                )

            pagina.goto(f"{BASE}/finanzas")
            pagina.wait_for_load_state("networkidle")
            prefijo = f"{ancho}px"

            if ancho >= 768:
                comprobar(
                    f"{prefijo}: tarjeta web visible",
                    pagina.locator(".atajo-web").first.is_visible(),
                )
                comprobar(
                    f"{prefijo}: vista primaria oculta en web",
                    not pagina.locator(".lista-atajos__texto").first.is_visible(),
                )
                verificar_detalle(pagina, prefijo, ".atajo-web")
            else:
                comprobar(
                    f"{prefijo}: vista primaria intacta",
                    pagina.locator(".lista-atajos__descripcion").first.is_visible()
                    and pagina.locator(".badge--fecha").first.is_visible(),
                )
                comprobar(
                    f"{prefijo}: tarjeta web oculta",
                    not pagina.locator(".atajo-web").first.is_visible(),
                )
                fila = pagina.locator('li[data-atajo-fila]').first
                fila.click()
                pagina.wait_for_timeout(200)
                verificar_detalle(pagina, prefijo, ".atajo-detalle--modal")

            anchos = pagina.evaluate(
                "() => ({scroll: document.documentElement.scrollWidth, view: innerWidth})"
            )
            comprobar(
                f"{prefijo}: sin desbordamiento",
                anchos["scroll"] <= anchos["view"],
                str(anchos),
            )
            comprobar(f"{prefijo}: sin errores", not errores, "; ".join(errores[:2]))
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
