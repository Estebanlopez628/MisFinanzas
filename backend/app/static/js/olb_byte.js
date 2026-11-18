/**
 * Formulario de venta de OLB_BYTE: producto por producto, con detalle y edición.
 *
 * Responsabilidad
 * ---------------
 * - Calcular el subtotal del producto que se está escribiendo.
 * - Agregar el producto a la tabla de detalle («+ Agregar otro producto» o Enter).
 * - Eliminar un producto de la tabla o corregirlo en el cuadro «Actualizar producto»,
 *   que se cierra con Cancelar sin cambiar nada.
 * - Mostrar totales de la orden: venta, costo al proveedor y ganancia.
 * - Completar el celular al elegir un cliente existente.
 * - Usar la Contact Picker API cuando el navegador la ofrece; si no, explicar por qué
 *   no está disponible en lugar de mostrar un botón que no responde.
 *
 * Los productos viajan al servidor en campos ocultos de cada fila. Ninguna regla de
 * negocio vive aquí: el servidor recalcula y valida todo al registrar la venta.
 */

(function () {
  "use strict";

  var formulario = document.querySelector("[data-venta-form]");
  if (!formulario) {
    return;
  }

  var tablaFilas = formulario.querySelector("[data-lista-productos]");
  var mensajeVacia = formulario.querySelector("[data-lista-vacia]");
  var plantilla = document.querySelector("[data-plantilla-fila]");
  var panel = formulario.querySelector(".bloque-producto");
  var errorPanel = formulario.querySelector("[data-error-panel]");
  var subtotalPanel = formulario.querySelector("[data-subtotal-panel]");
  var dialogo = document.querySelector("[data-dialogo-edicion]");
  var errorEdicion = document.querySelector("[data-error-edicion]");
  var filaEditando = null;

  var campoNombre = formulario.querySelector("[data-cliente-nombre]");
  var campoTelefono = formulario.querySelector("[data-cliente-telefono]");
  var listaClientes = document.getElementById("clientes-lista");

  /**
   * Convierte un monto escrito en formato colombiano («50.000») a número.
   *
   * @param {string} texto Monto escrito.
   * @returns {number} Valor numérico; cero si no es válido.
   */
  function numero(texto) {
    var limpio = String(texto || "").trim().replace(/\./g, "").replace(/,/g, ".");
    var valor = parseFloat(limpio);
    return isNaN(valor) ? 0 : valor;
  }

  /**
   * Da formato de pesos sin centavos.
   *
   * @param {number} valor Monto.
   * @returns {string} Texto como «$50.000».
   */
  function pesos(valor) {
    return "$" + Math.round(valor).toLocaleString("es-CO");
  }

  /**
   * Deja solo los dígitos del celular, quitando el indicativo 57 si viene.
   *
   * @param {string} texto Número tal como llegó.
   * @returns {string} Dígitos del celular.
   */
  function normalizarTelefono(texto) {
    var digitos = String(texto || "").replace(/\D/g, "");
    if (digitos.length === 12 && digitos.indexOf("57") === 0) {
      digitos = digitos.slice(2);
    }
    return digitos;
  }

  /**
   * Lee los campos del panel de producto.
   *
   * @returns {Object} Valores tal como se escriben.
   */
  function valoresPanel() {
    return leerCampos(panel, "data-campo-panel");
  }

  /**
   * Lee los campos del cuadro de edición.
   *
   * @returns {Object} Valores tal como se escriben.
   */
  function valoresEdicion() {
    return leerCampos(dialogo, "data-campo-edicion");
  }

  /**
   * Lee todos los campos que llevan el atributo indicado dentro de un contenedor.
   *
   * @param {HTMLElement} contenedor Elemento donde buscar.
   * @param {string} atributo Atributo que marca los campos.
   * @returns {Object} Mapa de nombre de campo a valor.
   */
  function leerCampos(contenedor, atributo) {
    var resultado = {};
    var campos = contenedor.querySelectorAll("[" + atributo + "]");
    for (var i = 0; i < campos.length; i += 1) {
      resultado[campos[i].getAttribute(atributo)] = campos[i].value;
    }
    return resultado;
  }

  /**
   * Escribe los valores en el panel de producto.
   *
   * @param {Object} valores Valores a mostrar; los faltantes se dejan en su valor por defecto.
   */
  function escribirPanel(valores) {
    var campos = panel.querySelectorAll("[data-campo-panel]");
    for (var i = 0; i < campos.length; i += 1) {
      var nombre = campos[i].getAttribute("data-campo-panel");
      campos[i].value = valores[nombre] !== undefined ? valores[nombre] : campos[i].defaultValue;
    }
  }

  /**
   * Escribe los valores en el cuadro de edición.
   *
   * @param {Object} valores Valores de la fila que se edita.
   */
  function escribirEdicion(valores) {
    var campos = dialogo.querySelectorAll("[data-campo-edicion]");
    for (var i = 0; i < campos.length; i += 1) {
      campos[i].value = valores[campos[i].getAttribute("data-campo-edicion")] || "";
    }
  }

  /**
   * Revisa un producto antes de agregarlo o actualizarlo.
   *
   * @param {Object} valores Valores escritos.
   * @returns {string} Mensaje de error, o cadena vacía si el producto es válido.
   */
  function validarProducto(valores) {
    if (!valores.producto_nombre || !valores.producto_nombre.trim()) {
      return "Escribe el nombre del producto.";
    }
    var cantidad = parseInt(valores.cantidad, 10);
    if (!cantidad || cantidad < 1) {
      return "La cantidad debe ser de al menos 1.";
    }
    if (!valores.precio_unitario || !valores.precio_unitario.trim()) {
      return "Escribe el precio de venta de " + valores.producto_nombre.trim() + ".";
    }
    if (numero(valores.precio_unitario) < 0 || numero(valores.costo_unitario) < 0) {
      return "El precio y el costo no pueden ser negativos.";
    }
    return "";
  }

  /**
   * Muestra u oculta un mensaje de error de un bloque.
   *
   * @param {HTMLElement} elemento Contenedor del mensaje.
   * @param {string} mensaje Texto del error; vacío lo oculta.
   */
  function mostrarError(elemento, mensaje) {
    if (!elemento) {
      return;
    }
    elemento.textContent = mensaje;
    elemento.hidden = !mensaje;
  }

  /**
   * Calcula el subtotal del producto que se está escribiendo.
   */
  function actualizarSubtotalPanel() {
    var valores = valoresPanel();
    subtotalPanel.textContent = pesos(numero(valores.precio_unitario) * Math.max(parseInt(valores.cantidad, 10) || 0, 0));
  }

  /**
   * Lee los valores guardados en los campos ocultos de una fila.
   *
   * @param {HTMLElement} fila Fila de la tabla.
   * @returns {Object} Valores del producto.
   */
  function leerFila(fila) {
    var valores = {};
    var ocultos = fila.querySelectorAll("input[type='hidden']");
    for (var i = 0; i < ocultos.length; i += 1) {
      valores[ocultos[i].name] = ocultos[i].value;
    }
    return valores;
  }

  /**
   * Guarda los valores en los campos ocultos de una fila y actualiza su vista.
   *
   * @param {HTMLElement} fila Fila a escribir.
   * @param {Object} valores Valores del producto.
   */
  function escribirFila(fila, valores) {
    var ocultos = fila.querySelectorAll("input[type='hidden']");
    for (var i = 0; i < ocultos.length; i += 1) {
      ocultos[i].value = valores[ocultos[i].name] !== undefined ? valores[ocultos[i].name] : "";
    }
    var vistas = fila.querySelectorAll("[data-vista]");
    for (var j = 0; j < vistas.length; j += 1) {
      var clave = vistas[j].getAttribute("data-vista");
      var texto = valores[clave];
      if (clave === "garantia_meses") {
        texto = (valores.garantia_meses || "0") + " mes(es)";
      }
      vistas[j].textContent = texto || "";
    }
  }

  /**
   * Cuenta las filas de producto y muestra el aviso de tabla vacía si corresponde.
   */
  function actualizarVacia() {
    var filas = tablaFilas.querySelectorAll("[data-fila-producto]");
    mensajeVacia.hidden = filas.length > 0;
  }

  /**
   * Recalcula los totales de la orden a partir de las filas de la tabla.
   */
  function recalcular() {
    var total = 0;
    var costo = 0;
    var ganancia = 0;
    var filas = tablaFilas.querySelectorAll("[data-fila-producto]");
    for (var i = 0; i < filas.length; i += 1) {
      var valores = leerFila(filas[i]);
      var cantidad = Math.max(parseInt(valores.cantidad, 10) || 0, 0);
      var precio = numero(valores.precio_unitario);
      var costoUnitario = numero(valores.costo_unitario);
      total += precio * cantidad;
      costo += costoUnitario * cantidad;
      ganancia += (precio - costoUnitario) * cantidad;
    }
    formulario.querySelector("[data-total]").textContent = pesos(total);
    formulario.querySelector("[data-total-costo]").textContent = pesos(costo);
    formulario.querySelector("[data-ganancia]").textContent = pesos(ganancia);
    actualizarVacia();
  }

  /**
   * Agrega una fila a la tabla con los valores del producto.
   *
   * @param {Object} valores Valores validados del producto.
   */
  function agregarFila(valores) {
    var fila = plantilla.content.firstElementChild.cloneNode(true);
    escribirFila(fila, valores);
    tablaFilas.appendChild(fila);
  }

  /**
   * Reinicia el panel de producto a sus valores por defecto.
   */
  function limpiarPanel() {
    escribirPanel({});
    actualizarSubtotalPanel();
  }

  /**
   * Agrega el producto del panel a la tabla si es válido.
   *
   * @returns {boolean} `true` si se agregó; `false` si hay un error que mostrar.
   */
  function agregarDesdePanel() {
    var valores = valoresPanel();
    var error = validarProducto(valores);
    mostrarError(errorPanel, error);
    if (error) {
      return false;
    }
    agregarFila(valores);
    limpiarPanel();
    mostrarError(errorPanel, "");
    recalcular();
    return true;
  }

  /**
   * Indica si el usuario empezó a escribir un producto en el panel.
   *
   * @returns {boolean} `true` si hay texto en el nombre, la categoría, el costo o el precio.
   */
  function hayDatosEnPanel() {
    var valores = valoresPanel();
    return Boolean(
      (valores.producto_nombre || "").trim() ||
        (valores.categoria || "").trim() ||
        (valores.costo_unitario || "").trim() ||
        (valores.precio_unitario || "").trim()
    );
  }

  // --------------------------- Panel de producto -------------------------------

  panel.addEventListener("input", actualizarSubtotalPanel);

  panel.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter") {
      // Enter agrega el producto en lugar de enviar la venta a medio escribir.
      evento.preventDefault();
      agregarDesdePanel();
    }
  });

  var botonAgregar = formulario.querySelector("[data-agregar-producto]");
  if (botonAgregar) {
    botonAgregar.addEventListener("click", agregarDesdePanel);
  }

  // Si el usuario escribió un producto y pulsó «Registrar venta» sin agregarlo,
  // se agrega antes de enviar; si el producto no es válido, no se envía la venta.
  formulario.addEventListener("submit", function (evento) {
    if (hayDatosEnPanel() && !agregarDesdePanel()) {
      evento.preventDefault();
      panel.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });

  // ----------------------------- Tabla de productos ----------------------------

  tablaFilas.addEventListener("click", function (evento) {
    var objetivo = evento.target;
    if (!(objetivo instanceof Element)) {
      return;
    }
    var fila = objetivo.closest("[data-fila-producto]");
    if (!fila) {
      return;
    }

    if (objetivo.closest("[data-eliminar-fila]")) {
      fila.parentNode.removeChild(fila);
      recalcular();
      return;
    }

    if (objetivo.closest("[data-editar-fila]")) {
      filaEditando = fila;
      escribirEdicion(leerFila(fila));
      mostrarError(errorEdicion, "");
      if (typeof dialogo.showModal === "function") {
        dialogo.showModal();
      }
    }
  });

  // ------------------------------- Cuadro de edición ---------------------------

  var botonGuardarEdicion = dialogo.querySelector("[data-guardar-edicion]");
  var botonCancelarEdicion = dialogo.querySelector("[data-cancelar-edicion]");

  if (botonGuardarEdicion) {
    botonGuardarEdicion.addEventListener("click", function () {
      var valores = valoresEdicion();
      var error = validarProducto(valores);
      mostrarError(errorEdicion, error);
      if (error || !filaEditando) {
        return;
      }
      escribirFila(filaEditando, valores);
      filaEditando = null;
      dialogo.close();
      recalcular();
    });
  }

  if (botonCancelarEdicion) {
    botonCancelarEdicion.addEventListener("click", function () {
      // Cancelar no cambia la fila: solo cierra el cuadro.
      filaEditando = null;
      dialogo.close();
    });
  }

  // ------------------------------- Cliente y celular ---------------------------

  if (campoNombre && listaClientes && campoTelefono) {
    campoNombre.addEventListener("input", function () {
      var opciones = listaClientes.querySelectorAll("option");
      for (var j = 0; j < opciones.length; j += 1) {
        if (opciones[j].value === campoNombre.value) {
          var telefono = opciones[j].getAttribute("data-telefono");
          if (telefono && !campoTelefono.value.trim()) {
            campoTelefono.value = telefono;
          }
          return;
        }
      }
    });
  }

  if (campoTelefono) {
    campoTelefono.addEventListener("blur", function () {
      campoTelefono.value = normalizarTelefono(campoTelefono.value);
    });
  }

  // La Contact Picker API solo existe en Android con Chrome y en una conexión segura.
  // En otros casos se explica por qué no está disponible en lugar de dejar un botón mudo.
  var nota = formulario.querySelector("[data-nota-contactos]");
  var soportaContactos = "contacts" in navigator && "ContactsManager" in window;
  if (botonContactos() && soportaContactos) {
    botonContactos().hidden = false;
    botonContactos().addEventListener("click", importarContacto);
  } else if (nota) {
    nota.hidden = false;
  }

  /**
   * Devuelve el botón de contactos del formulario.
   *
   * @returns {HTMLElement|null} Botón o `null` si no existe.
   */
  function botonContactos() {
    return formulario.querySelector("[data-contactos]");
  }

  /**
   * Abre la agenda del celular y copia el nombre y el número elegidos.
   */
  function importarContacto() {
    navigator.contacts
      .select(["name", "tel"], { multiple: false })
      .then(function (contactos) {
        if (!contactos || !contactos.length) {
          return;
        }
        var contacto = contactos[0];
        if (contacto.tel && contacto.tel.length && campoTelefono) {
          campoTelefono.value = normalizarTelefono(contacto.tel[0]);
        }
        if (contacto.name && contacto.name.length && campoNombre && !campoNombre.value.trim()) {
          campoNombre.value = contacto.name[0];
        }
      })
      .catch(function (error) {
        if (error && error.name === "AbortError") {
          return;
        }
        if (nota) {
          nota.textContent = "No se pudo abrir Contactos. Escribe el número a mano.";
          nota.hidden = false;
        }
      });
  }

  // ------------------------------- Arranque ------------------------------------

  var filasIniciales = tablaFilas.querySelectorAll("[data-fila-producto]");
  for (var k = 0; k < filasIniciales.length; k += 1) {
    escribirFila(filasIniciales[k], leerFila(filasIniciales[k]));
  }
  actualizarSubtotalPanel();
  recalcular();
})();
