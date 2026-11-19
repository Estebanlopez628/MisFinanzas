/**
 * Mejoras progresivas globales.
 *
 * Responsabilidad
 * ---------------
 * - Copiar referencias al portapapeles (Chancucos) con confirmación visual.
 * - Añadir filas a la venta multipartida de OLB_BYTE sin JavaScript de cálculo.
 * - Cerrar las ediciones en línea con «Cancelar» y confirmar las acciones
 *   masivas marcadas con `data-confirmar` (SRS v1.7).
 * - Mostrar el segundo día de pago solo cuando el atajo no es un pago único.
 * - Mostrar la fecha final solo en contratos a término fijo (Trabajos Extras).
 * - Registrar el service worker para que la PWA sea instalable y funcione sin red
 *   en las pantallas ya visitadas.
 *
 * Ninguna regla de negocio vive aquí: solo se manipula el DOM.
 */

(function () {
  "use strict";

  /**
   * Copia un texto al portapapeles y avisa al usuario.
   *
   * @param {string} texto Contenido a copiar.
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function copiar(texto, boton) {
    var confirmar = function () {
      var original = boton.textContent;
      boton.textContent = "Copiado";
      window.setTimeout(function () {
        boton.textContent = original;
      }, 1500);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(confirmar).catch(function () {
        seleccionarManual(texto);
      });
      return;
    }
    seleccionarManual(texto);
  }

  /**
   * Respaldo para navegadores sin API de portapapeles.
   *
   * @param {string} texto Contenido a copiar.
   */
  function seleccionarManual(texto) {
    var area = document.createElement("textarea");
    area.value = texto;
    area.setAttribute("readonly", "readonly");
    area.style.position = "absolute";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
    } catch (error) {
      // Sin soporte: el usuario puede copiar el número manualmente.
    }
    document.body.removeChild(area);
  }

  var botonesCopiar = document.querySelectorAll("[data-copiar]");
  for (var i = 0; i < botonesCopiar.length; i += 1) {
    botonesCopiar[i].addEventListener("click", function (evento) {
      copiar(evento.currentTarget.getAttribute("data-copiar"), evento.currentTarget);
    });
  }

  // ------------------- Login, diálogos de detalle ------------------------

  // Mostrar u ocultar la contraseña del login sin recargar la página.
  document.addEventListener("click", function (evento) {
    var objetivo = evento.target instanceof Element ? evento.target.closest("[data-mostrar-clave]") : null;
    if (!objetivo) {
      return;
    }
    var campo = document.getElementById(objetivo.getAttribute("data-mostrar-clave"));
    if (!campo) {
      return;
    }
    var mostrar = campo.type === "password";
    campo.type = mostrar ? "text" : "password";
    objetivo.setAttribute("aria-pressed", mostrar ? "true" : "false");
    objetivo.setAttribute("aria-label", mostrar ? "Ocultar contraseña" : "Mostrar contraseña");
  });

  // Abrir y cerrar el detalle de una orden o pendiente (vista móvil).
  document.addEventListener("click", function (evento) {
    var objetivo = evento.target instanceof Element ? evento.target : null;
    if (!objetivo) {
      return;
    }
    var abrir = objetivo.closest("[data-abrir-dialogo]");
    if (abrir) {
      var dialogo = document.getElementById(abrir.getAttribute("data-abrir-dialogo"));
      if (dialogo && typeof dialogo.showModal === "function") {
        dialogo.showModal();
      }
      return;
    }
    var cerrar = objetivo.closest("[data-cerrar-dialogo]");
    if (cerrar) {
      var contenedor = cerrar.closest("dialog");
      if (contenedor) {
        contenedor.close();
      }
    }
  });

  // ------------------- Ediciones en línea y confirmaciones ----------------

  /**
   * Cierra un desplegable de edición en línea y descarta lo escrito.
   *
   * @param {HTMLDetailsElement} detalles Desplegable de edición abierto.
   */
  function cerrarEdicion(detalles) {
    var formulario = detalles.querySelector("form");
    if (formulario) {
      formulario.reset();
    }
    detalles.open = false;
  }

  // SRS v1.7: «Cancelar» cierra el desplegable de edición y descarta lo escrito.
  document.addEventListener("click", function (evento) {
    var objetivo = evento.target;
    if (!(objetivo instanceof Element)) {
      return;
    }
    var cancelar = objetivo.closest("[data-cancelar-edicion]");
    if (!cancelar) {
      return;
    }
    evento.preventDefault();
    var detalles = cancelar.closest("details");
    if (detalles) {
      cerrarEdicion(detalles);
    }
  });

  // Ajuste móvil (SRS v1.7): el fondo oscuro de la ventana de edición se dibuja
  // con `::before` sobre el propio <details>, de modo que tocarlo llega aquí
  // como un clic en el desplegable. Se cierra sin guardar. El resumen y los
  // campos detienen el evento en sí mismos, así que no entran en este caso.
  document.addEventListener("click", function (evento) {
    var objetivo = evento.target;
    if (!(objetivo instanceof Element)) {
      return;
    }
    if (!objetivo.classList.contains("edicion-gasto--modal") || !objetivo.open) {
      return;
    }
    cerrarEdicion(objetivo);
  });

  // La tecla Escape también descarta la edición, útil con el teclado abierto.
  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") {
      return;
    }
    var abiertos = document.querySelectorAll("details.edicion-gasto--modal[open]");
    for (var k = 0; k < abiertos.length; k += 1) {
      cerrarEdicion(abiertos[k]);
    }
  });

  // SRS v1.7: las acciones destructivas o masivas piden confirmación con un
  // atributo, sin depender de manejadores incrustados en el HTML.
  document.addEventListener("submit", function (evento) {
    var formulario = evento.target;
    if (!(formulario instanceof HTMLFormElement)) {
      return;
    }
    var mensaje = formulario.getAttribute("data-confirmar");
    if (mensaje && !window.confirm(mensaje)) {
      evento.preventDefault();
    }
  });

  // ------------------ Tipo de contrato de Trabajos Extras ------------------

  // SRS v1.7: la fecha final solo aplica al contrato a término fijo. Sin
  // JavaScript el campo queda visible y el servidor ignora el valor si no aplica.
  var selectorContrato = document.querySelector("[data-contrato-tipo]");
  var campoFin = document.querySelector("[data-contrato-fin]");
  if (selectorContrato && campoFin) {
    var sincronizarContrato = function () {
      campoFin.hidden = selectorContrato.value !== "TERMINO_FIJO";
    };
    selectorContrato.addEventListener("change", sincronizarContrato);
    sincronizarContrato();
  }

  // SRS v1.8: en Trabajos Extras la frecuencia decide si se piden los datos de
  // quincena, y «¿conoce el porcentaje?» decide qué reparto se muestra. Sin
  // JavaScript los campos quedan visibles y el servidor valida.
  var selectorFrecuencia = document.querySelector("[data-frecuencia-tipo]");
  var selectorConoce = document.querySelector("[data-conoce-porcentaje]");
  if (selectorFrecuencia) {
    var sincronizarFrecuencia = function () {
      var quincenal = selectorFrecuencia.value === "QUINCENAL";
      var conoce = selectorConoce ? selectorConoce.value === "1" : false;
      var campos = document.querySelectorAll("[data-solo-quincenal]");
      for (var s = 0; s < campos.length; s += 1) {
        var campo = campos[s];
        var oculto = !quincenal;
        if (campo.hasAttribute("data-conoce-si")) {
          oculto = oculto || !conoce;
        }
        if (campo.hasAttribute("data-conoce-no")) {
          oculto = oculto || conoce;
        }
        campo.hidden = oculto;
      }
    };
    selectorFrecuencia.addEventListener("change", sincronizarFrecuencia);
    if (selectorConoce) {
      selectorConoce.addEventListener("change", sincronizarFrecuencia);
    }
    sincronizarFrecuencia();
  }

  // ------------------- Filas dinámicas de la venta -------------------------

  var botonAgregar = document.querySelector("[data-agregar-linea]");
  var cuerpoLineas = document.querySelector("[data-lineas]");
  if (botonAgregar && cuerpoLineas) {
    botonAgregar.addEventListener("click", function () {
      var primera = cuerpoLineas.querySelector("tr");
      if (!primera) {
        return;
      }
      var nueva = primera.cloneNode(true);
      var campos = nueva.querySelectorAll("input, select");
      for (var j = 0; j < campos.length; j += 1) {
        if (campos[j].tagName === "INPUT") {
          campos[j].value = campos[j].name === "cantidad" ? "1" : "";
        } else {
          campos[j].selectedIndex = 0;
        }
      }
      cuerpoLineas.appendChild(nueva);
    });
  }

  // --------------------- Días de pago de los atajos -----------------------

  // SRS v1.7: con «único pago mensual» el segundo día no aplica. Sin JavaScript
  // el campo sigue visible y el servidor ignora el segundo día si no se usa.
  var radiosPago = document.querySelectorAll("[data-pago-unico]");
  var bloquesDia = document.querySelectorAll("[data-dia-pago]");
  if (radiosPago.length && bloquesDia.length) {
    var sincronizarDias = function () {
      var unico = document.querySelector('[data-pago-unico][value="1"]');
      var esUnico = !unico || unico.checked;
      for (var d = 0; d < bloquesDia.length; d += 1) {
        bloquesDia[d].hidden = esUnico;
      }
    };
    for (var r = 0; r < radiosPago.length; r += 1) {
      radiosPago[r].addEventListener("change", sincronizarDias);
    }
    sincronizarDias();
  }

  // ------------------------- Service worker (PWA) -------------------------

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {
        // La aplicación sigue funcionando aunque el navegador no permita el SW.
      });
    });
  }
})();
