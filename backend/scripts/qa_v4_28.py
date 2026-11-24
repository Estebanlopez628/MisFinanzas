"""Gate QA de la SRS v4.28 (bloques A y B) en Chromium, con ambos roles."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
CUENTAS = (
    ("admin", "prueba_qa_admin@misfinanzas.local", "QA_Admin_2026!"),
    ("usuario", "prueba_qa@misfinanzas.local", "QA_MisFinanzas_2026!"),
)

resultados: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Registra una comprobación.

    Args:
        nombre: Etiqueta legible.
        condicion: Resultado de la comprobación.
        detalle: Información extra para el informe.
    """
    resultados.append((nombre, bool(condicion), detalle))


def main() -> None:
    """Ejecuta el recorrido completo.

    Returns:
        None. Imprime el informe.
    """
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
            for etiqueta, correo, clave in CUENTAS:
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
                pagina.fill("#campo-correo", correo)
                pagina.fill("#campo-clave", clave)
                pagina.locator('form[action="/login"] button[type="submit"]').first.click()
                pagina.wait_for_load_state("networkidle")
                prefijo = f"{ancho}px {etiqueta}"

                comprobar(f"{prefijo}: login", "/login" not in pagina.url, pagina.url)
                cabecera = pagina.locator("header").inner_text()
                comprobar(
                    f"{prefijo}: sin rol en la cabecera",
                    "USER_FINANZAS" not in cabecera and "ADMIN_OLB" not in cabecera,
                    cabecera[:80],
                )

                pagina.goto(f"{BASE}/presupuesto")
                pagina.wait_for_load_state("networkidle")
                cuerpo = pagina.content()
                comprobar(f"{prefijo}: componente nuevo", "impacto-deudas" in cuerpo)
                comprobar(
                    f"{prefijo}: sin gráfica vieja",
                    "Base frente a optimizado" not in cuerpo
                    and "comparativa__grafica" not in cuerpo,
                )

                pagina.goto(f"{BASE}/finanzas")
                pagina.wait_for_load_state("networkidle")
                comprobar(
                    f"{prefijo}: sin enlace de gastos",
                    "Ver todos los gastos fijos" not in pagina.content(),
                )

                pagina.goto(f"{BASE}/ayuda")
                pagina.wait_for_load_state("networkidle")
                ayuda = pagina.content()
                comprobar(
                    f"{prefijo}: marca correcta",
                    "Mis Finanzas" in ayuda and "MisFinanzas" not in ayuda,
                )

                pagina.goto(f"{BASE}/perfil")
                pagina.wait_for_load_state("networkidle")
                perfil = pagina.content()
                comprobar(
                    f"{prefijo}: seguridad sin términos técnicos",
                    "PBKDF2" not in perfil and "SHA256" not in perfil,
                )
                comprobar(f"{prefijo}: sin errores de consola", not errores, "; ".join(errores[:2]))
                contexto.close()
        navegador.close()

    fallos = [fila for fila in resultados if not fila[1]]
    for nombre, ok, detalle in resultados:
        print(("PASS " if ok else "FAIL ") + nombre + (f" — {detalle}" if detalle else ""))
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
