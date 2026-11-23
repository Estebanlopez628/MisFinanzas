/**
 * Tooltip táctil de la gráfica «Comparativa de cierre de deuda» (SRS v3.7).
 *
 * El cálculo y las cifras los genera Python; aquí solo se muestra el detalle
 * del mes que el usuario toca o sobre el que pasa el cursor.
 */
(function () {
  "use strict";

  var bloque = document.querySelector("[data-cierre-consejero]");
  if (!bloque) {
    return;
  }
  var tooltip = bloque.querySelector("[data-cierre-tooltip]");
  var detalle = bloque.querySelector("[data-cierre-detalle]");

  /**
   * Muestra el salto del mes seleccionado.
   *
   * @param {HTMLButtonElement} boton Botón del mes.
   */
  function mostrar(boton) {
    var texto =
      boton.getAttribute("data-mes") +
      " · Saldo Base: " + boton.getAttribute("data-base") +
      " · Saldo Optimizado: " + boton.getAttribute("data-optimo") +
      " · Reducción extra acumulada: " + boton.getAttribute("data-reduccion");
    if (detalle) {
      detalle.textContent = texto;
    }
    if (tooltip) {
      tooltip.textContent = texto;
      tooltip.hidden = false;
    }
  }

  bloque.querySelectorAll(".cierre-deuda__mes").forEach(function (boton) {
    boton.addEventListener("click", function () {
      mostrar(boton);
    });
    boton.addEventListener("mouseenter", function () {
      mostrar(boton);
    });
  });
})();
