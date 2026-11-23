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

  // SRS v4.17: marcas de graduación del dial. Solo dibuja una vez por SVG.
  bloque.querySelectorAll(".mf-cockpit-dial").forEach(function (svg) {
    var grupo = svg.querySelector(".mf-dial-ticks");
    if (!grupo || grupo.childElementCount > 0) {
      return;
    }
    var cx = 120;
    var cy = 112;
    var rInner = 97;
    var total = 41;
    for (var i = 0; i < total; i++) {
      var radio = i / (total - 1);
      var angulo = -205 + radio * 230;
      var rad = (angulo * Math.PI) / 180;
      var principal = i % 5 === 0;
      var rOuter = rInner + (principal ? 7 : 4);
      var linea = document.createElementNS("http://www.w3.org/2000/svg", "line");
      linea.setAttribute("x1", (cx + rInner * Math.cos(rad)).toFixed(1));
      linea.setAttribute("y1", (cy + rInner * Math.sin(rad)).toFixed(1));
      linea.setAttribute("x2", (cx + rOuter * Math.cos(rad)).toFixed(1));
      linea.setAttribute("y2", (cy + rOuter * Math.sin(rad)).toFixed(1));
      linea.setAttribute("stroke", principal ? "rgba(226, 232, 240, 0.45)" : "rgba(148, 163, 184, 0.22)");
      linea.setAttribute("stroke-width", principal ? "1.3" : "0.8");
      grupo.appendChild(linea);
    }
  });
})();
