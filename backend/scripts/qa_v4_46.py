"""Gate QA de la SRS v4.44, secciones 8 y 9: deudas previas y gastos operativos."""

from __future__ import annotations

import re
from datetime import date

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import GastoOperativo

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


def limpiar_gastos() -> None:
    """Borra los gastos operativos del gate para repetirlo sin basura.

    Returns:
        None.
    """
    with FabricaSesiones() as bd:
        bd.query(GastoOperativo).delete(synchronize_session=False)
        bd.commit()


def iniciar(pagina, ancho: int) -> None:
    """Inicia sesión con la cuenta QA de administración.

    Args:
        pagina: Página de Playwright.
        ancho: Ancho de la ventana, solo para el prefijo del informe.

    Returns:
        None.
    """
    pagina.goto(f"{BASE}/login")
    pagina.fill("#campo-correo", CORREO)
    pagina.fill("#campo-clave", CLAVE)
    pagina.locator('form[action="/login"] button[type="submit"]').first.click()
    pagina.wait_for_load_state("networkidle")


def main() -> None:
    """Ejecuta el recorrido en escritorio y móvil.

    Returns:
        None. Imprime el informe.
    """
    limpiar_gastos()
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
            limpiar_gastos()
            contexto = navegador.new_context(
                viewport={"width": ancho, "height": 900}, service_workers="block"
            )
            pagina = contexto.new_page()
            prefijo = f"{ancho}px"
            iniciar(pagina, ancho)
            pagina.goto(f"{BASE}/olb-byte/cartera")
            pagina.wait_for_load_state("networkidle")

            # §8.1: tarjetas gemelas de igual ancho y altura.
            if ancho >= 768:
                gemelas = pagina.locator(".rejilla-paneles--proveedor").nth(1)
                tarjetas = gemelas.locator("> .panel").all()
                if len(tarjetas) == 2:
                    a, b = tarjetas[0].bounding_box(), tarjetas[1].bounding_box()
                    comprobar(
                        f"{prefijo}: tarjetas gemelas del mismo ancho y altura",
                        abs(a["width"] - b["width"]) <= 2
                        and abs(a["height"] - b["height"]) <= 2,
                        f"{a['width']:.0f}x{a['height']:.0f} vs {b['width']:.0f}x{b['height']:.0f}",
                    )

            fecha = pagina.locator('form[action$="gastos-operativos"] input[readonly]')
            valor_fecha = fecha.input_value()
            comprobar(
                f"{prefijo}: fecha bloqueada en MM/DD/AAAA",
                bool(re.fullmatch(r"\d{2}/\d{2}/\d{4}", valor_fecha)),
                valor_fecha,
            )

            # §8.2: registrar y editar un gasto operativo.
            formulario = pagina.locator('form[action$="/cartera/gastos-operativos"]').first
            formulario.locator('input[name="monto"]').fill("25000")
            formulario.locator('button:has-text("Registrar gasto")').click()
            pagina.wait_for_load_state("networkidle")
            total = pagina.locator(".panel__total strong").first.text_content() or ""
            comprobar(
                f"{prefijo}: el total del historial se actualiza al registrar",
                "25.000" in total,
                total,
            )

            abrir = pagina.locator('button[data-abrir-dialogo^="gasto-"]:visible').first
            abrir.click()
            pagina.wait_for_timeout(200)
            dialogo = pagina.locator("dialog.detalle-orden[open]").first
            comprobar(f"{prefijo}: el diálogo de edición se abre", dialogo.count() == 1)
            x = dialogo.locator(".detalle-orden__cerrar").bounding_box()
            caja = dialogo.bounding_box()
            comprobar(
                f"{prefijo}: X arriba a la derecha en el modal",
                bool(x and caja)
                and x["x"] > caja["x"] + caja["width"] * 0.7
                and x["y"] < caja["y"] + 60,
            )
            comprobar(
                f"{prefijo}: campos Fecha y Valor editables",
                dialogo.locator('input[name="fecha"][type="date"]').count() == 1
                and dialogo.locator('input[name="monto"]').count() == 1,
            )
            nombres = dialogo.locator("button[type='submit']").all_inner_texts()
            comprobar(
                f"{prefijo}: botones Guardar y Eliminar",
                any("Guardar" in n for n in nombres) and any("Eliminar" in n for n in nombres),
                str(nombres),
            )
            dialogo.locator('input[name="monto"]').fill("30000")
            dialogo.locator('button[type="submit"]:has-text("Guardar")').click()
            pagina.wait_for_load_state("networkidle")
            total = pagina.locator(".panel__total strong").first.text_content() or ""
            comprobar(
                f"{prefijo}: el total se recalcula al editar",
                "30.000" in total,
                total,
            )

            # §8.3: impacto inmediato en la analítica.
            pagina.goto(f"{BASE}/olb-byte/analitica")
            pagina.wait_for_load_state("networkidle")
            gasto_kpi = pagina.locator(".kpi__valor--gasto").first.text_content() or ""
            comprobar(
                f"{prefijo}: gasto operativo visible como KPI",
                "30.000" in gasto_kpi,
                gasto_kpi,
            )
            neta_kpi = (
                pagina.locator(".kpi__valor--positivo, .kpi__valor--negativo").first.text_content() or ""
            ).strip()
            comrobar_neta = "$" in neta_kpi
            # Verificación real: en la fila del mes, neta = ganancia − gasto.
            meses = (
                "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
            )
            fila_mes = pagina.locator(f".panel--tabla tbody tr:has-text('{meses[date.today().month - 1]}')").first
            if fila_mes.count():
                celdas = [c.strip() for c in fila_mes.locator("td").all_inner_texts()]

                def a_pesos(texto: str) -> int:
                    """Convierte una celda con formato COP a entero.

                    Args:
                        texto: Celda con símbolo y separadores de miles.

                    Returns:
                        El valor numérico sin formato.
                    """
                    return int(re.sub(r"[^0-9]", "", texto) or "0")

                # SRS v4.44 ADR-113 añadió la columna «Deudas proveedor» en la
                # posición 5: gasto=6, neta=7.
                comrobar_neta = (
                    a_pesos(celdas[7]) == a_pesos(celdas[4]) - a_pesos(celdas[6])
                    and a_pesos(celdas[6]) == 30000
                )
                detalle_neta = f"ganancia={celdas[4]} gasto={celdas[6]} neta={celdas[7]}"
            else:
                detalle_neta = neta_kpi
            comprobar(
                f"{prefijo}: la ganancia neta descuenta el gasto del mes",
                comrobar_neta,
                detalle_neta,
            )
            cabeceras = [
                t.strip().title()
                for t in pagina.locator(".panel--tabla thead th").all_inner_texts()
            ]
            comprobar(
                f"{prefijo}: columnas Gastos op. y Ganancia neta en las tablas",
                cabeceras.count("Gastos Op.") >= 2
                and cabeceras.count("Ganancia Neta") >= 2,
                str(cabeceras[:12]),
            )

            # Borrar con confirmación propia.
            pagina.goto(f"{BASE}/olb-byte/cartera")
            pagina.wait_for_load_state("networkidle")
            abrir = pagina.locator('button[data-abrir-dialogo^="gasto-"]:visible').first
            abrir.click()
            pagina.wait_for_timeout(200)
            dialogo = pagina.locator("dialog.detalle-orden[open]").first
            dialogo.locator('button[type="submit"]:has-text("Eliminar")').click()
            pagina.wait_for_timeout(200)
            confirmacion = pagina.locator("#modal-confirmacion:visible")
            comprobar(
                f"{prefijo}: confirmación propia antes de eliminar",
                confirmacion.count() == 1,
            )
            if confirmacion.count():
                confirmacion.locator("[data-confirm-aceptar]").click()
                pagina.wait_for_load_state("networkidle")
            total = pagina.locator(".panel__total strong").first.text_content() or ""
            comprobar(
                f"{prefijo}: el total vuelve a cero tras eliminar",
                "0" in total,
                total,
            )

            # §8.1: deuda anterior al sistema.
            formulario = pagina.locator('form[action$="deudas-iniciales"]').first
            formulario.locator('input[name="concepto"]').fill("Deuda QA anterior")
            formulario.locator('input[name="monto"]').fill("125000")
            formulario.locator('button:has-text("Registrar deuda")').click()
            pagina.wait_for_load_state("networkidle")
            filas = pagina.locator(".tabla-contenedor--movimientos tbody tr").all_inner_texts()
            comprobar(
                f"{prefijo}: la deuda anterior aparece como «Deuda inicial»",
                any("Deuda inicial" in fila and "Deuda QA anterior" in fila for fila in filas),
                str(filas[:2]),
            )

            contexto.close()
        navegador.close()

    limpiar_gastos()
    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
