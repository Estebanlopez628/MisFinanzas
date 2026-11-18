/**
 * Formulario de venta de OLB_BYTE: mini-tabla de productos en tiempo real.
 *
 * Responsabilidad
 * ---------------
 * - Mostrar subtotal por fila y totales (venta, costo y ganancia) mientras se escribe.
 * - Editar una fila con lápiz; «Actualizar» la guarda y «Cancelar» restaura lo que
 *   estaba guardado (o descarta la fila si nunca se guardó).
 * - Completar el celular al elegir un cliente existente.
 * - Usar la Contact Picker API cuando el navegador la ofrece; en otros casos el
 *   campo se escribe a mano.
 *
 * Ninguna regla de negocio vive aquí: el servidor recalcula todo al guardar.
 */

(function () {
  "use strict";

  var formulario = document.querySelector("[data-venta-form]");
  if (!formulario) {
    return;
  }

  var cuerpo = formulario.querySelector("[data-lineas]");
  var plantilla = document.querySelector("[data-plantilla-linea]");
  var campoNombre = formulario.querySelector("[data-cliente-nombre]");
  var campoTelefono = formulario.querySelector("[data-cliente-telefono]");
  var listaClientes = document.getElementById("clientes-lista");
  var botonEnviar = formulario.querySelector('button[type="submit"]');

  /**
   * Convierte un monto escrito en formato colombiano («50.000») a número.
   *
   * @param {string} texto Monto escrito.
   * @returns {number} Valor numérico, cero si no es válido.
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
   * Deja solo los 10 dígitos del celular, quitando el indicativo 57 si viene.
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
   * Lee los valores escritos en una fila.
   *
   * @param {HTMLElement} fila Fila de la mini-tabla.
   * @returns {Object} Valores tal como se escriben.
   */
  function valoresDeFila(fila) {
    var resultado = {};
    var campos = fila.querySelectorAll("[data-campo]");
    for (var i = 0; i < campos.length; i += 1) {
      resultado[campos[i].getAttribute("data-campo")] = campos[i].value;
    }
    return resultado;
  }

  /**
   * Escribe los valores de una fila en su vista de solo lectura.
   *
   * @param {HTMLElement} fila Fila a actualizar.
   */
  function pintarVista(fila) {
    var valores = valoresDeFila(fila);
    var vistas = fila.querySelectorAll("[data-vista]");
    for (var i = 0; i < vistas.length; i += 1) {
      var clave = vistas[i].getAttribute("data-vista");
      vistas[i].textContent = valores[clave] || "";
    }
  }

  /**
   * Cambia entre vista de solo lectura y edición de una fila.
   *
   * @param {HTMLElement} fila Fila a cambiar.
   * @param {string} modo `vista` o `edicion`.
   */
  function fijarModo(fila, modo) {
    fila.setAttribute("data-modo", modo);
  }

  /**
   * Guarda una copia de los valores actuales para poder cancelar la edición.
   *
   * @param {HTMLElement} fila Fila en edición.
   */
  function guardarCopia(fila) {
    fila.setAttribute("data-copia", JSON.stringify(valoresDeFila(fila)));
  }

  /**
   * Devuelve a los campos los valores de la última copia guardada.
   *
   * @param {HTMLElement} fila Fila cuya edición se cancela.
   */
  function restaurarCopia(fila) {
    var copia = fila.getAttribute("data-copia");
    if (!copia) {
      return;
    }
    var valores = JSON.parse(copia);
    var campos = fila.querySelectorAll("[data-campo]");
    for (var i = 0; i < campos.length; i += 1) {
      campos[i].value = valores[campos[i].getAttribute("data-campo")] || "";
    }
  }

  /**
   * Recalcula el subtotal de cada fila y los totales de la orden.
   */
  function recalcular() {
    var total = 0;
    var costo = 0;
    var ganancia = 0;
    var filas = cuerpo.querySelectorAll("[data-linea]");
    for (var i = 0; i < filas.length; i += 1) {
      var fila = filas[i];
      var valores = valoresDeFila(fila);
      var cantidad = Math.max(parseInt(valores.cantidad, 10) || 0, 0);
      var precio = numero(valores.precio_unitario);
      var costoUnitario = numero(valores.costo_unitario);
      var celdaSubtotal = fila.querySelector("[data-subtotal]");
      if (celdaSubtotal) {
        celdaSubtotal.textContent = pesos(precio * cantidad);
      }
      if (!valores.producto_nombre.trim()) {
        continue;
      }
      total += precio * cantidad;
      costo += costoUnitario * cantidad;
      ganancia += (precio - costoUnitario) * cantidad;
    }
    formulario.querySelector("[data-total]").textContent = pesos(total);
    formulario.querySelector("[data-total-costo]").textContent = pesos(costo);
    formulario.querySelector("[data-ganancia]").textContent = pesos(ganancia);
  }

  /**
   * Agrega una fila vacía en modo edición.
   *
   * @returns {HTMLElement} Fila creada.
   */
  function agregarFila() {
    var fila = plantilla.content.firstElementChild.cloneNode(true);
    fijarModo(fila, "edicion");
    cuerpo.appendChild(fila);
    return fila;
  }

  /**
   * Quita una fila y mantiene siempre una fila disponible para escribir.
   *
   * @param {HTMLElement} fila Fila a quitar.
   */
  function quitarFila(fila) {
    fila.parentNode.removeChild(fila);
    if (!cuerpo.querySelector("[data-linea]")) {
      agregarFila();
    }
    recalcular();
  }

  /**
   * Quita las filas que el usuario dejó en blanco antes de validar el formulario.
   * Sin esto, los campos obligatorios de una fila vacía impedirían enviar la venta.
   */
  function quitarFilasVacias() {
    var filas = cuerpo.querySelectorAll("[data-linea]");
    for (var i = 0; i < filas.length; i += 1) {
      var valores = valoresDeFila(filas[i]);
      if (!valores.producto_nombre.trim() && !valores.precio_unitario.trim() && !valores.costo_unitario.trim()) {
        if (filas.length > 1) {
          filas[i].parentNode.removeChild(filas[i]);
        }
      }
    }
    recalcular();
  }

  // ------------------------------- Eventos de filas -------------------------------

  cuerpo.addEventListener("click", function (evento) {
    var objetivo = evento.target;
    if (!(objetivo instanceof Element)) {
      return;
    }
    var fila = objetivo.closest("[data-linea]");
    if (!fila) {
      return;
    }

    if (objetivo.closest("[data-editar-linea]")) {
      guardarCopia(fila);
      fijarModo(fila, "edicion");
      var primero = fila.querySelector("[data-campo]");
      if (primero) {
        primero.focus();
      }
      return;
    }

    if (objetivo.closest("[data-actualizar-linea]")) {
      var campos = fila.querySelectorAll("[data-campo][required]");
      for (var i = 0; i < campos.length; i += 1) {
        if (!campos[i].reportValidity()) {
          return;
        }
      }
      fila.removeAttribute("data-nueva");
      pintarVista(fila);
      fijarModo(fila, "vista");
      recalcular();
      return;
    }

    if (objetivo.closest("[data-cancelar-linea]")) {
      if (fila.hasAttribute("data-nueva")) {
        quitarFila(fila);
      } else {
        restaurarCopia(fila);
        fijarModo(fila, "vista");
        recalcular();
      }
      return;
    }

    if (objetivo.closest("[data-eliminar-linea]")) {
      quitarFila(fila);
    }
  });

  cuerpo.addEventListener("input", recalcular);

  var botonAgregar = formulario.querySelector("[data-agregar-linea]");
  if (botonAgregar) {
    botonAgregar.addEventListener("click", function () {
      agregarFila();
      recalcular();
    });
  }

  // Las filas iniciales llegan con datos (tras un error) o vacías: en ambos casos
  // empiezan en edición porque aún no se han confirmado con «Actualizar».
  var iniciales = cuerpo.querySelectorAll("[data-linea]");
  for (var k = 0; k < iniciales.length; k += 1) {
    fijarModo(iniciales[k], "edicion");
  }
  recalcular();

  if (botonEnviar) {
    // El clic se dispara antes de la validación nativa del formulario, así que
    // aquí se limpian las filas en blanco a tiempo.
    botonEnviar.addEventListener("click", quitarFilasVacias);
  }

  // ---------------------------- Cliente y celular -------------------------------

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

  // La Contact Picker API solo existe en algunos navegadores móviles y exige una
  // conexión segura. Si no está disponible, el botón queda oculto.
  var botonContactos = formulario.querySelector("[data-contactos]");
  if (botonContactos && "contacts" in navigator && "ContactsManager" in window) {
    botonContactos.hidden = false;
    botonContactos.addEventListener("click", function () {
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
        .catch(function () {
          // El usuario canceló o el navegador negó el permiso: se escribe a mano.
        });
    });
  }
})();
