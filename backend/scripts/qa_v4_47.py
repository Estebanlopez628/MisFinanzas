"""Gate QA de la SRS v4.44, sección 4.3: recuadro de totales de la factura.

Verifica el divisor TOTAL → ABONADO / SALDO y el fondo transparente con celdas
blancas en escritorio, móvil e impresión, y confirma que el PDF y el uso compartido
por WhatsApp consumen la misma plantilla y la misma hoja de estilos.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.base_datos import FabricaSesiones
from app.modelos import Venta
from app.servicios import comercial

BASE = "http://127.0.0.1:8000"
CORREO = "admin@olbbyte.co"
CLAVE = "Admin123*"

RUTA_APP = Path(__file__).resolve().parents[1] / "app"
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


def id_venta_con_saldo() -> str:
    """Busca o crea una orden con saldo pendiente para que aparezca ABONADO / SALDO.

    Returns:
        Identificador de la orden.
    """
    with FabricaSesiones() as bd:
        venta = bd.query(Venta).filter(Venta.saldo_pendiente > 0).first()
        if venta is not None:
            return venta.id_venta
        venta = comercial.registrar_venta(
            bd,
            "QA Factura v4.44",
            "3001112233",
            [
                comercial.LineaVenta(
                    nombre="Producto QA",
                    cantidad=1,
                    precio_unitario="150000",
                    costo_unitario="90000",
                )
            ],
        )
        return venta.id_venta


CONSULTA_TOTALES = """() => {
  const caja = document.querySelector('.totales-caja');
  const valores = [...document.querySelectorAll('.total-valor')];
  const etiquetas = [...document.querySelectorAll('.total-etiqueta')];
  const estilo = (el) => getComputedStyle(el);
  return {
    fondo: estilo(caja).backgroundColor,
    radio: estilo(caja).borderRadius,
    desbordamiento: estilo(caja).overflow,
    fondos: valores.map(v => estilo(v).backgroundColor),
    divisorSubtotal: estilo(valores[0]).borderBottomWidth + ' ' + estilo(valores[0]).borderBottomColor,
    divisorTotal: estilo(valores[1]).borderBottomWidth + ' ' + estilo(valores[1]).borderBottomColor,
    divisorEtiquetaTotal: estilo(etiquetas[1]).borderBottomWidth,
    bordeArribaAbono: estilo(etiquetas[2]).borderTopWidth,
    filas: document.querySelectorAll('.total-fila').length,
  };
}"""

CONSULTA_MARCA = """() => {
  const contenedor = document.querySelector('.marca-contenedor');
  const eslogan = document.querySelector('.marca-eslogan');
  const imagen = contenedor.querySelector('img');
  const e = getComputedStyle(contenedor);
  const cajaLogo = imagen.getBoundingClientRect();
  const cajaEslogan = eslogan.getBoundingClientRect();
  return {
    display: e.display,
    direccion: e.flexDirection,
    alineacion: e.alignItems,
    texto: e.textAlign,
    esloganTexto: getComputedStyle(eslogan).textAlign,
    desalineacion: Math.abs((cajaLogo.x + cajaLogo.width / 2) - (cajaEslogan.x + cajaEslogan.width / 2)),
  };
}"""


def main() -> None:
    """Recorre la factura en web, móvil e impresión.

    Returns:
        None. Imprime el informe.
    """
    id_venta = id_venta_con_saldo()
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(headless=True)
        for ancho in (1280, 375):
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
            pagina.goto(f"{BASE}/olb-byte/factura/{id_venta}/hoja")
            pagina.wait_for_load_state("networkidle")

            marco = pagina.evaluate(CONSULTA_MARCA)
            comprobar(
                f"{prefijo}: logo y eslogan agrupados y centrados",
                marco["display"] == "flex"
                and marco["direccion"] == "column"
                and marco["alineacion"] == "center"
                and marco["texto"] == "center"
                and marco["esloganTexto"] == "center"
                and marco["desalineacion"] <= 2,
                str(marco),
            )

            for medio in ("screen", "print"):
                pagina.emulate_media(media=medio)
                datos = pagina.evaluate(CONSULTA_TOTALES)
                etiqueta = f"{prefijo}/{medio}"
                comprobar(
                    f"{etiqueta}: caja transparente con radio y recorte",
                    datos["fondo"] == "rgba(0, 0, 0, 0)"
                    and datos["radio"] == "10px"
                    and datos["desbordamiento"] == "hidden",
                    f"{datos['fondo']} radio={datos['radio']}",
                )
                comprobar(
                    f"{etiqueta}: blanco solo en las celdas de valor",
                    all(fondo == "rgb(255, 255, 255)" for fondo in datos["fondos"]),
                    str(datos["fondos"]),
                )
                comprobar(
                    f"{etiqueta}: divisor TOTAL→ABONADO igual a SUBTOTAL→TOTAL",
                    datos["divisorTotal"] == datos["divisorSubtotal"] == "1px rgb(184, 214, 245)"
                    and datos["divisorEtiquetaTotal"] == "1px"
                    and datos["bordeArribaAbono"] == "0px",
                    f"{datos['divisorSubtotal']} / {datos['divisorTotal']}",
                )
                comprobar(
                    f"{etiqueta}: ABONADO / SALDO presente",
                    datos["filas"] == 3,
                    f"filas={datos['filas']}",
                )
            pagina.emulate_media(media="screen")
            contexto.close()
        navegador.close()

    # Las tres salidas usan la misma plantilla y la misma hoja de estilos.
    plantilla = (RUTA_APP / "templates/olb_byte/_hoja_factura.html").read_text(encoding="utf-8")
    pdf = (RUTA_APP / "servicios/factura_pdf.py").read_text(encoding="utf-8")
    css = (RUTA_APP / "static/css/factura-olb.css").read_text(encoding="utf-8")
    comprobar(
        "PDF y WhatsApp comparten plantilla y CSS con la vista",
        "_hoja_factura.html" in pdf
        and "factura-olb.css" in pdf
        and "total-fila--con-abono" in plantilla,
    )
    impresion = css.split("@media print", 1)[1].split(".totales-caja {", 1)[1].split("}", 1)[0]
    comprobar(
        "La impresión no contradice el diseño del recuadro",
        "background" not in impresion and "border" not in impresion,
        impresion.strip(),
    )

    fallos = [fila for fila in resultados if not fila[1]]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
