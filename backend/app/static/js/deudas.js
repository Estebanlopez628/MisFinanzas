/**
 * Interacción de filas con modal centrado (SRS v1.9, secciones 2.3 y 3.3).
 *
 * Responsabilidad
 * ---------------
 * - En escritorio los botones lápiz y × viven al final de cada fila; el lápiz
 *   abre el `<details class="edicion-gasto--modal">` que ya existe en el resto
 *   de módulos.
 * - En móvil esos iconos se ocultan con CSS y un toque sobre la fila abre el
 *   mismo modal: en «Deudas registradas», «Deducciones fijas» y «Atajos
 *   guardados».
 *   Solo se abre uno a la vez para no apilar fondos.
 *
 * El cierre con «Cancelar», Escape o tocando el fondo lo hace `app.js`.
 */
(function () {
  "use strict";

  function esMovil() {
    return window.matchMedia && window.matchMedia("(max-width: 640px)").matches;
  }

  function cerrarOtras(actual) {
    document.querySelectorAll("details.edicion-gasto--modal[open]").forEach(function (detalles) {
      if (detalles !== actual) {
        detalles.open = false;
      }
    });
  }

  function conectarFilas(selectorFila, selectorModal) {
    document.querySelectorAll(selectorFila).forEach(function (fila) {
      fila.addEventListener("click", function (evento) {
        if (!esMovil()) {
          return;
        }
        // Los controles del modal y los formularios laterales gestionan sus
        // propios clics: no queremos reabrir ni cerrar al interactuar.
        if (evento.target.closest("form, button, input, select, textarea, label, a")) {
          return;
        }
        var detalles = fila.querySelector(selectorModal);
        if (!detalles) {
          return;
        }
        cerrarOtras(detalles);
        detalles.open = !detalles.open;
      });
    });
  }

  conectarFilas("tr[data-deuda-fila]", "details.edicion-gasto--modal");
  conectarFilas("li[data-deduccion-fila]", "details.edicion-gasto--modal");
  conectarFilas("tr[data-chancuco-fila]", "details.atajo-modal");
  conectarFilas("li[data-atajo-fila]", "details.atajo-finanzas-modal");
})();
