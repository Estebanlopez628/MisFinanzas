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

  /* SRS v4.44, sección 2: errores de edición de atajos dentro del modal. */
  (function () {
    function mostrarErrorModal(formulario, banner, texto) {
      if (!banner) return;
      banner.textContent = typeof window.limpiarMensajeError === "function"
        ? window.limpiarMensajeError(texto)
        : texto;
      banner.hidden = false;
      formulario.scrollTop = 0;
    }

    function ocultarErrorModal(banner) {
      if (!banner) return;
      banner.hidden = true;
      banner.textContent = "";
    }

    function validarAtajo(formulario) {
      var descripcion = formulario.querySelector('[name="descripcion"]');
      var referencia = formulario.querySelector('[name="numero_referencia"]');
      var url = formulario.querySelector("[data-url-pago]");
      if (descripcion && !descripcion.value.trim()) {
        return "La descripción del atajo es obligatoria.";
      }
      if (referencia && !referencia.value.trim()) {
        return "El número de referencia es obligatorio.";
      }
      if (url) {
        url.value = normalizarEnlaceModal(url.value);
        var valor = url.value.trim();
        if (valor && !/^(https?:\/\/|[a-zA-Z][a-zA-Z0-9+.-]*:\/\/).*/i.test(valor)) {
          return "Enlace inválido. Usa formato web (https://...) o de app móvil (ej. daviplata://).";
        }
      }
      return "";
    }

    function normalizarEnlaceModal(texto) {
      var limpio = (texto || "").trim();
      if (!limpio || /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(limpio)) return limpio;
      if (/^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(\/.*)?$/.test(limpio)) return "https://" + limpio;
      if (/^[a-zA-Z][a-zA-Z0-9+.-]*$/.test(limpio)) return limpio.toLowerCase() + "://";
      return limpio;
    }

    document.querySelectorAll("form[data-atajo-editar]").forEach(function (formulario) {
      var banner = formulario.querySelector("[data-error-modal]");
      var detalles = formulario.closest("details");

      formulario.addEventListener("input", function () {
        ocultarErrorModal(banner);
      });
      if (detalles) {
        detalles.addEventListener("toggle", function () {
          if (detalles.open) ocultarErrorModal(banner);
        });
      }

      formulario.addEventListener("submit", function (evento) {
        // «Eliminar» usa formaction y sigue su flujo normal con confirmación.
        if (evento.submitter && evento.submitter.hasAttribute("formaction")) {
          return;
        }
        evento.preventDefault();
        var error = validarAtajo(formulario);
        if (error) {
          mostrarErrorModal(formulario, banner, error);
          return;
        }
        fetch(formulario.action, {
          method: "POST",
          body: new FormData(formulario),
          redirect: "follow",
        })
          .then(function (respuesta) {
            var destino = new URL(respuesta.url, window.location.href);
            var detalle = destino.searchParams.get("error");
            if (!respuesta.ok || detalle) {
              mostrarErrorModal(
                formulario,
                banner,
                detalle || "No se pudo guardar el atajo. Intenta nuevamente."
              );
              return;
            }
            window.recargarManteniendoScroll();
          })
          .catch(function () {
            mostrarErrorModal(
              formulario,
              banner,
              "No se pudo guardar el atajo. Revisa la conexión e intenta de nuevo."
            );
          });
      });
    });
  })();

  /* SRS v4.42: Deep Links nativos y apertura inteligente de «Pagar». */
  (function () {
    var REGEX_URL_PAGO = /^(https?:\/\/|[a-zA-Z][a-zA-Z0-9+.-]*:\/\/).*/i;

    /**
     * Normaliza un enlace de pago antes de validarlo (SRS v4.44, sección 1).
     *
     * @param {string} texto Valor escrito por el usuario.
     * @returns {string} Enlace con esquema, o el texto original si no aplica.
     */
    function normalizarEnlace(texto) {
      var limpio = (texto || "").trim();
      if (!limpio || REGEX_URL_PAGO.test(limpio)) {
        return limpio;
      }
      if (/^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(\/.*)?$/.test(limpio)) {
        return "https://" + limpio;
      }
      if (/^[a-zA-Z][a-zA-Z0-9+.-]*$/.test(limpio)) {
        return limpio.toLowerCase() + "://";
      }
      return limpio;
    }

    document.addEventListener("click", function (evento) {
      var control = evento.target instanceof Element
        ? evento.target.closest("[data-pagar-atajo]")
        : null;
      if (!control) {
        return;
      }
      var url = (
        control.getAttribute("data-url") || control.getAttribute("href") || ""
      ).trim();
      if (!url) {
        return;
      }
      evento.preventDefault();
      if (/^https?:\/\//i.test(url)) {
        window.open(url, "_blank", "noopener,noreferrer");
      } else {
        // iOS Safari y Android disparan la app nativa sin pestaña residual.
        window.location.href = url;
      }
    });

    // El formulario acepta https:// y esquemas de app (daviplata://, nequi://…).
    document.addEventListener(
      "submit",
      function (evento) {
        var formulario = evento.target;
        if (!(formulario instanceof HTMLFormElement)) {
          return;
        }
        var campo = formulario.querySelector("[data-url-pago]");
        if (!campo) {
          return;
        }
        var valor = normalizarEnlace(campo.value);
        campo.value = valor;
        if (valor && !REGEX_URL_PAGO.test(valor)) {
          evento.preventDefault();
          campo.setCustomValidity(
            "Escribe https://... o un enlace de app como daviplata://."
          );
          if (typeof campo.reportValidity === "function") {
            campo.reportValidity();
          }
          campo.addEventListener("input", function limpiar() {
            campo.setCustomValidity("");
            campo.removeEventListener("input", limpiar);
          });
        }
      },
      true
    );
  })();

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
        // Guardar la posición antes de abrir el modal: al registrar un gasto
        // desde aquí se recarga la página y debemos volver al mismo punto.
        if (typeof guardarScroll === "function") {
          guardarScroll();
        }
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
      var texto = encodeURIComponent(mensaje);
      // En móvil se usa el esquema nativo sobre la ventana actual: así no
      // queda una pestaña web en blanco esperando a que WhatsApp tome control.
      if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
        window.location.href = "whatsapp://send?text=" + texto;
      } else {
        window.open("https://wa.me/?text=" + texto, "_blank", "noopener,noreferrer");
      }
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
  // SRS v4.38: la fila inhabilitada usa `opacity < 1`, que crea un contexto de
  // apilamiento y deja el modal detrás de la liquidación. Mientras está abierto
  // se traslada al <body> (como en Deudas) y al cerrarse vuelve a su fila.
  function sacarDelContexto(detalles) {
    // Solo los ítems inhabilitados tienen `opacity < 1`: los demás modales
    // (atajos, deudas, OLB_BYTE) se quedan en su sitio, sin cambios.
    if (
      !detalles.open ||
      !detalles.classList.contains("edicion-gasto--modal") ||
      !detalles.closest("li.lista-gastos__item--inhabilitado")
    ) {
      return;
    }
    if (detalles._marcadorEdicion) {
      return;
    }
    var marcador = document.createComment("modal-edicion-gasto");
    detalles.parentNode.insertBefore(marcador, detalles);
    detalles._marcadorEdicion = marcador;
    document.body.appendChild(detalles);
  }

  function devolverAlContexto(detalles) {
    var marcador = detalles._marcadorEdicion;
    if (!marcador) {
      return;
    }
    if (marcador.parentNode) {
      marcador.parentNode.insertBefore(detalles, marcador);
      marcador.parentNode.removeChild(marcador);
    }
    detalles._marcadorEdicion = null;
  }

  document.querySelectorAll("details.edicion-gasto--modal").forEach(function (detalles) {
    detalles.addEventListener("toggle", function () {
      if (detalles.open) {
        sacarDelContexto(detalles);
      } else {
        devolverAlContexto(detalles);
      }
    });
  });

  function cerrarEdicion(detalles) {
    var formulario = detalles.querySelector("form");
    if (formulario) {
      formulario.reset();
    }
    detalles.open = false;
    devolverAlContexto(detalles);
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
   * Coloca un modal dentro del `<dialog>` abierto para que herede su capa
   * superior; un div con z-index siempre queda detrás de un dialog nativo.
   *
   * @param {Element} modal Modal propio de la app.
   * @returns {Element | null} Dialog abierto, o null si no hay.
   */
  function elevarSobreDialogo(modal) {
    var dialogo = document.querySelector("dialog[open]");
    if (dialogo && modal && modal.parentElement !== dialogo) {
      modal.setAttribute("data-padre-original", modal.parentElement.tagName.toLowerCase());
      dialogo.appendChild(modal);
    }
    return dialogo;
  }

  /**
   * Devuelve un modal a su contenedor original al cerrarse.
   *
   * @param {Element} modal Modal propio de la app.
   */
  function reposicionarModal(modal) {
    if (!modal || !modal.hasAttribute("data-padre-original")) {
      return;
    }
    modal.removeAttribute("data-padre-original");
    document.body.appendChild(modal);
  }

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
    reposicionarModal(modalConfirmacion);
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
    elevarSobreDialogo(modalConfirmacion);
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
    elevarSobreDialogo(modalAviso);
    modalAviso.hidden = false;
    var entendido = modalAviso.querySelector("[data-aviso-entendido]");
    if (entendido) {
      entendido.focus();
    }
  }

  if (modalAviso) {
    var entendido = modalAviso.querySelector("[data-aviso-entendido]");
    if (entendido) {
      entendido.addEventListener("click", function () {
        modalAviso.hidden = true;
        reposicionarModal(modalAviso);
      });
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
        // La posición se guarda de nuevo porque el modal pudo desplazar la vista.
        guardarScroll();
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
          guardarScroll();
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

  // SRS v4.4 y v4.38: conservar la posición exacta de desplazamiento cuando un
  // formulario, un modal o una acción con fetch recarga la página. Se guardan
  // X e Y y se restauran con `behavior: "instant"`; el bloque de pago cercano
  // solo se ancla con `block: "nearest"` para no alterar la posición guardada.
  var CLAVE_SCROLL = "misfinanzas_saved_scroll_y";
  var CLAVE_SCROLL_X = "misfinanzas_saved_scroll_x";
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
   * Guarda la posición vertical y horizontal antes de cualquier navegación.
   *
   * @returns {void}
   */
  function guardarScroll() {
    try {
      sessionStorage.setItem(
        CLAVE_SCROLL_X,
        String(window.scrollX || window.pageXOffset || 0)
      );
      sessionStorage.setItem(
        CLAVE_SCROLL,
        String(window.scrollY || window.pageYOffset || 0)
      );
      sessionStorage.setItem(CLAVE_ANCLA, anclaCercana());
    } catch (error) {
      // Sin sessionStorage la aplicación sigue funcionando desde el inicio.
    }
  }

  // Los manejadores fuera de este ámbito (omitir, eliminar, habilitar, abonos)
  // recargan la página: deben guardar la posición antes de recargar.
  window.guardarScrollApp = guardarScroll;
  window.recargarManteniendoScroll = function (yaGuardado) {
    if (!yaGuardado) {
      guardarScroll();
    }
    window.location.reload();
  };

  document.addEventListener("submit", guardarScroll, true);

  var xGuardado = null;
  var yGuardado = null;
  var anclaGuardada = null;
  try {
    var textoX = sessionStorage.getItem(CLAVE_SCROLL_X);
    var textoY = sessionStorage.getItem(CLAVE_SCROLL);
    anclaGuardada = sessionStorage.getItem(CLAVE_ANCLA);
    sessionStorage.removeItem(CLAVE_SCROLL_X);
    sessionStorage.removeItem(CLAVE_SCROLL);
    sessionStorage.removeItem(CLAVE_ANCLA);
    if (textoX !== null || textoY !== null) {
      xGuardado = Number(textoX) || 0;
      yGuardado = Number(textoY) || 0;
    }
  } catch (error) {
    // Sin sessionStorage no hay posición que restaurar.
  }

  /**
   * Restaura la posición guardada una vez que el layout está listo.
   *
   * @returns {void}
   */
  function restaurarScroll() {
    if (xGuardado === null && yGuardado === null) {
      return;
    }
    // SRS v4.38: se restaura literalmente X e Y. El antiguo `scrollIntoView`
    // del ancla podía desplazar la vista después de guardar y era la causa de
    // que una acción en quincena 1 devolviera a otra posición. El flujo de
    // retorno de deudas tiene su propio anclaje en `deudas.js` y no se toca.
    // El backend vuelve a `/finanzas#quincenas`: el salto automático del ancla
    // debe retirarse para que la posición la decida esta restauración. El
    // anclaje del retorno de deudas vive en `deudas.js` y no se toca.
    try {
      if (window.location.hash === "#quincenas") {
        window.history.replaceState(
          null, "", window.location.pathname + window.location.search
        );
      }
    } catch (error) {
      // Sin history no hay ancla que retirar.
    }
    var objetivoX = xGuardado || 0;
    var objetivoY = yGuardado || 0;
    window.scrollTo({ left: objetivoX, top: objetivoY, behavior: "instant" });
    // El layout puede seguir acomodándose (cálculo inicial, fuentes, imágenes).
    // Se reaplica la misma posición en el siguiente cuadro y poco después.
    requestAnimationFrame(function () {
      window.scrollTo({ left: objetivoX, top: objetivoY, behavior: "instant" });
    });
    setTimeout(function () {
      window.scrollTo({ left: objetivoX, top: objetivoY, behavior: "instant" });
    }, 180);
    // El ancla `#quincenas` del backend puede desplazar la vista más tarde.
    setTimeout(function () {
      window.scrollTo({ left: objetivoX, top: objetivoY, behavior: "instant" });
    }, 500);
    // Los diálogos pueden devolver el foco al inicio después de `load`.
    setTimeout(function () {
      window.scrollTo({ left: objetivoX, top: objetivoY, behavior: "instant" });
    }, 1000);
  }

  if (document.readyState === "complete") {
    requestAnimationFrame(restaurarScroll);
  } else {
    window.addEventListener("load", function () {
      requestAnimationFrame(restaurarScroll);
    });
  }

  // SRS v4.44 (OLB_BYTE · Ventas): al abrir la factura o WhatsApp desde una
  // orden, guardar X, Y y el diálogo abierto con claves propias. Las claves
  // genéricas se consumen en la página intermedia de la factura, así que no
  // pueden usarse para el regreso a «Órdenes registradas».
  var CLAVE_OLB_X = "misfinanzas_olb_ventas_scroll_x";
  var CLAVE_OLB_Y = "misfinanzas_olb_ventas_scroll_y";
  var CLAVE_OLB_DIALOGO = "misfinanzas_olb_ventas_dialogo";
  var CLAVE_OLB_TIEMPO = "misfinanzas_olb_ventas_ts";

  /**
   * Guarda la posición y el diálogo abierto antes de salir de Ventas.
   *
   * @returns {void}
   */
  function guardarPosicionVentas() {
    try {
      sessionStorage.setItem(CLAVE_OLB_X, String(window.scrollX || window.pageXOffset || 0));
      sessionStorage.setItem(CLAVE_OLB_Y, String(window.scrollY || window.pageYOffset || 0));
      var abierto = document.querySelector("dialog[open]");
      sessionStorage.setItem(CLAVE_OLB_DIALOGO, abierto ? abierto.id : "");
      sessionStorage.setItem(CLAVE_OLB_TIEMPO, String(Date.now()));
    } catch (error) {
      // Sin sessionStorage el retorno empieza desde arriba, como antes.
    }
  }

  document.addEventListener(
    "click",
    function (evento) {
      var objetivo = evento.target instanceof Element ? evento.target : null;
      if (objetivo && objetivo.closest("[data-volver-ventas]")) {
        guardarPosicionVentas();
      }
    },
    true
  );

  /**
   * Restaura la posición exacta al volver a Ventas y reabre el diálogo móvil.
   *
   * @returns {void}
   */
  function restaurarPosicionVentas() {
    if (window.location.pathname.replace(/\/$/, "") !== "/olb-byte") {
      return;
    }
    var textoX;
    var textoY;
    var idDialogo;
    var textoFecha;
    try {
      textoX = sessionStorage.getItem(CLAVE_OLB_X);
      textoY = sessionStorage.getItem(CLAVE_OLB_Y);
      idDialogo = sessionStorage.getItem(CLAVE_OLB_DIALOGO);
      textoFecha = sessionStorage.getItem(CLAVE_OLB_TIEMPO);
      sessionStorage.removeItem(CLAVE_OLB_X);
      sessionStorage.removeItem(CLAVE_OLB_Y);
      sessionStorage.removeItem(CLAVE_OLB_DIALOGO);
      sessionStorage.removeItem(CLAVE_OLB_TIEMPO);
    } catch (error) {
      return;
    }
    if (textoX === null && textoY === null && !idDialogo) {
      return;
    }
    // Una pestaña muy antigua no debe mover la vista al abrir Ventas.
    if (textoFecha && Date.now() - Number(textoFecha) > 15 * 60 * 1000) {
      return;
    }
    var x = Number(textoX) || 0;
    var y = Number(textoY) || 0;

    /**
     * Aplica posición y diálogo; se repite porque el layout sigue acomodándose.
     *
     * @returns {void}
     */
    function aplicar() {
      if (idDialogo) {
        var dialogo = document.getElementById(idDialogo);
        if (dialogo && !dialogo.open && typeof dialogo.showModal === "function") {
          dialogo.showModal();
        }
      }
      window.scrollTo({ left: x, top: y, behavior: "instant" });
    }

    aplicar();
    requestAnimationFrame(aplicar);
    window.setTimeout(aplicar, 180);
    window.setTimeout(aplicar, 500);
  }

  if (document.readyState === "complete") {
    requestAnimationFrame(restaurarPosicionVentas);
  } else {
    window.addEventListener("load", function () {
      requestAnimationFrame(restaurarPosicionVentas);
    });
  }

  // SRS (abonos): modal propio para registrar abonos a deudas vinculadas.
  var modalAbono = document.getElementById("modal-abono");
  var abonoValor = document.getElementById("modal-abono-valor");
  var abonoError = document.getElementById("modal-abono-error");
  var abonoDeuda = document.getElementById("modal-abono-deuda");
  var idDeudaAbono = null;
  var enviandoAbono = false;

  function cerrarModalAbono() {
    if (modalAbono) {
      modalAbono.hidden = true;
    }
    idDeudaAbono = null;
  }

  function abrirModalAbono(boton) {
    if (!modalAbono) {
      return;
    }
    // El botón vive dentro del modal de edición; si se deja abierto, su fondo
    // intercepta los clics del modal de abono. Se cierra antes de mostrarlo.
    var detalles = boton.closest("details");
    if (detalles) {
      detalles.open = false;
    }
    idDeudaAbono = boton.getAttribute("data-id-deuda");
    if (!idDeudaAbono) {
      return;
    }
    if (abonoDeuda) {
      abonoDeuda.textContent = boton.getAttribute("data-deuda") || "tu deuda";
    }
    if (abonoValor) {
      abonoValor.value = "";
      abonoValor.focus();
    }
    if (abonoError) {
      abonoError.hidden = true;
      abonoError.textContent = "";
    }
    modalAbono.hidden = false;
  }

  function registrarAbono(aplicaCuota, boton) {
    if (!idDeudaAbono || enviandoAbono) {
      return;
    }
    var valor = abonoValor ? abonoValor.value.trim() : "";
    if (!valor) {
      if (abonoError) {
        abonoError.textContent = "Digita el valor que deseas abonar.";
        abonoError.hidden = false;
      }
      if (abonoValor) {
        abonoValor.focus();
      }
      return;
    }
    enviandoAbono = true;
    var textoOriginal = boton.textContent;
    boton.disabled = true;
    boton.textContent = "Abonando...";
    var datos = new FormData();
    datos.append("valor", valor);
    if (aplicaCuota) {
      datos.append("aplica_cuota", "1");
    }
    fetch("/api/deudas/" + encodeURIComponent(idDeudaAbono) + "/abono", {
      method: "POST",
      body: datos,
    })
      .then(function (respuesta) {
        return respuesta.json().then(function (cuerpo) {
          return { ok: respuesta.ok && cuerpo.ok, detalle: cuerpo.detail };
        });
      })
      .then(function (resultado) {
        if (!resultado.ok) {
          throw new Error(resultado.detalle || "No se pudo registrar el abono.");
        }
        window.recargarManteniendoScroll();
      })
      .catch(function (error) {
        if (abonoError) {
          abonoError.textContent = limpiarMensajeError(error.message);
          abonoError.hidden = false;
        }
        boton.disabled = false;
        boton.textContent = textoOriginal;
      })
      .finally(function () {
        enviandoAbono = false;
      });
  }

  document.querySelectorAll("[data-abrir-abono]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      abrirModalAbono(boton);
    });
  });

  if (modalAbono) {
    var cancelarAbono = modalAbono.querySelector("[data-abono-cancelar]");
    if (cancelarAbono) {
      cancelarAbono.addEventListener("click", cerrarModalAbono);
    }
    var abonoSolo = modalAbono.querySelector("[data-abono-solo]");
    if (abonoSolo) {
      abonoSolo.addEventListener("click", function () { registrarAbono(false, abonoSolo); });
    }
    var abonoConCuota = modalAbono.querySelector("[data-abono-cuota]");
    if (abonoConCuota) {
      abonoConCuota.addEventListener("click", function () { registrarAbono(true, abonoConCuota); });
    }
    modalAbono.addEventListener("click", function (evento) {
      if (evento.target === modalAbono) {
        cerrarModalAbono();
      }
    });
  }
})();

