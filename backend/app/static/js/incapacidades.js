/**
 * Cálculo automático del módulo de incapacidades (SRS v1.5).
 *
 * Responsabilidad
 * ---------------
 * - Recalcular la liquidación en cuanto cambian las fechas, el sueldo o el mes,
 *   sin botón «Calcular».
 * - Reemplazar solo la zona de resultado y el bloque de errores: el resto de la
 *   página no se recarga.
 * - Dejar intacto el botón «Guardar incapacidad», que sigue siendo un POST
 *   clásico y funciona aunque JavaScript esté desactivado.
 *
 * La aritmética y el HTML los produce el servidor; este archivo solo transporta
 * el formulario y sustituye el fragmento devuelto.
 */

(function () {
  "use strict";

  // Suficiente para no lanzar una petición por cada tecla del sueldo.
  var RETARDO_MS = 350;

  var formulario = document.querySelector("[data-incapacidad-auto]");
  if (!formulario) {
    return;
  }

  var zonaResultado = document.querySelector("#zona-resultado-incapacidades");
  var zonaErrores = document.querySelector("#errores-incapacidad");
  var temporizador = null;
  var peticionEnCurso = 0;

  /**
   * Indica si las dos fechas ya están completas.
   *
   * @returns {boolean} `true` cuando se puede pedir la liquidación.
   */
  function fechasListas() {
    var inicio = formulario.querySelector('input[name="fecha_inicio"]');
    var fin = formulario.querySelector('input[name="fecha_fin"]');
    return Boolean(inicio && fin && inicio.value && fin.value);
  }

  /**
   * Sustituye un fragmento del documento por el que devolvió el servidor.
   *
   * @param {Document} documento Página completa recibida.
   * @param {string} selector Identificador del fragmento.
   * @param {HTMLElement|null} destino Elemento actual en pantalla.
   */
  function reemplazar(documento, selector, destino) {
    if (!destino) {
      return;
    }
    var nuevo = documento.querySelector(selector);
    if (nuevo) {
      destino.innerHTML = nuevo.innerHTML;
    }
  }

  /**
   * Pide la liquidación y actualiza la zona de resultado.
   */
  function actualizar() {
    if (!fechasListas()) {
      return;
    }

    peticionEnCurso += 1;
    var turno = peticionEnCurso;

    fetch(formulario.action, {
      method: "POST",
      body: new FormData(formulario),
      credentials: "same-origin"
    })
      .then(function (respuesta) {
        return respuesta.text();
      })
      .then(function (texto) {
        // Si llegó una respuesta más nueva, esta ya no interesa.
        if (turno !== peticionEnCurso) {
          return;
        }
        var documento = new DOMParser().parseFromString(texto, "text/html");
        reemplazar(documento, "#zona-resultado-incapacidades", zonaResultado);
        reemplazar(documento, "#errores-incapacidad", zonaErrores);
      })
      .catch(function () {
        // Sin conexión se conserva el último resultado visible.
      });
  }

  /**
   * Agrupa los cambios seguidos en una sola petición.
   */
  function programar() {
    if (temporizador) {
      window.clearTimeout(temporizador);
    }
    temporizador = window.setTimeout(actualizar, RETARDO_MS);
  }

  formulario.addEventListener("input", programar);
  formulario.addEventListener("change", programar);

  // SRS v1.6: Enter solo recalcula; el guardado queda en su botón.
  formulario.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter") {
      evento.preventDefault();
      actualizar();
    }
  });

  formulario.addEventListener("submit", function (evento) {
    // El botón de guardar lleva `formaction`: debe navegar y persistir.
    if (evento.submitter && evento.submitter.hasAttribute("formaction")) {
      return;
    }
    evento.preventDefault();
    actualizar();
  });

  // Si la página llega con fechas (error corregido o vuelta atrás), se liquida.
  if (fechasListas()) {
    actualizar();
  }
})();
