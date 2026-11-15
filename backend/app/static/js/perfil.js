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

  if (porcentaje1 && porcentaje2) {
    porcentaje1.addEventListener("input", function () {
      if (segundoEditado) {
        return;
      }
      var valor = parseFloat(porcentaje1.value);
      if (!isNaN(valor) && valor > 0 && valor < 100) {
        porcentaje2.value = (100 - valor).toFixed(2);
      }
    });
    porcentaje2.addEventListener("input", function () {
      segundoEditado = true;
    });
  }

  radios.forEach(function (radio) {
    radio.addEventListener("change", actualizar);
  });
  modalidad.addEventListener("change", actualizar);
  actualizar();
})();