/* SRS v4.35: modal de la X en gastos fijos normales (omitir 10 días o eliminar). */
(function () {
  var modal = document.getElementById("modal-omitir-gasto");
  if (!modal) return;

  var cuerpo = document.getElementById("modal-omitir-gasto-detalle");
  var error = document.getElementById("modal-omitir-gasto-error");
  var idGasto = null;
  var origen = "";
  var esMeta = false;
  var AVISO_META =
    "No puedes eliminar una meta desde gastos fijos, debes hacerlo en el módulo de registro de metas.";

  function configurarEliminar() {
    var eliminar = modal.querySelector("[data-eliminar-confirmar]");
    if (!eliminar) return;
    eliminar.classList.toggle("boton--deshabilitado", esMeta);
    eliminar.setAttribute("aria-disabled", esMeta ? "true" : "false");
    eliminar.title = esMeta ? AVISO_META : "Eliminar gasto fijo";
  }

  function cerrar() {
    modal.hidden = true;
    idGasto = null;
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest("[data-omitir-gasto]");
    if (!boton) return;
    evento.preventDefault();
    idGasto = boton.getAttribute("data-id-gasto");
    origen = boton.getAttribute("data-origen") || "";
    esMeta = boton.getAttribute("data-es-meta") === "1";
    configurarEliminar();
    if (cuerpo) {
      cuerpo.textContent = boton.getAttribute("data-descripcion") || "Este gasto fijo";
    }
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
    var detalles = boton.closest("details");
    if (detalles) {
      detalles.open = false;
    }
    // Si hay un dialog nativo abierto, el modal debe vivir dentro de él para
    // heredar su capa superior.
    var dialogo = document.querySelector("dialog[open]");
    if (dialogo && modal.parentElement !== dialogo) {
      dialogo.appendChild(modal);
    }
    modal.hidden = false;
  });

  function accion(ruta, usarOrigen) {
    if (!idGasto) return;
    var datos = new FormData();
    if (usarOrigen) {
      datos.append("origen", origen);
    }
    fetch(ruta, { method: "POST", body: datos })
      .then(function (respuesta) {
        return respuesta.json().then(function (cuerpoJson) {
          return { ok: respuesta.ok && cuerpoJson.ok !== false, detalle: cuerpoJson.detail };
        });
      })
      .then(function (resultado) {
        if (!resultado.ok) {
          throw new Error(resultado.detalle || "No se pudo completar la acción.");
        }
        window.recargarManteniendoScroll();
      })
      .catch(function (errorCapturado) {
        if (error) {
          error.textContent = errorCapturado.message;
          error.hidden = false;
        }
      });
  }

  var confirmar = modal.querySelector("[data-omitir-confirmar]");
  if (confirmar) {
    confirmar.addEventListener("click", function () {
      accion("/api/gastos/" + encodeURIComponent(idGasto) + "/omitir", false);
    });
  }
  var eliminar = modal.querySelector("[data-eliminar-confirmar]");
  if (eliminar) {
    eliminar.addEventListener("click", function () {
      if (esMeta) {
        // El aviso tiene z-index superior al modal de la X, así que puede
        // mostrarse sin cerrarlo: el usuario sigue viendo sus otras opciones.
        if (typeof window.mostrarAvisoApp === "function") {
          window.mostrarAvisoApp(AVISO_META);
        }
        return;
      }
      // Eliminar devuelve una redirección HTML, no JSON: se envía como
      // formulario nativo para que el navegador navegue y se guarde el scroll.
      var formulario = document.createElement("form");
      formulario.method = "post";
      formulario.action = "/gastos/" + encodeURIComponent(idGasto) + "/eliminar";
      var campoOrigen = document.createElement("input");
      campoOrigen.type = "hidden";
      campoOrigen.name = "origen";
      campoOrigen.value = origen;
      formulario.appendChild(campoOrigen);
      document.body.appendChild(formulario);
      // `form.submit()` no dispara el evento submit: se guarda la posición
      // explícitamente antes de navegar. El cierre va después.
      if (typeof window.guardarScrollApp === "function") {
        window.guardarScrollApp();
      }
      formulario.submit();
      cerrar();
    });
  }
  var cancelar = modal.querySelector("[data-omitir-cancelar]");
  if (cancelar) {
    cancelar.addEventListener("click", cerrar);
  }
})();

