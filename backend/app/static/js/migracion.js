/**
 * Comportamiento de la pestaña «Migración de Cartera» de OLB BYTE.
 *
 * Responsabilidad
 * ---------------
 * - Reutilizar el panel de producto de Registro de venta (categoría, nombre,
 *   cantidad, costo, precio y garantía), con todos los campos opcionales.
 * - Pasar cada producto guardado a la tabla como campos ocultos, para que el
 *   servidor reciba los mismos nombres que en una venta normal.
 * - Abrir WhatsApp directamente desde «Pegar Numero», sin libreta de contactos
 *   ni portapapeles (SRS Migración §4).
 *
 * Toda la validación y los cálculos de negocio viven en el servidor.
 */

(function () {
  "use strict";

  var formulario = document.querySelector("[data-migracion-form]");
  if (!formulario) {
    return;
  }

  var lista = formulario.querySelector("[data-lista-productos]");
  var plantilla = formulario.querySelector("[data-plantilla-producto]");
  var mensajeVacio = formulario.querySelector("[data-lista-vacia]");
  var botonAgregar = formulario.querySelector("[data-agregar-producto]");
  var botonGuardar = formulario.querySelector("[data-guardar-producto]");
  var panel = formulario.querySelector("[data-panel-producto]");
  var errorPanel = formulario.querySelector("[data-error-panel]");
  var estadoPanel = formulario.querySelector("[data-estado-panel]");
  var subtotalPanel = formulario.querySelector("[data-subtotal-panel]");
  var campoTelefono = formulario.querySelector("[data-cliente-telefono]");
  var botonNumero = formulario.querySelector("[data-pegar-numero]");
  var campoGarantia = panel ? panel.querySelector('[data-campo-panel="garantia_meses"]') : null;
  var garantiaDefecto = campoGarantia ? campoGarantia.value : "0";

  /**
   * Lee los campos del panel de producto.
   *
   * @returns {Object} Valores escritos, con claves de `data-campo-panel`.
   */
  function leerPanel() {
    var valores = {};
    if (!panel) {
      return valores;
    }
    panel.querySelectorAll("[data-campo-panel]").forEach(function (campo) {
      valores[campo.getAttribute("data-campo-panel")] = campo.value.trim();
    });
    return valores;
  }

  /**
   * Indica si el usuario escribió algo en el panel (la garantía y la cantidad
   * traen valores por defecto y por sí solas no cuentan como detalle).
   *
   * @returns {boolean} `true` si hay datos de producto.
   */
  function hayDatosEnPanel() {
    var valores = leerPanel();
    return !!(
      valores.producto_nombre ||
      valores.categoria ||
      valores.precio_unitario ||
      valores.costo_unitario ||
      (valores.cantidad && valores.cantidad !== "1")
    );
  }

  /**
   * Muestra u oculta el error del panel.
   *
   * @param {string} texto Mensaje; vacío lo oculta.
   */
  function mostrarError(texto) {
    if (!errorPanel) {
      return;
    }
    errorPanel.textContent = texto;
    errorPanel.hidden = !texto;
  }

  /**
   * Actualiza el subtotal mostrado en el panel.
   */
  function actualizarSubtotal() {
    if (!subtotalPanel) {
      return;
    }
    var valores = leerPanel();
    var cantidad = parseInt(valores.cantidad, 10) || 0;
    var precio = Number(String(valores.precio_unitario || "0").replace(/[^\d.-]/g, "")) || 0;
    var total = cantidad * precio;
    subtotalPanel.textContent = "$" + Math.round(total).toLocaleString("es-CO");
  }

  /**
   * Escribe un valor en la fila de la tabla (vista y campo oculto).
   *
   * @param {HTMLElement} fila Fila destino.
   * @param {string} nombre Nombre del campo.
   * @param {string} valor Valor a escribir.
   */
  function escribirEnFila(fila, nombre, valor) {
    var oculto = fila.querySelector('input[type="hidden"][name="' + nombre + '"]');
    if (oculto) {
      oculto.value = valor;
    }
    var vista = fila.querySelector('[data-vista="' + nombre + '"]');
    if (vista) {
      vista.textContent = valor;
    }
  }

  /**
   * Actualiza el aviso de tabla vacía según las filas visibles.
   */
  function actualizarVacia() {
    if (!mensajeVacio || !lista) {
      return;
    }
    mensajeVacio.hidden = lista.querySelectorAll("[data-fila-producto]").length > 0;
  }

  function mostrarEstado(texto) {
    if (!estadoPanel) {
      return;
    }
    estadoPanel.textContent = texto;
    estadoPanel.hidden = !texto;
  }

  /**
   * Guarda el producto del panel como una fila nueva de la tabla. Con los campos
   * vacíos guarda una fila de saldo global (sin precio inventado).
   *
   * @returns {boolean} `true` si se agregó una fila.
   */
  function guardarProducto() {
    if (!lista || !plantilla) {
      return false;
    }
    if (!hayDatosEnPanel()) {
      var yaEsta = Array.prototype.some.call(
        lista.querySelectorAll('input[type="hidden"][name="producto_nombre"]'),
        function (campo) { return campo.value === "Saldo pendiente migrado"; }
      );
      if (yaEsta) {
        mostrarEstado("La fila de saldo global ya está en la lista.");
        return true;
      }
      var filaSaldo = plantilla.content.cloneNode(true).querySelector("[data-fila-producto]");
      escribirEnFila(filaSaldo, "producto_nombre", "Saldo pendiente migrado");
      escribirEnFila(filaSaldo, "categoria", "");
      escribirEnFila(filaSaldo, "cantidad", "1");
      escribirEnFila(filaSaldo, "costo_unitario", "0");
      escribirEnFila(filaSaldo, "precio_unitario", "0");
      escribirEnFila(filaSaldo, "garantia_meses", "0");
      lista.appendChild(filaSaldo);
      mostrarError("");
      limpiarPanel();
      mostrarEstado("Saldo global agregado. Puedes cargar solo el valor total.");
      actualizarVacia();
      return true;
    }
    var valores = leerPanel();
    var nombre = valores.producto_nombre || "(sin nombre)";
    var precio = valores.precio_unitario || "0";
    var cantidad = parseInt(valores.cantidad, 10) || 0;
    if (cantidad <= 0) {
      mostrarError("La cantidad debe ser mayor que cero.");
      return false;
    }
    if (!lista || !plantilla) {
      return false;
    }
    var fila = plantilla.content.cloneNode(true).querySelector("[data-fila-producto]");
    escribirEnFila(fila, "producto_nombre", nombre);
    escribirEnFila(fila, "categoria", valores.categoria || "");
    escribirEnFila(fila, "cantidad", String(cantidad));
    escribirEnFila(fila, "costo_unitario", valores.costo_unitario || "0");
    escribirEnFila(fila, "precio_unitario", precio);
    escribirEnFila(fila, "garantia_meses", valores.garantia_meses || "0");
    lista.appendChild(fila);
    mostrarError("");
    mostrarEstado("");
    limpiarPanel();
    actualizarVacia();
    return true;
  }

  /**
   * Deja el panel listo para otro producto.
   */
  function limpiarPanel() {
    if (!panel) {
      return;
    }
    mostrarEstado("");
    panel.querySelectorAll("[data-campo-panel]").forEach(function (campo) {
      var nombre = campo.getAttribute("data-campo-panel");
      if (nombre === "cantidad") {
        campo.value = "1";
      } else if (nombre === "garantia_meses") {
        campo.value = garantiaDefecto;
      } else {
        campo.value = "";
      }
    });
    actualizarSubtotal();
  }

  /**
   * Carga una fila existente en el panel para editarla.
   *
   * @param {HTMLElement} fila Fila a editar.
   */
  function editarFila(fila) {
    ["producto_nombre", "categoria", "cantidad", "costo_unitario", "precio_unitario", "garantia_meses"].forEach(
      function (nombre) {
        var oculto = fila.querySelector('input[type="hidden"][name="' + nombre + '"]');
        var campo = panel && panel.querySelector('[data-campo-panel="' + nombre + '"]');
        if (oculto && campo) {
          campo.value = oculto.value;
        }
      }
    );
    fila.parentNode.removeChild(fila);
    actualizarVacia();
    actualizarSubtotal();
  }

  if (botonGuardar) {
    botonGuardar.addEventListener("click", guardarProducto);
  }

  if (botonAgregar) {
    botonAgregar.addEventListener("click", function () {
      if (!guardarProducto()) {
        return;
      }
      limpiarPanel();
      if (panel) {
        var nombre = panel.querySelector('[data-campo-panel="producto_nombre"]');
        if (nombre) {
          nombre.focus();
        }
      }
    });
  }

  if (panel) {
    panel.addEventListener("input", actualizarSubtotal);
    panel.addEventListener("change", actualizarSubtotal);
  }

  if (lista) {
    lista.addEventListener("click", function (evento) {
      var objetivo = evento.target instanceof Element ? evento.target : null;
      if (!objetivo) {
        return;
      }
      var fila = objetivo.closest("[data-fila-producto]");
      if (!fila) {
        return;
      }
      if (objetivo.closest("[data-eliminar-producto]")) {
        fila.parentNode.removeChild(fila);
        actualizarVacia();
        return;
      }
      if (objetivo.closest("[data-editar-fila]")) {
        editarFila(fila);
      }
    });
  }

  // Si el usuario dejó datos en el panel, se guardan antes de enviar el formulario.
  formulario.addEventListener("submit", function (evento) {
    if (hayDatosEnPanel() && !guardarProducto()) {
      evento.preventDefault();
      if (panel) {
        panel.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  });

  /** Normaliza el celular mientras se escribe o se pega. */
  function normalizarTelefono(texto) {
    var digitos = String(texto || "").replace(/\D/g, "");
    if (digitos.length === 12 && digitos.indexOf("57") === 0) {
      digitos = digitos.slice(2);
    }
    return digitos.slice(0, 10);
  }

  if (campoTelefono) {
    campoTelefono.addEventListener("input", function () {
      campoTelefono.value = normalizarTelefono(campoTelefono.value);
    });
    campoTelefono.addEventListener("blur", function () {
      campoTelefono.value = normalizarTelefono(campoTelefono.value);
    });
  }

  /** Abre WhatsApp para que el usuario copie el número del contacto. */
  function abrirWhatsappNumero() {
    var texto = encodeURIComponent("Hola");
    if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
      window.location.href = "whatsapp://send?text=" + texto;
    } else {
      window.open(
        "https://wa.me/?text=" + texto,
        "_blank",
        "noopener,noreferrer"
      );
    }
  }

  if (botonNumero) {
    botonNumero.addEventListener("click", abrirWhatsappNumero);
  }

  actualizarSubtotal();
  actualizarVacia();
})();
