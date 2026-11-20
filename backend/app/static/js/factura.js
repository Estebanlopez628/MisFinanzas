/**
 * Factura y recibo de abono de OLB_BYTE como imagen PNG (ADR-50).
 *
 * Responsabilidad
 * ---------------
 * - Pedir al servidor la hoja HTML de la factura o del recibo y convertirla en PNG
 *   en el propio navegador con `html-to-image` (vendor/html-to-image.js, local).
 * - Preparar la imagen al cargar la página, para que el clic responda al instante.
 * - WhatsApp: abre la conversación con el número del cliente de inmediato, copia la
 *   imagen al portapapeles (si el navegador lo permite) y la descarga como respaldo.
 * - Descargar la imagen cuando el botón lo pide.
 *
 * El servidor no genera imágenes ni PDF. Ninguna regla de negocio vive aquí.
 */

(function () {
  "use strict";

  var COLOR_FACTURA = "#ffffff";
  var COLOR_RECIBO = "#0f172a";
  var imagenesPreparadas = {};

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
   * Espera a que una imagen esté cargada y decodificada para poder dibujarla.
   *
   * @param {HTMLImageElement} imagen Logo o imagen de la hoja.
   * @returns {Promise<void>} Se resuelve también si la imagen falla, para no bloquear la captura.
   */
  function esperarImagen(imagen) {
    var cargada = imagen.complete
      ? Promise.resolve()
      : new Promise(function (resolver) {
          imagen.addEventListener("load", resolver);
          imagen.addEventListener("error", resolver);
        });
    return cargada.then(function () {
      return imagen.decode ? imagen.decode().catch(function () {}) : null;
    });
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
        var imagenes = Array.prototype.slice.call(contenedor.querySelectorAll("img"));
        return Promise.all(imagenes.map(esperarImagen)).then(function () {
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
   * Devuelve la imagen de una hoja, reutilizando la que ya se preparó al cargar.
   *
   * @param {string} url Dirección del fragmento HTML.
   * @returns {Promise<Blob>} Imagen PNG.
   */
  function imagenDe(url) {
    if (!imagenesPreparadas[url]) {
      imagenesPreparadas[url] = crearPng(url).catch(function (error) {
        delete imagenesPreparadas[url];
        throw error;
      });
    }
    return imagenesPreparadas[url];
  }

  /**
   * Copia una imagen PNG al portapapeles para pegarla en WhatsApp (Ctrl+V).
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
   * Abre la conversación de WhatsApp del cliente y deja lista la imagen para adjuntarla.
   *
   * La ventana se abre dentro del clic para que el navegador no la bloquee; la imagen se
   * prepara en paralelo, así que la conversación aparece sin esperar la captura.
   *
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function enviarPorWhatsapp(boton) {
    var url = boton.getAttribute("data-fragmento");
    var nombre = boton.getAttribute("data-nombre") || "factura.png";
    var whatsapp = boton.getAttribute("data-whatsapp") || "";
    var etiqueta = boton.textContent;

    if (boton.hasAttribute("data-sin-celular")) {
      window.alert("Esta orden no tiene celular del cliente. Agrégalo en su ficha para abrir el chat.");
      return;
    }

    window.open(whatsapp, "_blank");
    boton.disabled = true;
    boton.textContent = "Preparando…";

    imagenDe(url)
      .then(function (blob) {
        descargar(blob, nombre);
        return copiarImagen(blob).then(function (copiada) {
          window.alert(
            copiada
              ? "Se abrió el chat del cliente y la imagen se copió. Pégala con Ctrl+V; también quedó descargada."
              : "Se abrió el chat del cliente y la imagen se descargó. Adjúntala con el clip antes de enviar."
          );
        });
      })
      .catch(function (error) {
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

    imagenDe(url)
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

  // Preparar la imagen al cargar: el clic posterior no espera a la captura.
  var botonesPreparar = document.querySelectorAll("[data-compartir], [data-compartir-factura], [data-descargar-imagen]");
  for (var p = 0; p < botonesPreparar.length; p += 1) {
    var urlPreparar = botonesPreparar[p].getAttribute("data-fragmento");
    if (urlPreparar && window.htmlToImage) {
      imagenDe(urlPreparar).catch(function () {});
    }
  }

  var botonesCompartir = document.querySelectorAll("[data-compartir], [data-compartir-factura]");
  for (var i = 0; i < botonesCompartir.length; i += 1) {
    botonesCompartir[i].addEventListener("click", function (evento) {
      enviarPorWhatsapp(evento.currentTarget);
    });
  }

  var botonesDescargar = document.querySelectorAll("[data-descargar-imagen]");
  for (var j = 0; j < botonesDescargar.length; j += 1) {
    botonesDescargar[j].addEventListener("click", function (evento) {
      descargarImagen(evento.currentTarget);
    });
  }
})();