/* SRS v4.37: botón Habilitar en ítems omitidos/inhabilitados. */
(function () {
  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest("[data-habilitar-gasto]");
    if (!boton || boton.dataset.enviando === "1") return;
    evento.preventDefault();
    // Se guarda antes de cambiar la etiqueta del botón, porque ese cambio puede
    // reacomodar la fila y desplazar la vista antes de la recarga.
    if (typeof window.guardarScrollApp === "function") {
      window.guardarScrollApp();
    }
    boton.dataset.enviando = "1";
    var id = boton.getAttribute("data-id-gasto");
    var texto = boton.textContent;
    boton.textContent = "Habilitando...";
    boton.style.pointerEvents = "none";
    fetch("/api/gastos/" + encodeURIComponent(id) + "/habilitar", {
      method: "POST",
    })
      .then(function (respuesta) {
        return respuesta.json().then(function (cuerpo) {
          return { ok: respuesta.ok && cuerpo.ok !== false, detalle: cuerpo.detail };
        });
      })
      .then(function (resultado) {
        if (!resultado.ok) {
          throw new Error(resultado.detalle || "No se pudo habilitar el gasto.");
        }
        window.recargarManteniendoScroll(true);
      })
      .catch(function (errorCapturado) {
        boton.textContent = texto;
        if (typeof window.mostrarAvisoApp === "function") {
          window.mostrarAvisoApp(errorCapturado.message);
        }
      })
      .finally(function () {
        boton.dataset.enviando = "0";
        boton.style.pointerEvents = "";
      });
  });
})();

