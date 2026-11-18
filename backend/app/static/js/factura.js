/**
 * Acciones de la factura de OLB_BYTE: vista previa, compartir y envío por WhatsApp.
 *
 * Responsabilidad
 * ---------------
 * - Abrir la vista previa del PDF en un diálogo nativo y cerrarla.
 * - Compartir el PDF con la Web Share API cuando el navegador puede enviar archivos.
 * - Si no puede compartir archivos, abrir el enlace de WhatsApp con el resumen.
 *
 * El PDF lo genera el servidor (Chromium headless). Este script no calcula nada.
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
    // Sin <dialog> no hay vista previa dentro de la página; la descarga sigue disponible.
    botonVista.hidden = true;
  }

  var botonCompartir = document.querySelector("[data-compartir]");
  if (!botonCompartir) {
    return;
  }

  /**
   * Intenta compartir el PDF como archivo; si no es posible abre WhatsApp.
   *
   * @param {Event} evento Clic en el botón de compartir.
   */
  function compartir(evento) {
    evento.preventDefault();
    var url = botonCompartir.getAttribute("data-pdf");
    var nombre = botonCompartir.getAttribute("data-nombre");
    var whatsapp = botonCompartir.getAttribute("data-whatsapp");

    if (!navigator.share || !navigator.canShare || typeof File !== "function") {
      window.open(whatsapp, "_blank", "noopener");
      return;
    }

    fetch(url, { credentials: "same-origin" })
      .then(function (respuesta) {
        return respuesta.blob();
      })
      .then(function (blob) {
        var archivo = new File([blob], nombre, { type: "application/pdf" });
        if (!navigator.canShare({ files: [archivo] })) {
          window.open(whatsapp, "_blank", "noopener");
          return null;
        }
        return navigator.share({ files: [archivo], title: nombre, text: "Factura OLB_BYTE" });
      })
      .catch(function (error) {
        // El usuario cerró la hoja de compartir: no se abre WhatsApp por su cuenta.
        if (error && error.name === "AbortError") {
          return;
        }
        window.open(whatsapp, "_blank", "noopener");
      });
  }

  botonCompartir.addEventListener("click", compartir);
})();
