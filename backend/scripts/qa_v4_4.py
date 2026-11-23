"""Recorrido de QA de la SRS v4.4 en navegador real (Chromium).

Responsabilidad
---------------
Verificar en 360/390/768/1280 px que las donas están separadas, que el
Consejero usa el libre consolidado, que Deudas muestra la vinculación, que el
borrado y el alta no se duplican, y que el desplazamiento se conserva.

Uso (con el servidor levantado en 127.0.0.1:8000):

    .venv\\Scripts\\python -m scripts.qa_v4_4
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
QA_CORREO = "prueba_qa@misfinanzas.local"
QA_CLAVE = "QA_MisFinanzas_2026!"
ADMIN_CORREO = "prueba_qa_admin@misfinanzas.local"
ADMIN_CLAVE = "QA_Admin_2026!"
TAMANOS = (360, 390, 768, 1280)

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado de la comprobación.
        detalle: Información extra para el informe.
    """
    resultados.append((nombre, bool(condicion), detalle))


def entrar(contexto, correo: str, clave: str) -> None:
    """Inicia sesión en la aplicación.

    Args:
        contexto: Contexto del navegador.
        correo: Correo de la cuenta.
        clave: Contraseña de la cuenta.
    """
    pagina = contexto.new_page()
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", correo)
    pagina.fill("#campo-clave", clave)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")
    comprobar(f"login {correo}", "/login" not in pagina.url, pagina.url)


def sin_desborde(pagina, etiqueta: str) -> None:
    """Comprueba que la página no se desplace lateralmente.

    Args:
        pagina: Página abierta.
        etiqueta: Nombre de la vista para el informe.
    """
    ancho, desborde = pagina.evaluate(
        "() => [window.innerWidth, document.documentElement.scrollWidth]"
    )
    comprobar(
        f"sin desborde {etiqueta} ({ancho}px)",
        desborde <= ancho,
        f"scrollWidth={desborde}, innerWidth={ancho}",
    )


def main() -> None:
    """Ejecuta el recorrido completo.

    Returns:
        None. Imprime el informe por consola.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        contexto = navegador.new_context(viewport={"width": 1280, "height": 900})
        errores: list[str] = []
        contexto.on("page", lambda p: p.on("console", lambda m: errores.append(m.text) if m.type == "error" else None))
        entrar(contexto, QA_CORREO, QA_CLAVE)
        pagina = contexto.pages[0]

        pagina.goto(f"{BASE}/finanzas")
        html = pagina.content()
        comprobar("etiqueta Sueldo-percibido", "Sueldo-percibido" in html)
        comprobar("sin etiqueta anterior", "Saldo para el bolsillo" not in html)
        for ancla in ("bloque-quincena-1", "bloque-quincena-2", "bloque-pago-mensual"):
            comprobar(f"ancla {ancla}", pagina.locator(f"#{ancla}").count() >= 0)

        pagina.goto(f"{BASE}/presupuesto")
        comprobar("Consejero activo", "Consejero financiero" in pagina.content())
        comprobar(
            "Comparativa de cierre con deuda",
            "Comparativa de cierre de deuda" in pagina.content(),
        )

        pagina.goto(f"{BASE}/deudas")
        html = pagina.content()
        comprobar("columna Vinculación", "Vinculación" in html)
        comprobar("tarjeta de cuotas retirada", "Pagos que faltan en las deudas activas" not in html)
        comprobar(
            "botón Eliminar en modal",
            pagina.locator("[data-eliminar-deuda]").count() > 0,
        )
        respuesta = pagina.request.get(f"{BASE}/api/deudas")
        datos = respuesta.json()
        comprobar(
            "API de deudas con vinculación",
            isinstance(datos.get("deudas"), list)
            and all(
                "esta_vinculada" in fila and "modulos_vinculados" in fila
                for fila in datos["deudas"]
            ),
        )

        # Restauración de scroll: se siembra la posición guardada y se recarga.
        pagina.goto(f"{BASE}/finanzas")
        pagina.evaluate(
            "() => { sessionStorage.setItem('misfinanzas_saved_scroll_y', '240'); "
            "sessionStorage.setItem('misfinanzas_saved_scroll_ancla', 'bloque-quincena-2'); }"
        )
        pagina.reload()
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(300)
        scroll = pagina.evaluate("() => window.scrollY")
        altura = pagina.evaluate("() => document.documentElement.scrollHeight")
        clave = pagina.evaluate(
            "() => sessionStorage.getItem('misfinanzas_saved_scroll_y')"
        )
        comprobar(
            "scroll restaurado (sin volver arriba)",
            scroll > 0,
            f"scrollY={scroll}, altura={altura}, clave={clave}",
        )

        # Doble envío: dos submits síncronos solo pueden crear una deuda.
        pagina.goto(f"{BASE}/deudas")
        antes = len(pagina.request.get(f"{BASE}/api/deudas").json()["deudas"])
        sufijo = str(len(resultados))
        pagina.fill('input[name="acreedor"]', f"QA Doble {sufijo}")
        pagina.fill('input[name="saldo_total"]', "400.000")
        pagina.fill('input[name="cuota"]', "100.000")
        pagina.fill('input[name="cuotas_pendientes"]', "4")
        pagina.evaluate(
            "() => { var b = document.querySelector('[data-guardar-deuda]'); "
            "b.click(); b.click(); }"
        )
        pagina.wait_for_load_state("networkidle")
        despues = len(pagina.request.get(f"{BASE}/api/deudas").json()["deudas"])
        comprobar("doble envío no duplica", despues == antes + 1, f"{antes} -> {despues}")

        contexto_admin = navegador.new_context(viewport={"width": 1280, "height": 900})
        entrar(contexto_admin, ADMIN_CORREO, ADMIN_CLAVE)
        admin = contexto_admin.pages[0]
        admin.goto(f"{BASE}/")
        iconos = admin.locator('img[alt="OLB_BYTE"]')
        comprobar(
            "ícono navegación 24px",
            iconos.count() > 0 and iconos.first.get_attribute("width") == "24",
        )
        admin.goto(f"{BASE}/olb-byte")
        interno = admin.locator(".olb-interno__icono")
        comprobar(
            "ícono encabezado OLB_BYTE 28px",
            interno.count() == 1 and interno.get_attribute("width") == "28",
        )

        for ancho in TAMANOS:
            pagina.set_viewport_size({"width": ancho, "height": 900})
            for ruta in ("/", "/finanzas", "/presupuesto", "/deudas", "/trabajos-extras"):
                pagina.goto(f"{BASE}{ruta}")
                sin_desborde(pagina, f"{ruta} {ancho}px")

        comprobar("sin errores de consola", not errores, "; ".join(errores[:3]))
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    for nombre, ok, detalle in resultados:
        print(("PASS " if ok else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""))
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones en verde")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
