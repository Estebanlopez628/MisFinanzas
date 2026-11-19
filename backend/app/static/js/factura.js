/**
 * Factura y recibo de abono de OLB_BYTE como imagen PNG (ADR-50).
 *
 * Responsabilidad
 * ---------------
 * - Pedir al servidor la hoja HTML de la factura o del recibo y convertirla en PNG
 *   en el propio navegador con `html-to-image` (vendor/html-to-image.js, local).
 * - Compartir la imagen: en móvil con la hoja de compartir del sistema (archivo
 *   adjunto); en escritorio copiarla al portapapeles para pegarla en WhatsApp Web
 *   y descargarla como respaldo.
 * - Descargar la imagen cuando el botón lo pide.
 *
 * El servidor no genera imágenes ni PDF. Ninguna regla de negocio vive aquí.
 */

(function () {
  "use strict";

  var COLOR_FACTURA = "#ffffff";
  var COLOR_RECIBO = "#0f172a";

  /**
   * Guarda un archivo en el equipo mediante un enlace temporal.
   *
   * @param {Blob} blob Contenido del archivo.
   * @param {string} nombre Nombre con el que se descarga.
   */
  function descargar(blob, nombre) {
    var url = URL.createObjectURL(blob);
    var enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombre;
    document.body.appendChild(enlace);
    enlace.click();
    document.body.removeChild(enlace);
    window.setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  /**
   * Espera a que las imágenes de un contenedor estén listas para dibujarse.
   *
   * @param {HTMLElement} raiz Contenedor con la hoja.
   * @returns {Promise<void>} Se resuelve cuando todas las imágenes terminan de cargar.
   */
  function esperarImagenes(raiz) {
    var imagenes = Array.prototype.slice.call(raiz.querySelectorAll("img"));
    return Promise.all(
      imagenes.map(function (imagen) {
        if (imagen.complete) {
          return Promise.resolve();
        }
        return new Promise(function (resolver) {
          imagen.onload = resolver;
          imagen.onerror = resolver;
        });
      })
    );
  }

  /**
   * Descarga la hoja desde el servidor y la monta fuera de la vista para capturarla.
   *
   * @param {string} url Dirección del fragmento HTML de la hoja.
   * @returns {Promise<HTMLElement>} Contenedor ya montado en el documento.
   */
  function montarHoja(url) {
    return fetch(url, { credentials: "same-origin" })
      .then(function (respuesta) {
        if (!respuesta.ok) {
          throw new Error("No se pudo preparar la imagen. Revisa que tengas acceso al módulo.");
        }
        return respuesta.text();
      })
      .then(function (html) {
        var contenedor = document.createElement("div");
        contenedor.setAttribute("aria-hidden", "true");
        contenedor.style.cssText =
          "position:fixed;left:-10000px;top:0;width:850px;background:#ffffff;";
        contenedor.innerHTML = html;
        document.body.appendChild(contenedor);
        return esperarImagenes(contenedor).then(function () {
          return contenedor;
        });
      });
  }

  /**
   * Convierte la hoja de una dirección en un PNG de doble resolución.
   *
   * @param {string} url Dirección del fragmento HTML.
   * @returns {Promise<Blob>} Imagen PNG.
   */
  function crearPng(url) {
    var libreria = window.htmlToImage;
    if (!libreria) {
      return Promise.reject(new Error("La herramienta de imagen no cargó. Recarga la página."));
    }
    return montarHoja(url).then(function (contenedor) {
      var nodo = contenedor.querySelector(".hoja-factura") || contenedor.querySelector(".captura-recibo");
      if (!nodo) {
        document.body.removeChild(contenedor);
        throw new Error("No se encontró el contenido para la imagen.");
      }
      var fondo = nodo.classList.contains("hoja-factura") ? COLOR_FACTURA : COLOR_RECIBO;
      return libreria
        .toBlob(nodo, { pixelRatio: 2, backgroundColor: fondo, cacheBust: false })
        .then(
          function (blob) {
            document.body.removeChild(contenedor);
            return blob;
          },
          function (error) {
            document.body.removeChild(contenedor);
            throw error;
          }
        );
    });
  }

  /**
   * Copia una imagen PNG al portapapeles para pegarla en WhatsApp Web (Ctrl+V).
   *
   * @param {Blob} blob Imagen a copiar.
   * @returns {Promise<boolean>} `true` si el navegador la copió.
   */
  function copiarImagen(blob) {
    if (!navigator.clipboard || typeof window.ClipboardItem === "undefined") {
      return Promise.resolve(false);
    }
    return navigator.clipboard
      .write([new window.ClipboardItem({ "image/png": blob })])
      .then(
        function () {
          return true;
        },
        function () {
          return false;
        }
      );
  }

  /**
   * Comparte la imagen: hoja de compartir en móvil; portapapeles y descarga en PC.
   *
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function compartir(boton) {
    var url = boton.getAttribute("data-fragmento");
    var nombre = boton.getAttribute("data-nombre") || "imagen.png";
    var texto = boton.getAttribute("data-texto") || "";
    var whatsapp = boton.getAttribute("data-whatsapp") || "";
    var etiqueta = boton.textContent;

    // La ventana se abre dentro del clic para que el navegador no la bloquee.
    var ventana = whatsapp ? window.open("", "_blank") : null;
    boton.disabled = true;
    boton.textContent = "Preparando…";

    crearPng(url)
      .then(function (blob) {
        var archivo = new File([blob], nombre, { type: "image/png" });
        if (navigator.share && navigator.canShare && navigator.canShare({ files: [archivo] })) {
          if (ventana) {
            ventana.close();
          }
          return navigator.share({ files: [archivo], text: texto, title: nombre });
        }
        return copiarImagen(blob).then(function (copiada) {
          descargar(blob, nombre);
          if (ventana) {
            ventana.location.href = whatsapp;
          }
          window.alert(
            copiada
              ? "La imagen se copió y se descargó. En WhatsApp, pégala con Ctrl+V."
              : "La imagen se descargó. En WhatsApp, toca el clip y adjúntala antes de enviar."
          );
        });
      })
      .catch(function (error) {
        if (ventana) {
          ventana.close();
        }
        if (error && error.name === "AbortError") {
          return;
        }
        window.alert((error && error.message) || "No se pudo preparar la imagen.");
      })
      .then(function () {
        boton.disabled = false;
        boton.textContent = etiqueta;
      });
  }

  /**
   * Descarga la imagen en el equipo.
   *
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function descargarImagen(boton) {
    var url = boton.getAttribute("data-fragmento");
    var nombre = boton.getAttribute("data-nombre") || "imagen.png";
    var etiqueta = boton.textContent;
    boton.disabled = true;
    boton.textContent = "Preparando…";

    crearPng(url)
      .then(function (blob) {
        descargar(blob, nombre);
      })
      .catch(function (error) {
        window.alert((error && error.message) || "No se pudo preparar la imagen.");
      })
      .then(function () {
        boton.disabled = false;
        boton.textContent = etiqueta;
      });
  }

  var botonesCompartir = document.querySelectorAll("[data-compartir], [data-compartir-factura]");
  for (var i = 0; i < botonesCompartir.length; i += 1) {
    botonesCompartir[i].addEventListener("click", function (evento) {
      compartir(evento.currentTarget);
    });
  }

  var botonesDescargar = document.querySelectorAll("[data-descargar-imagen]");
  for (var j = 0; j < botonesDescargar.length; j += 1) {
    botonesDescargar[j].addEventListener("click", function (evento) {
      descargarImagen(evento.currentTarget);
    });
  }
})();
