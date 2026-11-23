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

  /** Duración de la confirmación visual de «Copiar» (5 segundos). */
  var CONFIRMACION_COPIADO_MS = 5000;

  /**
   * Devuelve un botón de copiado a su texto y estilo originales.
   *
   * @param {HTMLElement} boton Botón a restaurar.
   */
  function restaurarBotonCopiar(boton) {
    if (!boton.classList.contains("boton--copiado")) {
      return;
    }
    boton.textContent = boton.getAttribute("data-texto-original") || "Copiar";
    boton.classList.remove("boton--copiado");
    boton.removeAttribute("data-texto-original");
  }

  /**
   * Muestra «¡Copiado!» solo en el botón pulsado y lo restaura a los 5 segundos.
   *
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function confirmarCopia(boton) {
    document.querySelectorAll(".boton--copiado").forEach(function (otro) {
      if (otro !== boton) {
        restaurarBotonCopiar(otro);
      }
    });
    if (!boton.classList.contains("boton--copiado")) {
      boton.setAttribute("data-texto-original", boton.textContent);
      boton.classList.add("boton--copiado");
    }
    boton.textContent = "¡Copiado!";
    window.setTimeout(function () {
      restaurarBotonCopiar(boton);
    }, CONFIRMACION_COPIADO_MS);
  }

  /**
   * Copia un texto al portapapeles y avisa al usuario.
   *
   * @param {string} texto Contenido a copiar.
   * @param {HTMLElement} boton Botón que disparó la acción.
   */
  function copiar(texto, boton) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto)
        .then(function () { confirmarCopia(boton); })
        .catch(function () {
          seleccionarManual(texto);
          confirmarCopia(boton);
        });
      return;
    }
    seleccionarManual(texto);
    confirmarCopia(boton);
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
    // SRS v2.0, sección 5.2: invitación exclusiva de móvil. El enlace universal
    // sin destinatario abre la lista de contactos de WhatsApp.
    var invitar = objetivo.closest("[data-invitar-amigos]");
    if (invitar) {
      evento.preventDefault();
      var mensaje =
        "Acabo de probar esta aplicación y es súper buena, quiero invitarte a que la utilices y lleves el control de tus finanzas: " +
        window.location.origin;
      window.open("https://wa.me/?text=" + encodeURIComponent(mensaje), "_blank");
    }
  });

  // SRS v3.9.1, sección 2: en escritorio, un clic en cualquier zona del campo
  // de fecha despliega el calendario de inmediato sin perder la edición a mano.
  var esMovil = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  if (!esMovil) {
    document.addEventListener("click", function (evento) {
      var campo = evento.target;
      if (!(campo instanceof HTMLInputElement) || campo.type !== "date") {
        return;
      }
      if (typeof campo.showPicker !== "function") {
        return;
      }
      try {
        campo.showPicker();
      } catch (error) {
        // El navegador ya abrió el calendario o exige un gesto distinto.
      }
    });
  }

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

  /**
   * Quita prefijos técnicos de Pydantic antes de mostrar un error (SRS v3.9.3).
   *
   * @param {string} texto Mensaje recibido del servidor.
   * @returns {string} Mensaje limpio y legible.
   */
  function limpiarMensajeError(texto) {
    return String(texto || "")
      .replace(/^tasa_implicita:\s*Value error,\s*/i, "")
      .replace(/^Value error,\s*/i, "")
      .trim();
  }
  window.limpiarMensajeError = limpiarMensajeError;

  // SRS v3.9.1, sección 3: sistema global de modales. Ningún flujo dispara
  // diálogos nativos del navegador (alertas, confirmaciones o prompts).
  var modalConfirmacion = document.getElementById("modal-confirmacion");
  var modalAviso = document.getElementById("modal-aviso");
  var respuestaConfirmacion = null;

  /**
   * Cierra el modal de confirmación con una respuesta.
   *
   * @param {boolean} valor `true` si el usuario aceptó.
   */
  function cerrarConfirmacion(valor) {
    if (!modalConfirmacion) {
      return;
    }
    modalConfirmacion.hidden = true;
    if (respuestaConfirmacion) {
      respuestaConfirmacion(valor);
      respuestaConfirmacion = null;
    }
  }

  /**
   * Abre el modal de confirmación propio.
   *
   * @param {string} mensaje Texto a mostrar.
   * @param {boolean} peligro `true` para una eliminación definitiva.
   * @returns {Promise<boolean>} `true` si el usuario confirmó.
   */
  function pedirConfirmacion(mensaje, peligro) {
    if (!modalConfirmacion) {
      return Promise.resolve(false);
    }
    var cuerpo = document.getElementById("modal-confirmacion-cuerpo");
    var icono = document.getElementById("modal-confirmacion-icono");
    var aceptar = modalConfirmacion.querySelector("[data-confirm-aceptar]");
    if (cuerpo) {
      cuerpo.textContent = mensaje;
    }
    if (icono) {
      icono.textContent = peligro ? "!" : "?";
    }
    if (aceptar) {
      aceptar.className = peligro ? "boton boton--peligro" : "boton boton--primario";
      aceptar.textContent = peligro ? "Eliminar" : "Confirmar";
    }
    modalConfirmacion.hidden = false;
    return new Promise(function (resolver) {
      respuestaConfirmacion = resolver;
    });
  }

  // SRS v4.4, sección 5.2: los módulos con peticiones DELETE reutilizan estos
  // modales propios en lugar de inventar otro diálogo.
  window.pedirConfirmacion = pedirConfirmacion;
  window.mostrarAvisoApp = mostrarAvisoApp;

  if (modalConfirmacion) {
    var cancelar = modalConfirmacion.querySelector("[data-confirm-cancelar]");
    var aceptar = modalConfirmacion.querySelector("[data-confirm-aceptar]");
    if (cancelar) {
      cancelar.addEventListener("click", function () { cerrarConfirmacion(false); });
    }
    if (aceptar) {
      aceptar.addEventListener("click", function () { cerrarConfirmacion(true); });
    }
    modalConfirmacion.addEventListener("click", function (evento) {
      if (evento.target === modalConfirmacion) {
        cerrarConfirmacion(false);
      }
    });
  }

  /**
   * Muestra un aviso con el modal oscuro de la app.
   *
   * @param {string} mensaje Texto a mostrar.
   */
  function mostrarAvisoApp(mensaje) {
    if (!modalAviso) {
      return;
    }
    var cuerpo = document.getElementById("modal-aviso-cuerpo");
    if (cuerpo) {
      cuerpo.textContent = mensaje;
    }
    modalAviso.hidden = false;
    var entendido = modalAviso.querySelector("[data-aviso-entendido]");
    if (entendido) {
      entendido.focus();
    }
  }

  if (modalAviso) {
    var entendido = modalAviso.querySelector("[data-aviso-entendido]");
    if (entendido) {
      entendido.addEventListener("click", function () { modalAviso.hidden = true; });
    }
    modalAviso.addEventListener("click", function (evento) {
      if (evento.target === modalAviso) {
        modalAviso.hidden = true;
      }
    });
  }

  // Formularios con confirmación: se detiene el envío hasta que el usuario
  // responda en el modal propio.
  document.addEventListener("submit", function (evento) {
    var formulario = evento.target;
    if (!(formulario instanceof HTMLFormElement)) {
      return;
    }
    var mensaje = formulario.getAttribute("data-confirmar");
    if (!mensaje) {
      return;
    }
    evento.preventDefault();
    pedirConfirmacion(mensaje, formulario.hasAttribute("data-confirmar-peligro")).then(function (ok) {
      if (ok) {
        formulario.submit();
      }
    });
  });

  // Botones y enlaces con confirmación (incluidos los que usan `formaction`).
  document.addEventListener("click", function (evento) {
    var objetivo = evento.target;
    if (!(objetivo instanceof Element)) {
      return;
    }
    var control = objetivo.closest("[data-confirmar]");
    if (!control || control.tagName === "FORM") {
      return;
    }
    evento.preventDefault();
    var peligro = control.hasAttribute("data-confirmar-peligro");
    pedirConfirmacion(control.getAttribute("data-confirmar"), peligro).then(function (ok) {
      if (!ok) {
        return;
      }
      var formulario = control.form;
      if (formulario) {
        if (typeof formulario.requestSubmit === "function") {
          formulario.requestSubmit(control);
        } else {
          formulario.submit();
        }
      } else if (control.tagName === "A") {
        window.location.href = control.getAttribute("href");
      }
    });
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

  // ------------------ Blindaje de datos escritos por el usuario -------------
  //
  // SRS v1.8: antes de enviar, los campos numéricos se revisan en el navegador.
  // Si alguien escribe una letra donde va un número (o al contrario), el envío
  // se detiene y el campo se marca. El servidor vuelve a validar siempre, así
  // que apagar JavaScript no abre un hueco: solo se pierde el aviso temprano.
  document.addEventListener(
    "submit",
    function (evento) {
      var formulario = evento.target;
      if (!(formulario instanceof HTMLFormElement)) {
        return;
      }
      var controles = formulario.querySelectorAll(
        'input[inputmode="decimal"], input[inputmode="numeric"], input[type="number"]'
      );
      for (var c = 0; c < controles.length; c += 1) {
        var control = controles[c];
        if (control.disabled || control.value === "") {
          continue;
        }
        var decimal = control.getAttribute("inputmode") === "decimal";
        var patron = decimal ? /^-?[\d.,\s$%]*$/ : /^-?[\d.,\s]*$/;
        if (!patron.test(control.value)) {
          evento.preventDefault();
          control.setCustomValidity(
            "Escribe solo números" +
              (decimal ? " (puedes usar puntos de miles y coma decimal)." : ".")
          );
          control.reportValidity();
          control.focus();
          control.addEventListener(
            "input",
            function () {
              this.setCustomValidity("");
            },
            { once: true }
          );
          return;
        }
      }
    },
    true
  );

  // ------------------------- Service worker (PWA) -------------------------

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {
        // La aplicación sigue funcionando aunque el navegador no permita el SW.
      });
    });
  }

  // SRS v4.4, sección 6: conservar la posición de desplazamiento cuando un
  // formulario recarga la página. Nunca se fuerza el desplazamiento al inicio:
  // se guarda `window.scrollY`, se restaura con `behavior: "instant"` y, si el módulo
  // expone un bloque de pago cercano, se ancla con `block: "nearest"`.
  var CLAVE_SCROLL = "misfinanzas_saved_scroll_y";
  var CLAVE_ANCLA = "misfinanzas_saved_scroll_ancla";

  // Si el navegador restaura por su cuenta, lo hace después de este script y
  // nos devuelve al inicio. La posición la decide esta aplicación.
  if ("scrollRestoration" in window.history) {
    window.history.scrollRestoration = "manual";
  }

  /**
   * Devuelve el identificador del bloque de pago más cercano al viewport.
   *
   * @returns {string} Id del ancla, o cadena vacía si no hay ninguna.
   */
  function anclaCercana() {
    var bloques = document.querySelectorAll(
      "[data-quincena], #bloque-quincena-1, #bloque-quincena-2, #bloque-pago-mensual"
    );
    var mejor = null;
    var menorDistancia = Infinity;
    bloques.forEach(function (bloque) {
      var distancia = Math.abs(bloque.getBoundingClientRect().top);
      if (distancia < menorDistancia) {
        menorDistancia = distancia;
        mejor = bloque;
      }
    });
    if (!mejor) {
      return "";
    }
    if (mejor.id) {
      return mejor.id;
    }
    var numero = mejor.getAttribute("data-quincena");
    if (numero === "0") {
      return "bloque-pago-mensual";
    }
    if (numero === "1") {
      return "bloque-quincena-1";
    }
    if (numero === "2") {
      return "bloque-quincena-2";
    }
    return "";
  }

  /**
   * Guarda la posición actual antes de que el servidor responda.
   */
  function guardarScroll() {
    try {
      sessionStorage.setItem(CLAVE_SCROLL, String(window.scrollY || 0));
      sessionStorage.setItem(CLAVE_ANCLA, anclaCercana());
    } catch (error) {
      // Sin sessionStorage el formulario sigue funcionando desde el inicio.
    }
  }

  document.addEventListener("submit", guardarScroll, true);

  try {
    var scrollGuardado = sessionStorage.getItem(CLAVE_SCROLL);
    var anclaGuardada = sessionStorage.getItem(CLAVE_ANCLA);
    sessionStorage.removeItem(CLAVE_SCROLL);
    sessionStorage.removeItem(CLAVE_ANCLA);
    if (scrollGuardado !== null) {
      window.scrollTo({ top: Number(scrollGuardado) || 0, behavior: "instant" });
      if (anclaGuardada) {
        var bloque = document.getElementById(anclaGuardada);
        if (bloque && bloque.scrollIntoView) {
          bloque.scrollIntoView({ behavior: "instant", block: "nearest" });
        }
      }
    }
  } catch (error) {
    // Sin sessionStorage no hay posición que restaurar.
  }
})();