/* SRS v4.28: abonos libres y acumulables a metas de ahorro. */
(function () {
  var modal = document.getElementById("modal-abono-meta");
  if (!modal) return;

  var campo = document.getElementById("modal-abono-meta-valor");
  var error = document.getElementById("modal-abono-meta-error");
  var nombre = document.getElementById("modal-abono-meta-nombre");
  var idGasto = null;
  var enviando = false;

  function cerrar() {
    modal.hidden = true;
    idGasto = null;
  }

  function abrir(boton) {
    idGasto = boton.getAttribute("data-id-gasto");
    if (nombre) {
      nombre.textContent = boton.getAttribute("data-meta") || "tu meta";
    }
    if (campo) {
      campo.value = "";
      campo.focus();
    }
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
    var detalles = boton.closest("details");
    if (detalles) {
      detalles.open = false;
    }
    modal.hidden = false;
  }

  function registrar() {
    if (!idGasto || enviando) return;
    var valor = campo ? campo.value.trim() : "";
    if (!valor) {
      if (error) {
        error.textContent = "Digita el valor que deseas abonar.";
        error.hidden = false;
      }
      return;
    }
    enviando = true;
    var datos = new FormData();
    datos.append("valor", valor);
    fetch("/api/gastos/" + encodeURIComponent(idGasto) + "/abono-meta", {
      method: "POST",
      body: datos,
    })
      .then(function (respuesta) {
        return respuesta.json().then(function (cuerpo) {
          return { ok: respuesta.ok && cuerpo.ok, detalle: cuerpo.detail };
        });
      })
      .then(function (resultado) {
        if (!resultado.ok) {
          throw new Error(resultado.detalle || "No se pudo registrar el abono.");
        }
        window.recargarManteniendoScroll();
      })
      .catch(function (errorCapturado) {
        if (error) {
          var mensaje = errorCapturado.message;
          if (typeof window.limpiarMensajeError === "function") {
            mensaje = window.limpiarMensajeError(mensaje);
          }
          error.textContent = mensaje;
          error.hidden = false;
        }
      })
      .finally(function () {
        enviando = false;
      });
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest("[data-abrir-abono-meta]");
    if (boton) {
      abrir(boton);
    }
  });

  var cancelar = modal.querySelector("[data-abono-meta-cancelar]");
  if (cancelar) {
    cancelar.addEventListener("click", cerrar);
  }
  var confirmar = modal.querySelector("[data-abono-meta-confirmar]");
  if (confirmar) {
    confirmar.addEventListener("click", registrar);
  }
  modal.addEventListener("click", function (evento) {
    if (evento.target === modal) {
      cerrar();
    }
  });
})();

