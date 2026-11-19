/**
 * Acciones de la factura de OLB_BYTE: vista previa y envío por WhatsApp con el PDF.
 *
 * Responsabilidad
 * ---------------
 * - Abrir la vista previa del PDF en un diálogo nativo y cerrarla.
 * - Enviar la factura: se descarga el PDF desde el servidor y se comparte como
 *   archivo con la hoja de compartir del navegador (Android, iPhone), con el mensaje
 *   «Hola {cliente}, adjunto tu factura de compra.».
 * - Si el navegador no puede compartir archivos (por ejemplo, en un PC), se descarga
 *   el PDF y se abre WhatsApp con el mensaje; el PDF se adjunta desde la descarga.
 *
 * WhatsApp no permite que una página web adjunte un archivo a un chat sin la hoja de
 * compartir, por eso el respaldo descarga el archivo y lo indica al usuario.
 * El PDF lo genera el servidor. Este script no calcula nada.
 */

(function () {
  "use strict";

  var dialogo = document.querySelector("[data-dialogo-pdf]");
  var botonVista = document.querySelector("[data-vista-pdf]");
  var marco = document.querySelector("[data-marco-pdf]");

  if (dialogo && botonVista && marco && typeof dialogo.showModal === "function") {
    botonVista.addEventListener("click", function () {
      marco.setAttribute("src", marco.getAttribute("data-src"));
      dialogo.showModal();
    });

    var botonCerrar = dialogo.querySelector("[data-cerrar-pdf]");
    if (botonCerrar) {
      botonCerrar.addEventListener("click", function () {
        dialogo.close();
      });
    }

    dialogo.addEventListener("close", function () {
      marco.removeAttribute("src");
    });
  } else if (botonVista) {
    botonVista.hidden = true;
  }

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
   * Copia una imagen PNG al portapapeles para pegarla en WhatsApp Web (Ctrl+V).
   *
   * @param {Blob} blob Imagen del recibo.
   * @returns {Promise<boolean>} `true` si el navegador la copió.
   */
  function copiarImagen(blob) {
    if (!navigator.clipboard || typeof window.ClipboardItem === "undefined" || blob.type !== "image/png") {
      return Promise.resolve(false);
    }
    return navigator.clipboard
      .write([new window.ClipboardItem({ "image/png": blob })])
      .then(function () {
        return true;
      })
      .catch(function () {
        return false;
      });
  }

  /**
   * Envía la factura por WhatsApp con el PDF como archivo cuando es posible.
   *
   * @param {Event} evento Clic en el botón de envío.
   */
  function enviarFactura(evento) {
    var boton = evento.currentTarget;
    var url = boton.getAttribute("data-pdf");
    var nombre = boton.getAttribute("data-nombre");
    var texto = boton.getAttribute("data-texto");
    var whatsapp = boton.getAttribute("data-whatsapp");

    // La ventana se abre dentro del clic para que el navegador no la bloquee; el
    // respaldo la dirige a WhatsApp cuando el PDF ya está listo.
    var ventana = window.open("", "_blank");
    var etiqueta = boton.textContent;
    boton.disabled = true;
    boton.textContent = "Preparando…";

    fetch(url, { credentials: "same-origin" })
      .then(function (respuesta) {
        if (!respuesta.ok) {
          throw new Error("No se pudo generar el archivo.");
        }
        return respuesta.blob();
      })
      .then(function (blob) {
        var archivo = new File([blob], nombre, { type: blob.type || "application/octet-stream" });
        if (navigator.share && navigator.canShare && navigator.canShare({ files: [archivo] })) {
          if (ventana) {
            ventana.close();
          }
          return navigator.share({ files: [archivo], text: texto, title: nombre });
        }
        descargar(blob, nombre);
        return copiarImagen(blob).then(function (copiada) {
          if (ventana) {
            ventana.location.href = whatsapp;
          }
          window.alert(
            copiada
              ? "La imagen se copió y se descargó. En WhatsApp, pégala con Ctrl+V."
              : "El archivo se descargó. En WhatsApp, toca el clip y adjúntalo antes de enviar."
          );
          return null;
        });
      })
      .catch(function (error) {
        if (ventana) {
          ventana.close();
        }
        if (error && error.name === "AbortError") {
          // El usuario cerró la hoja de compartir: no se muestra nada.
          return;
        }
        window.alert(
          (error && error.message) ||
            "No se pudo preparar el archivo. Revisa la instalación de Chromium (DESPLIEGUE.md, sección 13)."
        );
      })
      .then(function () {
        boton.disabled = false;
        boton.textContent = etiqueta;
      });
  }

  var botonesEnvio = document.querySelectorAll("[data-compartir], [data-compartir-factura]");
  for (var i = 0; i < botonesEnvio.length; i += 1) {
    botonesEnvio[i].addEventListener("click", enviarFactura);
  }
})();
