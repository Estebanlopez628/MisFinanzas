/**
 * Formulario de venta de OLB_BYTE: forma de pago, productos guardados y totales.
 *
 * Responsabilidad
 * ---------------
 * - Mostrar los campos de pago según la forma (contado o crédito) y el anticipo.
 * - Guardar un producto en la tabla y bloquear el panel hasta «+ Agregar otro producto».
 * - Editar un producto en el cuadro «Actualizar» y cerrarlo con «Cancelar» sin cambios.
 * - Calcular totales: venta, costo al proveedor y ganancia.
 * - Completar el celular al elegir un cliente existente.
 * - Buscar un contacto en la libreta (Contact Picker) cuando el navegador lo permite;
 *   si no, guardar el número como contacto con una tarjeta de contacto (.vcf).
 *
 * Los productos viajan al servidor en campos ocultos de cada fila. Ninguna regla de
 * negocio vive aquí: el servidor valida y calcula todo al registrar la venta.
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
  var panel = formulario.querySelector("[data-panel-producto]");
  var errorPanel = formulario.querySelector("[data-error-panel]");
  var subtotalPanel = formulario.querySelector("[data-subtotal-panel]");
  var estadoPanel = formulario.querySelector("[data-estado-panel]");
  var botonGuardar = formulario.querySelector("[data-guardar-producto]");
  var botonAgregar = formulario.querySelector("[data-agregar-producto]");
  var dialogo = document.querySelector("[data-dialogo-edicion]");
  var errorEdicion = document.querySelector("[data-error-edicion]");
  var filaEditando = null;

  var campoNombre = formulario.querySelector("[data-cliente-nombre]");
  var campoTelefono = formulario.querySelector("[data-cliente-telefono]");
  var listaClientes = document.getElementById("clientes-lista");

  var formaPago = formulario.querySelector("[data-forma-pago]");
  var metodoPago = formulario.querySelector("[data-metodo-pago]");
  var anticipo = formulario.querySelector("[data-anticipo]");
  var montoAnticipo = formulario.querySelector("[data-monto-anticipo]");
  var metodoAnticipo = formulario.querySelector("[data-metodo-anticipo]");

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
   * Asigna un valor a un `<select>`, conservando los valores históricos.
   *
   * Si el valor guardado no está entre las opciones estándar (por ejemplo, una
   * categoría escrita antes de este catálogo), se agrega como opción temporal
   * para no perder el dato al editar la fila.
   *
   * @param {HTMLSelectElement} campo Selector a escribir.
   * @param {string} valor Valor guardado.
   */
  function fijarValorSelect(campo, valor) {
    var texto = valor === undefined || valor === null ? "" : String(valor);
    var previas = campo.querySelectorAll("option[data-historico]");
    for (var i = 0; i < previas.length; i += 1) {
      previas[i].parentNode.removeChild(previas[i]);
    }
    var existe = false;
    for (var j = 0; j < campo.options.length; j += 1) {
      if (campo.options[j].value === texto) {
        existe = true;
        break;
      }
    }
    if (!existe && texto) {
      var opcion = document.createElement("option");
      opcion.value = texto;
      opcion.textContent = "• " + texto;
      opcion.setAttribute("data-historico", "1");
      campo.appendChild(opcion);
    }
    campo.value = texto;
    if (!texto) {
      campo.selectedIndex = 0;
    }
  }

  /**
   * Escribe los valores en el panel de producto; los faltantes vuelven a su valor por defecto.
   *
   * @param {Object} valores Valores a mostrar.
   */
  function escribirPanel(valores) {
    var campos = panel.querySelectorAll("[data-campo-panel]");
    for (var i = 0; i < campos.length; i += 1) {
      var nombre = campos[i].getAttribute("data-campo-panel");
      if (campos[i].tagName === "SELECT") {
        fijarValorSelect(campos[i], valores[nombre] || "");
      } else {
        campos[i].value = valores[nombre] !== undefined ? valores[nombre] : campos[i].defaultValue;
      }
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
      var valor = valores[campos[i].getAttribute("data-campo-edicion")] || "";
      if (campos[i].tagName === "SELECT") {
        fijarValorSelect(campos[i], valor);
      } else {
        campos[i].value = valor;
      }
    }
  }

  /**
   * Revisa un producto antes de guardarlo o actualizarlo.
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
   * Muestra u oculta un mensaje de error.
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
   * Muestra el subtotal del producto que se está escribiendo.
   */
  function actualizarSubtotalPanel() {
    var valores = leerCampos(panel, "data-campo-panel");
    var cantidad = Math.max(parseInt(valores.cantidad, 10) || 0, 0);
    subtotalPanel.textContent = pesos(numero(valores.precio_unitario) * cantidad);
  }

  /**
   * Indica si el usuario escribió algo en el panel de producto.
   *
   * @returns {boolean} `true` si hay nombre, categoría, costo o precio escritos.
   */
  function hayDatosEnPanel() {
    var valores = leerCampos(panel, "data-campo-panel");
    return Boolean(
      (valores.producto_nombre || "").trim() ||
        (valores.categoria || "").trim() ||
        (valores.costo_unitario || "").trim() ||
        (valores.precio_unitario || "").trim()
    );
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
      if (clave === "precio_unitario") {
        texto = pesos(numero(valores.precio_unitario));
      }
      vistas[j].textContent = texto || "";
    }
  }

  /**
   * Muestra el aviso de tabla vacía solo cuando no hay productos.
   */
  function actualizarVacia() {
    mensajeVacia.hidden = tablaFilas.querySelectorAll("[data-fila-producto]").length > 0;
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
   * Valida y guarda el producto del panel en la tabla, y bloquea el panel.
   *
   * @returns {boolean} `true` si se guardó; `false` si hay un error que mostrar.
   */
  function guardarProducto() {
    var valores = leerCampos(panel, "data-campo-panel");
    var error = validarProducto(valores);
    mostrarError(errorPanel, error);
    if (error) {
      return false;
    }
    agregarFila(valores);
    mostrarError(errorPanel, "");
    panel.disabled = true;
    estadoPanel.textContent = "Producto guardado. Pulsa «+ Agregar otro producto» para escribir el siguiente.";
    recalcular();
    return true;
  }

  /**
   * Habilita el panel con los campos en blanco para escribir el siguiente producto.
   */
  function habilitarPanel() {
    panel.disabled = false;
    escribirPanel({});
    actualizarSubtotalPanel();
    mostrarError(errorPanel, "");
    estadoPanel.textContent = "Escribe el siguiente producto y pulsa Guardar.";
    panel.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // ------------------------------ Panel de producto ------------------------------

  panel.addEventListener("input", actualizarSubtotalPanel);

  panel.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter" && !panel.disabled) {
      evento.preventDefault();
      guardarProducto();
    }
  });

  if (botonGuardar) {
    botonGuardar.addEventListener("click", guardarProducto);
  }

  if (botonAgregar) {
    botonAgregar.addEventListener("click", function () {
      // Si hay un producto escrito y sin guardar, primero se guarda; si no se puede, no avanza.
      if (!panel.disabled && hayDatosEnPanel() && !guardarProducto()) {
        return;
      }
      habilitarPanel();
    });
  }

  /**
   * Convierte el enlace `wa.me` del servidor al esquema nativo en móvil.
   *
   * @param {string} enlace URL `https://wa.me/57...`.
   * @returns {string} Enlace `whatsapp://send` en móvil, el original en escritorio.
   */
  function enlaceWhatsappSegunDispositivo(enlace) {
    if (!/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
      return enlace;
    }
    try {
      var url = new URL(enlace);
      var numero = url.pathname.replace(/^\//, "");
      return (
        "whatsapp://send?phone=" +
        encodeURIComponent(numero) +
        "&text=" +
        encodeURIComponent(url.searchParams.get("text") || "")
      );
    } catch (error) {
      return enlace;
    }
  }

  /**
   * Apertura automática tras recargar la lista (solo móvil, SRS Migración §4).
   */
  var metaAuto = document.querySelector("[data-wa-auto]");
  if (metaAuto && metaAuto.content) {
    window.location.href = enlaceWhatsappSegunDispositivo(metaAuto.content);
  }

  // Si queda un producto escrito y sin guardar al registrar la venta, se guarda antes.
  // Con fetch, la orden se guarda y se refresca la lista antes de abrir WhatsApp.
  formulario.addEventListener("submit", function (evento) {
    if (!panel.disabled && hayDatosEnPanel() && !guardarProducto()) {
      evento.preventDefault();
      panel.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (!window.fetch || !FormData) {
      return;
    }
    evento.preventDefault();
    var esMovil = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    var tieneCelular = !!(campoTelefono && normalizarTelefono(campoTelefono.value).length === 10);
    // La ventana se abre dentro del gesto del clic: así Safari y Chrome no
    // bloquean la apertura después de esperar la respuesta del servidor.
    var ventanaWa = !esMovil && tieneCelular ? window.open("", "_blank") : null;

    fetch(formulario.action || window.location.href, {
      method: "POST",
      headers: { "X-OLB-AJAX": "1" },
      body: new FormData(formulario),
      credentials: "same-origin",
    })
      .then(function (respuesta) {
        return respuesta.json().then(function (datos) {
          return { estado: respuesta.status, datos: datos };
        });
      })
      .then(function (resultado) {
        if (resultado.estado >= 400 || !resultado.datos.ok) {
          if (ventanaWa) {
            ventanaWa.close();
          }
          if (typeof window.mostrarAvisoApp === "function") {
            window.mostrarAvisoApp(resultado.datos.error || "No se pudo registrar la venta.");
          }
          return;
        }
        var enlace = resultado.datos.enlace_whatsapp || "";
        if (esMovil && enlace && tieneCelular) {
          // Primero se recarga la lista con la orden nueva; la página abre WhatsApp al cargar.
          window.location.href =
            "/olb-byte?guardado=1&wa_auto=" + encodeURIComponent(resultado.datos.id_venta);
          return;
        }
        if (ventanaWa && enlace) {
          ventanaWa.location.href = enlace;
        }
        window.location.href = "/olb-byte?guardado=1";
      })
      .catch(function () {
        if (ventanaWa) {
          ventanaWa.close();
        }
        if (typeof window.mostrarAvisoApp === "function") {
          window.mostrarAvisoApp("No se pudo registrar la venta. Inténtalo de nuevo.");
        }
      });
  });

  // ------------------------------ Forma de pago ---------------------------------

  /**
   * Muestra solo los campos de pago que aplican y deshabilita los ocultos.
   *
   * Un campo deshabilitado no se envía: así el servidor no recibe un método de pago
   * de contado mientras la venta es a crédito.
   */
  function sincronizarPago() {
    var credito = formaPago && formaPago.value === "CREDITO";
    var conAnticipo = credito && anticipo && anticipo.value === "SI";

    formulario.querySelectorAll("[data-bloque='contado']").forEach(function (bloque) {
      bloque.hidden = credito;
    });
    formulario.querySelectorAll("[data-bloque='credito']").forEach(function (bloque) {
      bloque.hidden = !credito;
    });
    formulario.querySelectorAll("[data-bloque='anticipo']").forEach(function (bloque) {
      bloque.hidden = !conAnticipo;
    });

    if (metodoPago) {
      metodoPago.disabled = credito;
    }
    if (anticipo) {
      anticipo.disabled = !credito;
    }
    if (montoAnticipo) {
      montoAnticipo.disabled = !conAnticipo;
    }
    if (metodoAnticipo) {
      metodoAnticipo.disabled = !conAnticipo;
    }
  }

  if (formaPago) {
    formaPago.addEventListener("change", sincronizarPago);
  }
  if (anticipo) {
    anticipo.addEventListener("change", sincronizarPago);
  }

  // ----------------------------- Tabla de productos ------------------------------

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
      var valores = leerFila(fila);
      escribirEdicion(valores);
      mostrarError(errorEdicion, "");
      if (typeof dialogo.showModal === "function") {
        dialogo.showModal();
      }
    }
  });

  // ------------------------------ Cuadro de edición ------------------------------

  var botonGuardarEdicion = dialogo.querySelector("[data-guardar-edicion]");
  var botonCancelarEdicion = dialogo.querySelector("[data-cancelar-edicion]");

  if (botonGuardarEdicion) {
    botonGuardarEdicion.addEventListener("click", function () {
      var valores = leerCampos(dialogo, "data-campo-edicion");
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

  // --------------------------- Cliente y celular --------------------------------

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
    // Al pegar el número copiado en WhatsApp (o al escribirlo) queda limpio de inmediato.
    campoTelefono.addEventListener("input", function () {
      campoTelefono.value = normalizarTelefono(campoTelefono.value);
    });
    campoTelefono.addEventListener("blur", function () {
      campoTelefono.value = normalizarTelefono(campoTelefono.value);
    });
  }

  var botonPegar = formulario.querySelector("[data-pegar-numero]");

  /**
   * Abre WhatsApp directamente para que el usuario busque el contacto y copie
   * el número. Sin libreta nativa ni portapapeles: la página no puede leer la
   * agenda del teléfono (SRS Migración §4).
   */
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

  if (botonPegar) {
    botonPegar.addEventListener("click", abrirWhatsappNumero);
  }

  // ----------------------------------- Arranque ---------------------------------

  var filasIniciales = tablaFilas.querySelectorAll("[data-fila-producto]");
  for (var k = 0; k < filasIniciales.length; k += 1) {
    escribirFila(filasIniciales[k], leerFila(filasIniciales[k]));
  }
  if (formaPago) {
    sincronizarPago();
  }
  actualizarSubtotalPanel();
  recalcular();
})();
