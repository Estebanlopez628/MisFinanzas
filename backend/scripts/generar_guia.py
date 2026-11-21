r"""Generador y verificador de `Guia.md`.

Responsabilidad
---------------
Mantener sincronizado el inventario automático de la guía con el código real:

- Recorre `backend/app` (Python, plantillas, estáticos) y extrae módulos, clases,
  funciones y métodos con su docstring resumido.
- Reescribe el bloque delimitado por `MARCA_INICIO` y `MARCA_FIN` dentro de
  `Guia.md`; el resto de la guía (explicaciones y fichas) es manual.
- `--verificar` falla si un módulo, clase, función o método no tiene docstring, o
  si un archivo del inventario no tiene su ficha en la guía.

Uso
---
```bash
cd backend
.\.venv\Scripts\python scripts\generar_guia.py            # actualiza el inventario
.\.venv\Scripts\python scripts\generar_guia.py --verificar  # valida docstrings y fichas
```
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]
CARPETA_APP = RAIZ_REPO / "backend" / "app"
RUTA_GUIA = RAIZ_REPO / "Guia.md"

MARCA_INICIO = "<!-- INVENTARIO:INICIO -->"
MARCA_FIN = "<!-- INVENTARIO:FIN -->"

EXTENSIONES = {".py", ".html", ".js", ".css", ".webmanifest"}
# Carpetas que no aportan documentación (caché de bytecode, respaldos locales).
EXCLUIDAS = {"__pycache__", "respaldos", "datos"}

# Ancho máximo del resumen de un docstring dentro del inventario.
ANCHO_RESUMEN = 120


@dataclass
class Simbolo:
    """Clase, función o método encontrado en un archivo Python.

    Attributes:
        nombre: Nombre del símbolo.
        tipo: `clase`, `función` o `método`.
        linea: Línea donde empieza.
        resumen: Primera línea del docstring (vacía si falta).
        metodos: Métodos de la clase; vacío en funciones.
    """

    nombre: str
    tipo: str
    linea: int
    resumen: str
    metodos: list["Simbolo"] = field(default_factory=list)


@dataclass
class Archivo:
    """Archivo inventariado y su contenido documentable.

    Attributes:
        ruta: Ruta absoluta.
        relativa: Ruta relativa a la raíz del repositorio, con `/`.
        lineas: Total de líneas.
        resumen: Descripción breve del archivo.
        simbolos: Símbolos de primer nivel (Python).
        sin_docstring: Símbolos que deberían documentarse y no lo están.
    """

    ruta: Path
    relativa: str
    lineas: int
    resumen: str
    simbolos: list[Simbolo] = field(default_factory=list)
    sin_docstring: list[str] = field(default_factory=list)


def _resumen(texto: str | None) -> str:
    """Extrae la primera línea útil de un docstring.

    Args:
        texto: Docstring completo o `None`.

    Returns:
        Resumen en una sola línea, truncado a `ANCHO_RESUMEN` caracteres.
    """
    if not texto:
        return ""
    for linea in texto.strip().splitlines():
        limpia = linea.strip()
        if limpia:
            if len(limpia) > ANCHO_RESUMEN:
                return limpia[: ANCHO_RESUMEN - 1].rstrip() + "…"
            return limpia
    return ""


def _docstring(nodo: ast.AST) -> str | None:
    """Devuelve el docstring de un nodo AST.

    Args:
        nodo: Módulo, clase o función.

    Returns:
        El docstring o `None` si no existe.
    """
    return ast.get_docstring(nodo, clean=True)


def _analizar_python(archivo: Archivo, contenido: str) -> None:
    """Rellena `simbolos` y `sin_docstring` de un archivo Python.

    Args:
        archivo: Registro que se completa.
        contenido: Texto del archivo.

    Raises:
        SyntaxError: Si el archivo no es Python válido (se propaga para no
            publicar un inventario incompleto).
    """
    arbol = ast.parse(contenido, filename=archivo.relativa)
    archivo.resumen = _resumen(_docstring(arbol))
    if not archivo.resumen:
        archivo.sin_docstring.append("módulo")

    for nodo in arbol.body:
        if isinstance(nodo, ast.ClassDef):
            simbolo = Simbolo(
                nombre=nodo.name,
                tipo="clase",
                linea=nodo.lineno,
                resumen=_resumen(_docstring(nodo)),
            )
            if not simbolo.resumen:
                archivo.sin_docstring.append(f"clase {nodo.name}")
            for hijo in nodo.body:
                if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    metodo = Simbolo(
                        nombre=hijo.name,
                        tipo="método",
                        linea=hijo.lineno,
                        resumen=_resumen(_docstring(hijo)),
                    )
                    # Los métodos dunder generados por el framework no se exigen.
                    if not metodo.resumen and not hijo.name.startswith("__"):
                        archivo.sin_docstring.append(
                            f"método {nodo.name}.{hijo.name}"
                        )
                    simbolo.metodos.append(metodo)
            archivo.simbolos.append(simbolo)
        elif isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            simbolo = Simbolo(
                nombre=nodo.name,
                tipo="función",
                linea=nodo.lineno,
                resumen=_resumen(_docstring(nodo)),
            )
            if not simbolo.resumen:
                archivo.sin_docstring.append(f"función {nodo.name}")
            archivo.simbolos.append(simbolo)


def _resumen_plantilla(contenido: str) -> str:
    """Describe una plantilla Jinja2 a partir de su bloque `titulo`.

    Args:
        contenido: Texto de la plantilla.

    Returns:
        Texto como «Plantilla: Registro y Detalles de deudas» o la primera línea.
    """
    coincidencia = re.search(
        r"{%\s*block\s+titulo\s*%}(.*?){%\s*endblock\s*%}", contenido, re.DOTALL
    )
    if coincidencia:
        titulo = " ".join(
            re.sub(r"{{.*?}}", "", coincidencia.group(1)).split()
        )
        if titulo:
            return f"Plantilla: {titulo}"
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if limpia.startswith("{#"):
            return _resumen(limpia.strip("{#- }"))
    return "Plantilla Jinja2"


def _resumen_estatico(contenido: str) -> str:
    """Describe un archivo JavaScript o CSS con su primer comentario.

    Args:
        contenido: Texto del archivo.

    Returns:
        Primera línea de comentario con texto o una descripción genérica.
    """
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if not limpia.startswith(("/*", "//", "*")):
            continue
        texto = _resumen(limpia.strip("/*! "))
        # Descarta separadores decorativos como `/* ===== */`.
        if texto and sum(letra.isalpha() for letra in texto) >= 4:
            return texto
    return "Recurso estático"


def _simbolos_js(contenido: str) -> list[Simbolo]:
    """Extrae las funciones declaradas en un archivo JavaScript.

    Args:
        contenido: Texto del archivo.

    Returns:
        Lista de funciones con su línea y el comentario inmediatamente previo.
    """
    lineas = contenido.splitlines()
    simbolos: list[Simbolo] = []
    patron = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
    for indice, linea in enumerate(lineas):
        coincidencia = patron.match(linea.strip())
        if not coincidencia:
            continue
        resumen = ""
        cursor = indice - 1
        while cursor >= 0 and not lineas[cursor].strip():
            cursor -= 1
        if cursor >= 0:
            previa = lineas[cursor].strip()
            if previa.startswith("//"):
                resumen = _resumen(previa.lstrip("/ "))
        simbolos.append(
            Simbolo(
                nombre=coincidencia.group(1),
                tipo="función",
                linea=indice + 1,
                resumen=resumen,
            )
        )
    return simbolos


def _iterar_archivos() -> list[Path]:
    """Lista los archivos documentables bajo `backend/app`.

    Returns:
        Rutas ordenadas alfabéticamente, sin carpetas excluidas.
    """
    encontrados = [
        ruta
        for ruta in CARPETA_APP.rglob("*")
        if ruta.is_file()
        and ruta.suffix in EXTENSIONES
        and not (EXCLUIDAS & set(ruta.parts))
    ]
    return sorted(encontrados, key=lambda ruta: ruta.as_posix())


def inventariar() -> list[Archivo]:
    """Analiza todos los archivos documentables del proyecto.

    Returns:
        Lista de `Archivo` ordenada por ruta relativa.
    """
    archivos: list[Archivo] = []
    for ruta in _iterar_archivos():
        contenido = ruta.read_text(encoding="utf-8-sig")
        archivo = Archivo(
            ruta=ruta,
            relativa=ruta.relative_to(RAIZ_REPO).as_posix(),
            lineas=contenido.count("\n") + 1,
            resumen="",
        )
        if ruta.suffix == ".py":
            _analizar_python(archivo, contenido)
        elif ruta.suffix == ".html":
            archivo.resumen = _resumen_plantilla(contenido)
        elif ruta.suffix in {".js", ".css"}:
            archivo.resumen = _resumen_estatico(contenido)
            if ruta.suffix == ".js":
                archivo.simbolos = _simbolos_js(contenido)
        else:
            archivo.resumen = "Manifiesto PWA"
        archivos.append(archivo)
    return archivos


def _contar(archivos: list[Archivo]) -> dict[str, int]:
    """Resume el tamaño del inventario.

    Args:
        archivos: Archivos analizados.

    Returns:
        Conteo de archivos por tipo y de símbolos documentados.
    """
    conteo = {
        "archivos": len(archivos),
        "python": 0,
        "plantillas": 0,
        "estaticos": 0,
        "clases": 0,
        "funciones": 0,
        "metodos": 0,
    }
    for archivo in archivos:
        if archivo.ruta.suffix == ".py":
            conteo["python"] += 1
        elif archivo.ruta.suffix == ".html":
            conteo["plantillas"] += 1
        else:
            conteo["estaticos"] += 1
        for simbolo in archivo.simbolos:
            clave = {
                "clase": "clases",
                "función": "funciones",
                "método": "metodos",
            }[simbolo.tipo]
            conteo[clave] += 1
            conteo["metodos"] += sum(
                1 for metodo in simbolo.metodos if not metodo.nombre.startswith("__")
            )
    return conteo


def _nombre_corto(archivo: Archivo) -> str:
    """Devuelve la ruta relativa a `backend/app` para agrupar por carpeta.

    Args:
        archivo: Archivo inventariado.

    Returns:
        Ruta sin el prefijo `backend/app/`.
    """
    return archivo.relativa.removeprefix("backend/app/")


def generar_inventario(archivos: list[Archivo]) -> str:
    """Construye el bloque Markdown del inventario.

    Args:
        archivos: Archivos analizados.

    Returns:
        Texto listo para insertarse entre las marcas.
    """
    conteo = _contar(archivos)
    lineas = [
        "### Resumen del inventario",
        "",
        f"- **{conteo['archivos']} archivos** documentados: "
        f"{conteo['python']} Python, {conteo['plantillas']} plantillas Jinja2 y "
        f"{conteo['estaticos']} recursos estáticos.",
        f"- **{conteo['clases']} clases**, **{conteo['funciones']} funciones** y "
        f"**{conteo['metodos']} métodos** de clase.",
        "",
        "### Detalle por archivo",
        "",
    ]

    agrupados: dict[str, list[Archivo]] = {}
    for archivo in archivos:
        relativa = _nombre_corto(archivo)
        carpeta = str(Path(relativa).parent.as_posix())
        agrupados.setdefault(carpeta, []).append(archivo)

    for carpeta in sorted(agrupados):
        encabezado = "backend/app" if carpeta == "." else f"backend/app/{carpeta}"
        lineas.append(f"#### `{encabezado}/`")
        lineas.append("")
        for archivo in sorted(agrupados[carpeta], key=lambda a: a.relativa):
            nombre = Path(_nombre_corto(archivo)).name
            detalle = f"- **`{nombre}`** · {archivo.lineas} líneas"
            if archivo.resumen:
                detalle += f" — {archivo.resumen}"
            lineas.append(detalle)
            if not archivo.simbolos:
                continue
            clases = [s for s in archivo.simbolos if s.tipo == "clase"]
            funciones = [s for s in archivo.simbolos if s.tipo == "función"]
            if clases:
                nombres = ", ".join(f"`{s.nombre}`" for s in clases)
                lineas.append(f"  - Clases: {nombres}")
            if funciones:
                nombres = ", ".join(f"`{s.nombre}`" for s in funciones)
                lineas.append(f"  - Funciones: {nombres}")
        lineas.append("")

    return "\n".join(lineas).rstrip() + "\n"


def actualizar_guia(bloque: str) -> None:
    """Sustituye el inventario entre las marcas de `Guia.md`.

    Args:
        bloque: Markdown nuevo del inventario.

    Raises:
        SystemExit: Si la guía o las marcas no existen.
    """
    if not RUTA_GUIA.exists():
        raise SystemExit(f"No existe {RUTA_GUIA}; crea la guía antes de generar.")
    texto = RUTA_GUIA.read_text(encoding="utf-8")
    if MARCA_INICIO not in texto or MARCA_FIN not in texto:
        raise SystemExit(
            "Faltan las marcas del inventario en Guia.md: "
            f"{MARCA_INICIO} / {MARCA_FIN}"
        )
    inicio = texto.index(MARCA_INICIO) + len(MARCA_INICIO)
    fin = texto.index(MARCA_FIN)
    nuevo = f"{texto[:inicio]}\n\n{bloque}\n{texto[fin:]}"
    RUTA_GUIA.write_text(nuevo, encoding="utf-8", newline="\n")
    print(f"Inventario actualizado en {RUTA_GUIA}.")


def _fichas_presentes(texto: str) -> set[str]:
    """Extrae las rutas que ya tienen ficha en la guía.

    Args:
        texto: Contenido de `Guia.md`.

    Returns:
        Conjunto de rutas relativas con encabezado de nivel 3.
    """
    return set(re.findall(r"^### `(backend/app/[^`]+)`", texto, re.MULTILINE))


def verificar(archivos: list[Archivo]) -> list[str]:
    """Comprueba docstrings y fichas de la guía.

    Args:
        archivos: Archivos analizados.

    Returns:
        Lista de problemas; vacía si todo está correcto.
    """
    problemas: list[str] = []
    for archivo in archivos:
        for faltante in archivo.sin_docstring:
            problemas.append(f"{archivo.relativa}: sin docstring en {faltante}")

    if RUTA_GUIA.exists():
        texto = RUTA_GUIA.read_text(encoding="utf-8")
        fichas = _fichas_presentes(texto)
        for archivo in archivos:
            if archivo.relativa not in fichas:
                problemas.append(f"{archivo.relativa}: falta su ficha en Guia.md")
        for ficha in sorted(fichas):
            if not (RAIZ_REPO / ficha).exists():
                problemas.append(f"Guia.md: ficha de archivo inexistente {ficha}")
    else:
        problemas.append("No existe Guia.md")
    return problemas


def main() -> int:
    """Ejecuta la generación o la verificación según los argumentos.

    Returns:
        Código de salida: `0` si todo está correcto, `1` si hay problemas.
    """
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument(
        "--verificar",
        action="store_true",
        help="No escribe nada: solo valida docstrings y fichas.",
    )
    argumentos = analizador.parse_args()

    archivos = inventariar()
    if argumentos.verificar:
        problemas = verificar(archivos)
        if problemas:
            print(f"{len(problemas)} problema(s) encontrados:")
            for problema in problemas:
                print(f"  - {problema}")
            return 1
        print(
            f"Guía correcta: {len(archivos)} archivos con ficha y sin docstrings "
            "pendientes."
        )
        return 0

    actualizar_guia(generar_inventario(archivos))
    conteo = _contar(archivos)
    print(
        f"{conteo['archivos']} archivos, {conteo['clases']} clases, "
        f"{conteo['funciones']} funciones y {conteo['metodos']} métodos."
    )
    pendientes = sum(len(archivo.sin_docstring) for archivo in archivos)
    if pendientes:
        print(f"Aviso: {pendientes} símbolo(s) sin docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
