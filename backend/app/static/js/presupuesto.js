/**
 * Mejora progresiva de "Gastos y Presupuesto" (SRS v1.3, bloque 3).
 *
 * Responsabilidad
 * ---------------
 * - Habilitar el campo de meses solo cuando la duración es limitada.
 * - Mostrar el total acumulado proyectado mientras el usuario escribe la cuota
 *   y el número de meses, sin enviar nada al servidor.
 *
 * Sin JavaScript el formulario sigue funcionando: el servidor valida la
 * duración y rechaza los casos incoherentes con un mensaje en español.
 */

(function () {
  "use strict";

  var formulario = document.querySelector('form[action*="presupuesto/metas"]');
  if (!formulario) {
    return;
  }

  var selectorDuracion = formulario.querySelector("[data-duracion]");
  var campoMeses = formulario.querySelector("[data-meses]");
  var campoValor = formulario.querySelector('input[name="valor_mensual"]');
  var avisoTotal = formulario.querySelector("[data-total-proyectado]");

  /**
   * Convierte un monto escrito por el usuario en número.
   *
   * Acepta las dos convenciones habituales: «1.234.567» y «1.234,50».
   *
   * @param {string} texto Valor tal como está en el campo.
   * @returns {number} Monto numérico; `NaN` si no se puede interpretar.
   */
  function aNumero(texto) {
    if (!texto) {
      return NaN;
    }
    var limpio = String(texto).replace(/[^\d.,-]/g, "");
    // Si hay coma, se asume formato colombiano: los puntos son de miles.
    if (limpio.indexOf(",") !== -1) {
      limpio = limpio.replace(/\./g, "").replace(",", ".");
    } else {
      limpio = limpio.replace(/\./g, "");
    }
    return parseFloat(limpio);
  }

  /**
   * Formatea un número como pesos con separador de miles.
   *
   * @param {number} valor Monto a mostrar.
   * @returns {string} Texto tipo «$1.200.000».
   */
  function formatear(valor) {
    if (!isFinite(valor)) {
      return "—";
    }
    return "$" + Math.round(valor).toLocaleString("es-CO");
  }

  /**
   * Recalcula el aviso del total proyectado.
   */
  function actualizarTotal() {
    if (!avisoTotal) {
      return;
    }

    var esLimitado = selectorDuracion && selectorDuracion.value === "LIMITADO";
    var valor = aNumero(campoValor ? campoValor.value : "");
    var meses = campoMeses ? parseInt(campoMeses.value, 10) : NaN;

    if (!esLimitado) {
      avisoTotal.textContent =
        "Gasto fijo mensual: sin fecha de cierre, la comparación usa 12 meses.";
      return;
    }

    if (!isFinite(valor) || valor <= 0 || !isFinite(meses) || meses <= 0) {
      avisoTotal.textContent =
        "Total acumulado proyectado: escribe la cuota y los meses para verlo.";
      return;
    }

    avisoTotal.textContent =
      "Total acumulado proyectado: " +
      formatear(valor) +
      " × " +
      meses +
      " meses = " +
      formatear(valor * meses) +
      ".";
  }

  /**
   * Habilita o deshabilita el campo de meses según la duración elegida.
   */
  function sincronizarDuracion() {
    if (!selectorDuracion || !campoMeses) {
      return;
    }
    var esLimitado = selectorDuracion.value === "LIMITADO";
    campoMeses.disabled = !esLimitado;
    if (!esLimitado) {
      campoMeses.value = "";
    }
    actualizarTotal();
  }

  if (selectorDuracion) {
    selectorDuracion.addEventListener("change", sincronizarDuracion);
  }
  if (campoMeses) {
    campoMeses.addEventListener("input", actualizarTotal);
  }
  if (campoValor) {
    campoValor.addEventListener("input", actualizarTotal);
  }

  sincronizarDuracion();
})();