/* SRS v4.28: conservar la posición vertical al abrir y cerrar cualquier modal
   o confirmación, sin saltar a lo alto ni abajo del documento. */
(function () {
  var guardado = null;
  var antesClic = null;

  function hayModal() {
    return !!document.querySelector(
      ".edicion-gasto--modal[open], .app-modal:not([hidden]), .modal-centrado[open], dialog[open]"
    );
  }

  // Fase de captura: la posición se toma antes de que el manejador abra el modal
  // y de que un `focus()` pueda desplazar la página.
  document.addEventListener(
    "click",
    function () {
      if (!hayModal()) {
        antesClic = {
          x: window.scrollX || window.pageXOffset || 0,
          y: window.scrollY || window.pageYOffset || 0,
        };
      }
    },
    true
  );

  var observador = new MutationObserver(function () {
    if (hayModal()) {
      if (guardado === null) {
        guardado = antesClic || {
          x: window.scrollX || window.pageXOffset || 0,
          y: window.scrollY || window.pageYOffset || 0,
        };
        antesClic = null;
      }
    } else if (guardado !== null) {
      var destino = guardado;
      guardado = null;
      requestAnimationFrame(function () {
        window.scrollTo({ left: destino.x, top: destino.y, behavior: "instant" });
      });
    }
  });

  observador.observe(document.body, {
    attributes: true,
    subtree: true,
    attributeFilter: ["open", "hidden"]
  });
})();

