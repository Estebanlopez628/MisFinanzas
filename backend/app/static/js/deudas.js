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
 *
 * Contención de la tabla (ADR-62)
 * -------------------------------
 * La caja de deudas usa `contain: paint` para que la tabla ancha no ensanche el
 * layout del navegador móvil. Como la contención recortaría el modal, al abrir
 * uno de sus `<details>` en móvil se traslada al `body` y al cerrarse vuelve a
 * su fila mediante un marcador; así el modal sigue centrado en el viewport.
 */
(function () {
  "use strict";

  var marcadores = new WeakMap();

  function esMovil() {
    return window.matchMedia && window.matchMedia("(max-width: 640px)").matches;
  }

  function sacarDeLaTabla(detalles) {
    // Solo los modales de la tabla de deudas viven dentro de una caja con
    // `contain: paint`; el resto se queda en su sitio.
    if (!esMovil() || !detalles.closest(".tabla-contenedor--deudas")) {
      return;
    }
    if (marcadores.has(detalles)) {
      return;
    }
    var marcador = document.createComment("modal-deuda");
    detalles.parentNode.insertBefore(marcador, detalles);
    marcadores.set(detalles, marcador);
    document.body.appendChild(detalles);
  }

  function devolverALaTabla(detalles) {
    var marcador = marcadores.get(detalles);
    if (!marcador) {
      return;
    }
    if (marcador.parentNode) {
      marcador.parentNode.insertBefore(detalles, marcador);
      marcador.parentNode.removeChild(marcador);
    }
    marcadores.delete(detalles);
  }

  function vigilarPortabilidad(detalles) {
    detalles.addEventListener("toggle", function () {
      if (detalles.open) {
        sacarDeLaTabla(detalles);
      } else {
        devolverALaTabla(detalles);
      }
    });
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

  document
    .querySelectorAll(".tabla--deudas details.edicion-gasto--modal")
    .forEach(vigilarPortabilidad);

  // Escritorio: el botón «Actualizar» de cada fila abre su modal de edición.
  document.querySelectorAll("[data-abrir-atajo]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      var fila = boton.closest("tr");
      var detalles = fila && fila.querySelector("details.atajo-modal");
      if (!detalles) {
        return;
      }
      cerrarOtras(detalles);
      detalles.open = true;
    });
  });

  // SRS v2.0, sección 2.2: al cargar «Registro y Detalles de deudas» se verifica
  // si hay un formulario esperando su deuda. El servidor ya pintó el banner
  // cuando llegamos desde «Ve a registrar la deuda»; aquí solo se confirma con
  // sessionStorage y se ajusta la etiqueta legible.
  function pendienteDeDeuda() {
    try {
      return JSON.parse(sessionStorage.getItem("misfinanzas_pending_debt_link") || "null");
    } catch (error) {
      return null;
    }
  }

  var pendiente = pendienteDeDeuda();
  var banner = document.querySelector("[data-banner-volver]");
  if (pendiente && banner) {
    var enlace = banner.querySelector("[data-volver-origen]");
    if (enlace && pendiente.origin_label) {
      enlace.textContent =
        "← Volver a " + pendiente.origin_label + " para completar el registro";
      var reciente = banner.getAttribute("data-deuda-reciente");
      var destino = enlace.getAttribute("data-destino") || pendiente.origin_destino || "/";
      if (reciente) {
        enlace.href =
          destino + "?guardado_deuda=1&deuda_id=" + encodeURIComponent(reciente);
      }
    }
  }
})();
