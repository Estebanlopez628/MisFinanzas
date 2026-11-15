/**
 * Mejora progresiva de "Mis Finanzas".
 *
 * Responsabilidad
 * ---------------
 * - Enviar los datos del formulario a `POST /finanzas/calcular` y pintar el
 *   resultado sin recargar la página.
 * - Reflejar en tiempo real (SRS v1.3) las deducciones de ley en pesos, el
 *   valor del auxilio de transporte y el desglose de recargos.
 * - Ofrecer el botón "Limpiar" para vaciar las horas y avisar cuando hay
 *   cambios sin guardar.
 * - Dar confirmación visual ("¡Copiado!") a los botones `data-copiar` de los
 *   atajos de pago.
 *
 * Si el navegador no ejecuta JavaScript (o la petición falla), el formulario
 * sigue funcionando con el POST clásico que renderiza el servidor.
 */

(function () {
  "use strict";

  // Retardo del debounce: suficiente para no saturar el servidor mientras se
  // escribe, y por debajo del umbral de 100 ms percibido por el usuario.
  var RETARDO_MS = 150;
  var RUTA_CALCULO = "/finanzas/calcular";

  // Tiempo que el botón de copiado muestra la confirmación antes de restaurarse.
  var DURACION_CONFIRMACION_MS = 1200;

  // Campos que la interfaz muestra con signo negativo.
  var CAMPOS_NEGATIVOS = {
    deduccion_salud: true,
    deduccion_pension: true,
    deduccion_incapacidad: true,
    total_deducciones: true
  };

  var formulario = document.querySelector("[data-calculadora]");
  if (!formulario) {
    return;
  }

  var bloqueErrores = document.querySelector("[data-errores]");
  var cuerpoDetalle = document.querySelector("[data-detalle]");
  var mensajeAuxilio = document.querySelector("[data-mensaje-auxilio]");
  var valorAuxilio = document.querySelector("[data-auxilio-valor]");
  var avisoCambios = document.querySelector("[data-aviso-cambios]");
  var temporizador = null;
  var peticionEnCurso = 0;
  var hayCambios = false;

  /**
   * Reúne los campos del formulario en un objeto plano.
   *
   * @returns {Object<string, string>} Valores tal como están escritos.
   */
  function leerFormulario() {
    var datos = {};
    var campos = formulario.querySelectorAll("[data-entrada]");
    for (var i = 0; i < campos.length; i += 1) {
      datos[campos[i].name] = campos[i].value;
    }
    return datos;
  }

  /**
   * Escribe un valor formateado en el elemento marcado con `data-campo`.
   *
   * @param {string} campo Clave del campo devuelta por el servidor.
   * @param {string} valor Texto ya formateado en pesos.
   */
  function pintarCampo(campo, valor) {
    var destino = document.querySelector('[data-campo="' + campo + '"]');
    if (!destino) {
      return;
    }
    destino.textContent = (CAMPOS_NEGATIVOS[campo] ? "− " : "") + valor;
  }

  /**
   * Pinta una deducción de ley en todos los destinos `data-deduccion`.
   *
   * Existen dos destinos para salud y pensión (el bloque resumen y la tabla
   * final), por eso se recorre la lista completa en lugar de usar un único
   * `querySelector`.
   *
   * @param {string} clave Identificador de la deducción (`salud` o `pension`).
   * @param {string} valor Texto ya formateado en pesos.
   */
  function pintarDeduccion(clave, valor) {
    var destinos = document.querySelectorAll('[data-deduccion="' + clave + '"]');
    for (var i = 0; i < destinos.length; i += 1) {
      destinos[i].textContent = "− " + valor;
    }
  }

  /**
   * Pinta el valor monetario del auxilio de transporte.
   *
   * Cuando el salario supera el tope de 2 SMMLV el servidor devuelve cero; el
   * bloque pierde entonces el realce positivo para que la advertencia destaque.
   *
   * @param {string} valor Texto ya formateado en pesos.
   * @param {boolean} aplica Indica si el usuario conserva el auxilio.
   */
  function pintarValorAuxilio(valor, aplica) {
    if (!valorAuxilio) {
      return;
    }
    valorAuxilio.textContent = valor;
    valorAuxilio.dataset.aplica = aplica ? "si" : "no";
    valorAuxilio.classList.toggle("auxilio__monto--anulado", !aplica);
  }

  /**
   * Muestra u oculta el bloque de errores de validación.
   *
   * @param {string[]} errores Mensajes devueltos por el servidor.
   */
  function pintarErrores(errores) {
    if (!bloqueErrores) {
      return;
    }

    if (!errores || errores.length === 0) {
      bloqueErrores.hidden = true;
      bloqueErrores.innerHTML = "";
      return;
    }

    var lista = document.createElement("ul");
    errores.forEach(function (mensaje) {
      var item = document.createElement("li");
      item.textContent = mensaje;
      lista.appendChild(item);
    });

    bloqueErrores.innerHTML = "<strong>Revisa los datos:</strong>";
    bloqueErrores.appendChild(lista);
    bloqueErrores.hidden = false;
  }

  /**
   * Reconstruye la tabla de recargos con el desglose devuelto.
   *
   * @param {Array<{etiqueta: string, factor: string, horas: string, valor: string}>} filas
   */
  function pintarDetalle(filas) {
    if (!cuerpoDetalle) {
      return;
    }

    cuerpoDetalle.innerHTML = "";

    if (!filas || filas.length === 0) {
      var vacia = document.createElement("tr");
      var celda = document.createElement("td");
      celda.colSpan = 4;
      celda.className = "tabla__vacia";
      celda.textContent = "Sin horas extras ni recargos registrados.";
      vacia.appendChild(celda);
      cuerpoDetalle.appendChild(vacia);
      return;
    }

    filas.forEach(function (fila) {
      var tr = document.createElement("tr");

      var concepto = document.createElement("td");
      concepto.textContent = fila.etiqueta;

      var factor = document.createElement("td");
      factor.textContent = "× " + fila.factor;

      var horas = document.createElement("td");
      horas.className = "tabla__numero";
      horas.textContent = fila.horas;

      var valor = document.createElement("td");
      valor.className = "tabla__numero";
      valor.textContent = fila.valor;

      tr.appendChild(concepto);
      tr.appendChild(factor);
      tr.appendChild(horas);
      tr.appendChild(valor);
      cuerpoDetalle.appendChild(tr);
    });
  }

  /**
   * Actualiza el aviso del tope de 2 SMMLV.
   *
   * @param {string} mensaje Texto del validador.
   * @param {boolean} aplica Indica si el auxilio se conserva.
   */
  function pintarAuxilio(mensaje, aplica) {
    if (!mensajeAuxilio) {
      return;
    }
    mensajeAuxilio.textContent = mensaje;
    mensajeAuxilio.dataset.aplica = aplica ? "si" : "no";
  }

  /**
   * Aplica una respuesta correcta del servidor a la interfaz.
   *
   * @param {{datos: Object<string, string>, detalle: Array, mensaje_auxilio: string, aplica_auxilio: boolean}} respuesta
   */
  function aplicarResultado(respuesta) {
    var datos = respuesta.datos || {};

    Object.keys(datos).forEach(function (campo) {
      pintarCampo(campo, datos[campo]);
    });

    // Deducciones de ley y auxilio se pintan también en sus bloques dedicados.
    if (datos.deduccion_salud) {
      pintarDeduccion("salud", datos.deduccion_salud);
    }
    if (datos.deduccion_pension) {
      pintarDeduccion("pension", datos.deduccion_pension);
    }
    if (datos.auxilio_transporte) {
      pintarValorAuxilio(datos.auxilio_transporte, respuesta.aplica_auxilio);
    }

    pintarDetalle(respuesta.detalle);
    pintarAuxilio(respuesta.mensaje_auxilio, respuesta.aplica_auxilio);
    pintarErrores([]);
  }

  /**
   * Consulta el endpoint JSON con los valores actuales del formulario.
   */
  function calcular() {
    var numeroPeticion = peticionEnCurso + 1;
    peticionEnCurso = numeroPeticion;

    fetch(RUTA_CALCULO, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Requested-With": "fetch"
      },
      body: JSON.stringify(leerFormulario())
    })
      .then(function (respuesta) {
        if (respuesta.status === 401) {
          window.location.href = "/login";
          return null;
        }
        return respuesta.json();
      })
      .then(function (cuerpo) {
        // Una respuesta vieja no debe sobrescribir a la más reciente.
        if (!cuerpo || numeroPeticion !== peticionEnCurso) {
          return;
        }
        if (cuerpo.ok) {
          aplicarResultado(cuerpo);
        } else {
          pintarErrores(cuerpo.errores || ["No se pudo calcular la liquidación."]);
        }
      })
      .catch(function () {
        // Sin conexión el formulario sigue disponible con el POST clásico.
        pintarErrores(["No se pudo actualizar el cálculo en vivo. Puedes usar el botón Calcular."]);
      });
  }

  /**
   * Programa un cálculo con debounce.
   */
  function programarCalculo() {
    window.clearTimeout(temporizador);
    temporizador = window.setTimeout(calcular, RETARDO_MS);
  }

  /**
   * Marca que existen cambios sin guardar y muestra el aviso.
   */
  function marcarCambios() {
    hayCambios = true;
    if (avisoCambios) {
      avisoCambios.hidden = false;
    }
  }

  /**
   * Limpia las horas del formulario (única acción de plantilla vigente).
   *
   * @param {string} nombre Identificador de la acción; solo `limpiar` tiene efecto.
   */
  function aplicarPlantilla(nombre) {
    if (nombre !== "limpiar") {
      return;
    }
    var campos = formulario.querySelectorAll('input[name^="horas_"]');
    for (var i = 0; i < campos.length; i += 1) {
      campos[i].value = "0";
    }
    marcarCambios();
    programarCalculo();
  }

  /**
   * Copia un texto al portapapeles con respaldo para navegadores antiguos.
   *
   * @param {string} texto Contenido a copiar.
   */
  function copiarAlPortapapeles(texto) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).catch(function () {
        /* Si el permiso se deniega, el usuario aún puede seleccionar el texto. */
      });
      return;
    }

    var auxiliar = document.createElement("textarea");
    auxiliar.value = texto;
    auxiliar.setAttribute("readonly", "readonly");
    auxiliar.style.position = "fixed";
    auxiliar.style.opacity = "0";
    document.body.appendChild(auxiliar);
    auxiliar.select();
    try {
      document.execCommand("copy");
    } catch (error) {
      /* Sin soporte de copiado: no se interrumpe la navegación. */
    }
    document.body.removeChild(auxiliar);
  }

  /**
   * Da confirmación visual breve a los botones `data-copiar`.
   *
   * Se usa delegación en `document` para cubrir tanto el bloque de atajos como
   * la tabla de gestión, sin registrar un escucha por botón.
   */
  function prepararCopiadoRapido() {
    document.addEventListener("click", function (evento) {
      var boton = evento.target.closest("[data-copiar]");
      if (!boton) {
        return;
      }

      copiarAlPortapapeles(boton.getAttribute("data-copiar") || "");

      var textoOriginal = boton.textContent;
      boton.textContent = "¡Copiado!";
      boton.classList.add("boton--copiado");

      window.setTimeout(function () {
        boton.textContent = textoOriginal;
        boton.classList.remove("boton--copiado");
      }, DURACION_CONFIRMACION_MS);
    });
  }

  formulario.addEventListener("input", function () {
    marcarCambios();
    programarCalculo();
  });

  formulario.addEventListener("submit", function (evento) {
    var boton = evento.submitter;
    var accion = boton ? boton.getAttribute("formaction") : null;

    // "Guardar periodo" debe llegar al servidor como POST clásico. El aviso de
    // cambios se limpia antes de navegar para no bloquear la salida.
    if (accion) {
      hayCambios = false;
      return;
    }

    evento.preventDefault();
    window.clearTimeout(temporizador);
    calcular();
  });

  var botonesPlantilla = formulario.querySelectorAll("[data-plantilla]");
  for (var i = 0; i < botonesPlantilla.length; i += 1) {
    botonesPlantilla[i].addEventListener("click", function (evento) {
      aplicarPlantilla(evento.currentTarget.getAttribute("data-plantilla"));
    });
  }

  // Aviso del navegador: evita perder una liquidación a medio escribir.
  window.addEventListener("beforeunload", function (evento) {
    if (!hayCambios) {
      return undefined;
    }
    evento.preventDefault();
    evento.returnValue = "";
    return "";
  });

  prepararCopiadoRapido();

  // Reactividad al entrar: el primer cálculo llega sin esperar a que el usuario
  // toque un campo. Se difiere un ciclo para no competir con el render inicial.
  window.setTimeout(calcular, 0);
})();