/* SRS v4.26: checks de gastos fijos con actualización optimista. El ✔ cambia
   al instante; el guardado va en segundo plano y solo se revierte si falla. */
(function () {
  function aplicarEstado(formulario, pagado) {
    var boton = formulario.querySelector('button[type="submit"]');
    var fila = formulario.closest("li.lista-gastos__item");
    if (!boton) return;
    if (pagado) {
      boton.classList.remove("boton-circular--check");
      boton.classList.add("boton-circular--marcado");
      boton.setAttribute("aria-label", "Desmarcar el pago");
      boton.setAttribute("title", "Pagado · pulsa para desmarcar");
    } else {
      boton.classList.add("boton-circular--check");
      boton.classList.remove("boton-circular--marcado");
      boton.setAttribute("aria-label", "Marcar como pagado");
      boton.setAttribute("title", "Marcar como pagado");
    }
    if (fila) {
      if (pagado) {
        fila.classList.add("lista-gastos__item--pagado");
      } else {
        fila.classList.remove("lista-gastos__item--pagado");
      }
    }
  }

  document.querySelectorAll("form[data-check-gasto]").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      evento.preventDefault();
      var boton = formulario.querySelector('button[type="submit"]');
      if (!boton || boton.dataset.enviando === "1") return;

      var idGasto = formulario.getAttribute("data-id-gasto");
      var accion = formulario.getAttribute("data-accion");
      var marcando = accion === "marcar";
      var accionAnterior = accion;
      var actionAnterior = formulario.getAttribute("action");
      var siguiente = marcando ? "desmarcar" : "marcar";

      // Cambio visual inmediato (0 ms) y state local coherente para el próximo clic.
      aplicarEstado(formulario, marcando);
      formulario.setAttribute("data-accion", siguiente);
      formulario.setAttribute(
        "action",
        "/gastos/" + encodeURIComponent(idGasto) + (marcando ? "/no-pagado" : "/pagado")
      );

      boton.dataset.enviando = "1";
      boton.style.pointerEvents = "none";

      var ruta = "/api/gastos/" + encodeURIComponent(idGasto) +
        (marcando ? "/pagado" : "/no-pagado");
      fetch(ruta, { method: "POST", headers: { "Accept": "application/json" } })
        .then(function (respuesta) {
          return respuesta.json().then(function (cuerpo) {
            return { ok: respuesta.ok && cuerpo.ok, detalle: cuerpo.detail };
          });
        })
        .then(function (resultado) {
          if (!resultado.ok) {
            throw new Error(resultado.detalle || "No se pudo actualizar el pago.");
          }
        })
        .catch(function () {
          aplicarEstado(formulario, !marcando);
          formulario.setAttribute("data-accion", accionAnterior);
          formulario.setAttribute("action", actionAnterior);
          if (typeof window.mostrarAvisoApp === "function") {
            window.mostrarAvisoApp("No se pudo actualizar el pago. Inténtalo de nuevo.");
          }
        })
        .finally(function () {
          boton.dataset.enviando = "0";
          boton.style.pointerEvents = "";
        });
    });
  });

  /**
   * Evita que el gesto táctil se encadene a la página en las tablas de analítica
   * que desplazan en dos ejes (productos y último costo). Solo cancela el gesto
   * cuando el dedo ya está en un borde y el movimiento es dominante en ese eje;
   * el desplazamiento horizontal de columnas y el vertical de filas siguen activos.
   */
  function confinarGesto(caja) {
    var inicioX = null;
    var inicioY = null;
    var empiezaEnCabecera = false;
    caja.addEventListener("touchstart", function (evento) {
      if (!window.matchMedia("(max-width: 767px)").matches || evento.touches.length !== 1) {
        inicioX = inicioY = null;
        return;
      }
      inicioX = evento.touches[0].clientX;
      inicioY = evento.touches[0].clientY;
      var objetivo = evento.target instanceof Element ? evento.target : null;
      empiezaEnCabecera = !!(objetivo && objetivo.closest("thead"));
    }, { passive: true });

    caja.addEventListener("touchmove", function (evento) {
      if (inicioX === null || evento.touches.length !== 1) {
        return;
      }
      var dx = evento.touches[0].clientX - inicioX;
      var dy = evento.touches[0].clientY - inicioY;
      var horizontal = Math.abs(dx) > Math.abs(dy);
      // La cabecera no participa del desplazamiento vertical: solo se mueve
      // de forma horizontal. El scroll vertical nace en la fila 2 en adelante.
      if (empiezaEnCabecera && !horizontal) {
        evento.preventDefault();
        return;
      }
      var enBorde = horizontal
        ? (dx < 0
          ? caja.scrollLeft + caja.clientWidth >= caja.scrollWidth - 1
          : caja.scrollLeft <= 0)
        : (dy < 0
          ? caja.scrollTop + caja.clientHeight >= caja.scrollHeight - 1
          : caja.scrollTop <= 0);
      if (enBorde) {
        evento.preventDefault();
      }
    }, { passive: false });

    function terminarGesto() {
      inicioX = inicioY = null;
      empiezaEnCabecera = false;
    }
    caja.addEventListener("touchend", terminarGesto, { passive: true });
    caja.addEventListener("touchcancel", terminarGesto, { passive: true });
  }

  document
    .querySelectorAll(
      ".tabla-contenedor--productos, .tabla-contenedor--costos, " +
        ".tabla-contenedor--ordenes, .tabla-contenedor--migracion, " +
        ".tabla-contenedor--pendientes, .ordenes-moviles--ordenes"
    )
    .forEach(confinarGesto);
})();
