/**
 * Mejoras progresivas globales.
 *
 * Responsabilidad
 * ---------------
 * - Copiar referencias al portapapeles (Chancucos) con confirmación visual.
 * - Añadir filas a la venta multipartida de OLB_BYTE sin JavaScript de cálculo.
 * - Registrar el service worker para que la PWA sea instalable y funcione sin red
 *   en las pantallas ya visitadas.
 *
 * Ninguna regla de negocio vive aquí: solo se manipula el DOM.
 */

(function () {
  "use strict";

  /**
   * Copia un texto al portapapeles y avisa al usuario.
   *
   * @param {string} texto Contenido a copiar.
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function copiar(texto, boton) {
    var confirmar = function () {
      var original = boton.textContent;
      boton.textContent = "Copiado";
      window.setTimeout(function () {
        boton.textContent = original;
      }, 1500);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(confirmar).catch(function () {
        seleccionarManual(texto);
      });
      return;
    }
    seleccionarManual(texto);
  }

  /**
   * Respaldo para navegadores sin API de portapapeles.
   *
   * @param {string} texto Contenido a copiar.
   */
  function seleccionarManual(texto) {
    var area = document.createElement("textarea");
    area.value = texto;
    area.setAttribute("readonly", "readonly");
    area.style.position = "absolute";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
    } catch (error) {
      // Sin soporte: el usuario puede copiar el número manualmente.
    }
    document.body.removeChild(area);
  }

  var botonesCopiar = document.querySelectorAll("[data-copiar]");
  for (var i = 0; i < botonesCopiar.length; i += 1) {
    botonesCopiar[i].addEventListener("click", function (evento) {
      copiar(evento.currentTarget.getAttribute("data-copiar"), evento.currentTarget);
    });
  }

  // ------------------- Filas dinámicas de la venta -------------------------

  var botonAgregar = document.querySelector("[data-agregar-linea]");
  var cuerpoLineas = document.querySelector("[data-lineas]");
  if (botonAgregar && cuerpoLineas) {
    botonAgregar.addEventListener("click", function () {
      var primera = cuerpoLineas.querySelector("tr");
      if (!primera) {
        return;
      }
      var nueva = primera.cloneNode(true);
      var campos = nueva.querySelectorAll("input, select");
      for (var j = 0; j < campos.length; j += 1) {
        if (campos[j].tagName === "INPUT") {
          campos[j].value = campos[j].name === "cantidad" ? "1" : "";
        } else {
          campos[j].selectedIndex = 0;
        }
      }
      cuerpoLineas.appendChild(nueva);
    });
  }

  // ------------------------- Service worker (PWA) -------------------------

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {
        // La aplicación sigue funcionando aunque el navegador no permita el SW.
      });
    });
  }
})();
