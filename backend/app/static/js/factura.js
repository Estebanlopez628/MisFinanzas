/**
 * Factura y recibo de abono de OLB_BYTE como imagen PNG (ADR-50).
 *
 * Responsabilidad
 * ---------------
 * - Pedir al servidor la hoja HTML de la factura o del recibo y convertirla en PNG
 *   en el propio navegador con `html-to-image` (vendor/html-to-image.js, local).
 * - Preparar la imagen al cargar la página, para que el clic responda al instante.
 * - Compartir por WhatsApp:
 *   · Móvil con soporte de archivos: abre la hoja de compartir del sistema con el PNG
 *     adjunto y el mensaje (la app de WhatsApp recibe la imagen completa).
 *   · Escritorio: copia el PNG al portapapeles en el mismo clic, abre la conversación
 *     del número del cliente y descarga el PNG. WhatsApp Web no admite adjuntos desde
 *     un enlace; se pega con Ctrl+V en la conversación.
 * - Descargar la imagen cuando el botón lo pide.
 *
 * El servidor no genera imágenes ni PDF. Ninguna regla de negocio vive aquí.
 */

(function () {
  "use strict";

  var COLOR_FACTURA = "#ffffff";
  var COLOR_RECIBO = "#0f172a";
  var imagenesPromesas = {};
  var imagenesListas = {};

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
   * Espera un tiempo antes de seguir, para que el navegador termine de pintar.
   *
   * @param {number} milisegundos Pausa en milisegundos.
   * @returns {Promise<void>} Se resuelve al cumplirse la pausa.
   */
  function esperar(milisegundos) {
    return new Promise(function (resolver) {
      window.setTimeout(resolver, milisegundos);
    });
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
   * Guarda el estado del logo visible y devuelve una función que lo restaura.
   *
   * SRS v3.1, punto 2: durante la captura se trabaja solo sobre un clon fuera de
   * pantalla. Esta guardia evita que, si una librería muta el nodo original, el
   * modal pierda el logo al compartir. Nunca se oculta al usuario.
   *
   * @returns {Function} Restaurador del logo visible.
   */
  function protegerLogoVisible() {
    var logo = document.querySelector(".logo-ob-imagen");
    if (!logo) {
      return function () {};
    }
    var estado = {
      src: logo.getAttribute("src"),
      display: logo.style.display,
      visibility: logo.style.visibility,
      opacity: logo.style.opacity
    };
    return function () {
      if (estado.src !== null) {
        logo.setAttribute("src", estado.src);
      }
      logo.style.display = estado.display;
      logo.style.visibility = estado.visibility;
      logo.style.opacity = estado.opacity;
    };
  }

  /**
   * Muestra un aviso discreto y temporal en la esquina inferior.
   *
   * @param {string} texto Mensaje a mostrar.
   */
  function mostrarAviso(texto) {
    var aviso = document.createElement("div");
    aviso.className = "aviso-toast";
    aviso.setAttribute("role", "status");
    aviso.textContent = texto;
    document.body.appendChild(aviso);
    window.setTimeout(function () {
      if (aviso.parentNode) {
        aviso.parentNode.removeChild(aviso);
      }
    }, 5000);
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
          "position:fixed;left:-10000px;top:0;width:850px;background:#ffffff;" +
          "container-type:inline-size;";
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
      // Safari dibuja las imágenes de la hoja solo tras un instante: sin esta pausa
      // los logos se capturaban vacíos desde la lista de órdenes.
      var opciones = { pixelRatio: 2, backgroundColor: fondo, cacheBust: false };
      // Safari no dibuja las imágenes en la primera conversión: la primera pasada las
      // carga y la segunda es la que se entrega.
      return esperar(300)
        .then(function () {
          return libreria.toBlob(nodo, opciones);
        })
        .then(function () {
          return esperar(200);
        })
        .then(function () {
          return libreria.toBlob(nodo, opciones);
        })
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
    if (!imagenesPromesas[url]) {
      imagenesPromesas[url] = crearPng(url)
        .then(function (blob) {
          imagenesListas[url] = blob;
          return blob;
        })
        .catch(function (error) {
          delete imagenesPromesas[url];
          throw error;
        });
    }
    return imagenesPromesas[url];
  }

  /**
   * Copia la imagen al portapapeles. Acepta la promesa de la imagen para llamarla
   * dentro del clic, cuando la ventana todavía tiene el foco.
   *
   * @param {Promise<Blob>} promesaBlob Imagen PNG en preparación.
   * @returns {Promise<boolean>} `true` si el navegador la copió.
   */
  function copiarImagen(promesaBlob) {
    if (!navigator.clipboard || typeof window.ClipboardItem === "undefined") {
      return Promise.resolve(false);
    }
    try {
      return navigator.clipboard
        .write([new window.ClipboardItem({ "image/png": promesaBlob })])
        .then(
          function () {
            return true;
          },
          function () {
            return false;
          }
        );
    } catch (error) {
      return Promise.resolve(false);
    }
  }

  /**
   * Obtiene el mensaje prellenado de un enlace de WhatsApp.
   *
   * @param {string} enlace URL `wa.me` o `api.whatsapp.com`.
   * @returns {string} Texto del mensaje, o cadena vacía.
   */
  function mensajeDelEnlace(enlace) {
    try {
      return new URL(enlace).searchParams.get("text") || "";
    } catch (error) {
      return "";
    }
  }

  /**
   * Extrae el destinatario de un enlace `wa.me` y lo normaliza a Colombia.
   *
   * Se limpian espacios, guiones, paréntesis y el signo `+`. Con 10 dígitos se
   * antepone el indicativo 57; con 12 dígitos que ya empiezan por 57 se conserva.
   * Cualquier otro formato se rechaza para no abrir un chat equivocado.
   *
   * @param {string} enlace URL `wa.me` construida con el celular de la orden.
   * @returns {string} Número listo para `wa.me`, o cadena vacía si no es válido.
   */
  function numeroDelEnlace(enlace) {
    try {
      var partes = new URL(enlace).pathname.split("/").filter(Boolean);
      var destino = partes.length ? partes[partes.length - 1] : "";
      var limpio = destino.replace(/[\s\-()\+]/g, "");
      if (/^\d{10}$/.test(limpio)) {
        return "57" + limpio;
      }
      if (/^57\d{10}$/.test(limpio)) {
        return limpio;
      }
      return "";
    } catch (error) {
      return "";
    }
  }

  /**
   * Envía la factura o el recibo por WhatsApp.
   *
   * SRS v3.0, punto 2: nunca se usa la Web Share API aquí. Los tres puntos
   * (botón de Ver factura, ícono rápido y recibos de abono) comparten esta
   * función y abren siempre el chat del cliente con el destinatario en la URL,
   * sin pasar por el selector de aplicaciones del sistema.
   *
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function enviarPorWhatsapp(boton) {
    var url = boton.getAttribute("data-fragmento");
    var nombre = boton.getAttribute("data-nombre") || "imagen.png";
    var whatsapp = boton.getAttribute("data-whatsapp") || "";
    var texto = boton.getAttribute("data-texto") || mensajeDelEnlace(whatsapp);
    var etiqueta = boton.textContent;
    // SRS v2.0, sección 1: el destinatario se toma del celular registrado en la
    // factura activa (ya presente en `data-whatsapp`) y se sanea aquí, en el
    // único punto que abre el chat. El mensaje no se toca: se reutiliza el mismo
    // texto y solo se vuelve a codificar al construir la URL dirigida.
    var numero = numeroDelEnlace(whatsapp);

    if (!numero) {
      window.alert("El cliente no tiene un número de celular registrado. Agrégalo en su ficha para abrir el chat.");
      return;
    }

    var enlaceDirecto = "https://wa.me/" + numero + "?text=" + encodeURIComponent(texto);

    boton.disabled = true;
    boton.textContent = "Preparando…";
    // Guardia del logo del modal: la captura usa un clon fuera de pantalla y
    // aquí se garantiza que el nodo visible quede exactamente como estaba.
    var restaurarLogo = protegerLogoVisible();
    var promesaImagen = imagenDe(url);
    var copiada = copiarImagen(promesaImagen);
    // Apertura directa del chat. Si el navegador bloquea la ventana nueva, se
    // navega en la misma pestaña para no caer en el selector de aplicaciones.
    var ventana = window.open(enlaceDirecto, "_blank");
    if (!ventana) {
      window.location.href = enlaceDirecto;
    }

    Promise.all([promesaImagen, copiada])
      .then(function (resultado) {
        descargar(resultado[0], nombre);
        mostrarAviso(
          resultado[1]
            ? "Chat abierto y comprobante copiado: si deseas adjuntar la imagen, solo pulsa Pegar en el chat de WhatsApp"
            : "Chat abierto y comprobante descargado: adjúntalo con el clip antes de enviar."
        );
      })
      .catch(function (error) {
        mostrarAviso((error && error.message) || "No se pudo preparar la imagen.");
      })
      .then(function () {
        restaurarLogo();
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

    var restaurarLogo = protegerLogoVisible();
    imagenDe(url)
      .then(function (blob) {
        descargar(blob, nombre);
      })
      .catch(function (error) {
        window.alert((error && error.message) || "No se pudo preparar la imagen.");
      })
      .then(function () {
        restaurarLogo();
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
