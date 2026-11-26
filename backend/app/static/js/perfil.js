/**
 * Mejora progresiva del perfil financiero (SRS v1.2).
 *
 * Responsabilidad
 * ---------------
 * - Mostrar el bloque de quincenas solo en modalidad QUINCENAL.
 * - Alternar entre el caso A (porcentajes conocidos) y el caso B (neto de la
 *   quincena sin deducciones).
 * - Autocompletar la quincena 2 como complemento a 100 % mientras el usuario no
 *   la edite manualmente.
 *
 * La validación definitiva y el cálculo del caso B siempre ocurren en Python.
 */

(function () {
  "use strict";

  var modalidad = document.querySelector("[data-modalidad]");
  var grupo = document.querySelector("[data-grupo-quincenal]");
  if (!modalidad || !grupo) {
    return;
  }

  var avisoMensual = document.querySelector("[data-aviso-mensual]");

  var casoPorcentajes = document.querySelector("[data-caso-porcentajes]");
  var casoNeto = document.querySelector("[data-caso-neto]");
  var radios = document.querySelectorAll("[data-conoce-porcentajes]");
  var porcentaje1 = document.querySelector("[data-porcentaje-1]");
  var porcentaje2 = document.querySelector("[data-porcentaje-2]");
  var segundoEditado = false;

  /**
   * Habilita o deshabilita todos los controles de un subgrupo.
   *
   * @param {HTMLElement|null} contenedor Subgrupo a alternar.
   * @param {boolean} activo Si debe mostrarse y enviarse.
   */
  function alternarSubgrupo(contenedor, activo) {
    if (!contenedor) {
      return;
    }
    contenedor.hidden = !activo;
    contenedor.querySelectorAll("input, select").forEach(function (control) {
      control.disabled = !activo;
    });
  }

  /**
   * Indica si el usuario conoce los porcentajes de sus quincenas.
   *
   * @returns {boolean} `true` para el caso A, `false` para el caso B.
   */
  function conocePorcentajes() {
    var seleccionado = document.querySelector("[data-conoce-porcentajes]:checked");
    return !seleccionado || seleccionado.value === "SI";
  }

  /** Ajusta visibilidad y campos enviables según modalidad y caso elegido. */
  function actualizar() {
    var esQuincenal = modalidad.value === "QUINCENAL";
    grupo.hidden = !esQuincenal;
    grupo.disabled = !esQuincenal;
    // En modalidad mensual se explica por qué no hay quincenas que configurar.
    if (avisoMensual) {
      avisoMensual.hidden = esQuincenal;
    }

    if (!esQuincenal) {
      return;
    }

    var sabe = conocePorcentajes();
    alternarSubgrupo(casoPorcentajes, sabe);
    alternarSubgrupo(casoNeto, !sabe);
  }

  /**
   * Lee un porcentaje escrito con «%» y coma decimal.
   *
   * @param {string} texto Valor del campo, por ejemplo «60 %» o «60,5».
   * @returns {number} Porcentaje numérico; `NaN` si no se puede interpretar.
   */
  function leerPorcentaje(texto) {
    var limpio = String(texto || "").replace(/%/g, "").replace(/\s/g, "").replace(",", ".");
    var valor = parseFloat(limpio);
    return isFinite(valor) ? valor : NaN;
  }

  /**
   * Escribe un porcentaje con «%» y sin ceros de relleno.
   *
   * @param {number} valor Porcentaje a mostrar.
   * @returns {string} Texto como «40 %» o «37,5 %».
   */
  function escribirPorcentaje(valor) {
    var redondeado = Math.round(valor * 100) / 100;
    var texto = String(redondeado).replace(".", ",");
    return texto + " %";
  }

  if (porcentaje1 && porcentaje2) {
    porcentaje1.addEventListener("input", function () {
      if (segundoEditado) {
        return;
      }
      var valor = leerPorcentaje(porcentaje1.value);
      if (!isNaN(valor) && valor > 0 && valor < 100) {
        porcentaje2.value = escribirPorcentaje(100 - valor);
      }
    });
    porcentaje2.addEventListener("input", function () {
      segundoEditado = true;
    });
  }

  // SRS v1.9: los rótulos «Quincena N (día X)» siguen al día que se escribe,
  // sin esperar a guardar. Si el campo queda vacío se muestra el día predeterminado.
  var predeterminados = { "1": "15", "2": "30" };
  document.querySelectorAll("[data-dia-quincena]").forEach(function (campo) {
    var numero = campo.getAttribute("data-dia-quincena");
    campo.addEventListener("input", function () {
      var dia = campo.value.trim() || predeterminados[numero];
      document
        .querySelectorAll("option[data-etiqueta-quincena='" + numero + "']")
        .forEach(function (opcion) {
          opcion.textContent = "• Quincena " + numero + " (día " + dia + ")";
        });
    });
  });

  radios.forEach(function (radio) {
    radio.addEventListener("change", actualizar);
  });
  modalidad.addEventListener("change", actualizar);
  actualizar();
})();
