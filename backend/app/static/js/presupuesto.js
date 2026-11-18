/**
 * Mejora progresiva de "Gastos y Presupuesto" (SRS v1.3, bloque 3).
 *
 * Responsabilidad
 * ---------------
 * - Mostrar el total acumulado proyectado mientras el usuario escribe la cuota
 *   y el periodo (en meses o años), sin enviar nada al servidor.
 * - SRS v1.7: revelar el modo de «Ambas quincenas» y explicar el total mensual
 *   cuando la cuota se divide o se duplica entre los dos pagos.
 *
 * Sin JavaScript el formulario sigue funcionando: el servidor valida la
 * duración y el modo, y rechaza los casos incoherentes con un mensaje en
 * español.
 */

(function () {
  "use strict";

  var formulario = document.querySelector('form[action*="presupuesto/metas"]');
  if (!formulario) {
    return;
  }

  var campoMeses = formulario.querySelector("[data-meses]");
  var selectorUnidad = formulario.querySelector("[data-unidad]");
  var selectorQuincena = formulario.querySelector('select[name="quincena"]');
  var bloqueModo = formulario.querySelector("[data-modo-ambas]");
  var selectorModo = formulario.querySelector("[data-modo]");
  var campoValor = formulario.querySelector('input[name="valor_mensual"]');
  var avisoTotal = formulario.querySelector("[data-total-proyectado]");

  var QUINCENA_AMBAS = "3";
  var MODO_DUPLICAR = "DUPLICAR";

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
   * Indica si la meta se descuenta en las dos quincenas.
   *
   * @returns {boolean} `true` cuando el selector vale 3.
   */
  function usaAmbasQuincenas() {
    return Boolean(selectorQuincena) && selectorQuincena.value === QUINCENA_AMBAS;
  }

  /**
   * Indica si el monto se cobra completo en cada quincena.
   *
   * @returns {boolean} `true` con el modo DUPLICAR.
   */
  function duplicaElMonto() {
    return Boolean(selectorModo) && selectorModo.value === MODO_DUPLICAR;
  }

  /**
   * Muestra u oculta el selector de modo según la quincena elegida.
   */
  function sincronizarModo() {
    if (!bloqueModo) {
      return;
    }
    var visible = usaAmbasQuincenas();
    bloqueModo.hidden = !visible;
    if (!visible && selectorModo) {
      // Sin «Ambas quincenas» el servidor guarda DIVIDIR: el formulario se
      // alinea con esa regla para que un valor viejo no se envíe por error.
      selectorModo.value = "DIVIDIR";
    }
  }

  /**
   * Recalcula el aviso del total proyectado y el total mensual efectivo.
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

    var pagoMensual = valor;
    var detallePago = "";

    if (usaAmbasQuincenas()) {
      if (duplicaElMonto()) {
        pagoMensual = valor * 2;
        detallePago = " (" + formatear(valor) + " en cada quincena)";
      } else {
        detallePago = " (" + formatear(valor / 2) + " por quincena)";
      }
    }

    avisoTotal.textContent =
      "Total acumulado proyectado: " +
      formatear(pagoMensual) +
      " al mes" +
      detallePago +
      " × " +
      meses +
      " meses = " +
      formatear(pagoMensual * meses) +
      ".";
  }

  if (selectorQuincena) {
    selectorQuincena.addEventListener("change", function () {
      sincronizarModo();
      actualizarTotal();
    });
  }
  if (selectorModo) {
    selectorModo.addEventListener("change", actualizarTotal);
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

  sincronizarModo();
  actualizarTotal();
})();
