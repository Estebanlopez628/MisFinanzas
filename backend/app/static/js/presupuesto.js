/**
 * Mejora progresiva de "Gastos y Presupuesto" (SRS v1.3, bloque 3).
 *
 * Responsabilidad
 * ---------------
 * - Mostrar el total acumulado proyectado mientras el usuario escribe la cuota
 *   y el periodo (en meses o años), sin enviar nada al servidor.
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
  var selectorUnidad = formulario.querySelector("[data-unidad]");
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

    var valor = aNumero(campoValor ? campoValor.value : "");
    var cantidad = campoMeses ? parseInt(campoMeses.value, 10) : NaN;
    // SRS v1.6: el periodo puede escribirse en meses o en años.
    var porAnios = selectorUnidad && selectorUnidad.value === "ANIOS";
    var meses = porAnios ? cantidad * 12 : cantidad;

    if (!isFinite(valor) || valor <= 0 || !isFinite(meses) || meses <= 0) {
      avisoTotal.textContent =
        "Total acumulado proyectado: escribe la cuota y el periodo para verlo.";
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

  if (selectorDuracion) {
    selectorDuracion.addEventListener("change", actualizarTotal);
  }
  if (selectorUnidad) {
    selectorUnidad.addEventListener("change", actualizarTotal);
  }
  if (campoMeses) {
    campoMeses.addEventListener("input", actualizarTotal);
  }
  if (campoValor) {
    campoValor.addEventListener("input", actualizarTotal);
  }

  sincronizarDuracion();
})();
