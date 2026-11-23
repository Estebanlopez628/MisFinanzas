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
  // SRS v1.6: tras «Limpiar», la incapacidad registrada deja de aplicarse en el
  // cálculo hasta que el usuario escriba nuevas fechas.
  var incapacidadOmitida = false;

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
    // Las fechas de incapacidad se envían siempre (aunque vayan vacías) para que
    // el servidor sepa que el descuento se calcula desde ellas.
    var inicio = document.querySelector("[data-incapacidad-inicio]");
    var fin = document.querySelector("[data-incapacidad-fin]");
    datos.incapacidad_inicio = inicio ? inicio.value : "";
    datos.incapacidad_fin = fin ? fin.value : "";
    datos.incapacidad_omitir = incapacidadOmitida ? "1" : "";
    return datos;
  }

  /**
   * Escribe un valor formateado en el elemento marcado con `data-campo`.
   *
   * SRS v1.5: las deducciones se muestran en rojo y sin signo menos; el rótulo
   * ya indica que restan del salario.
   *
   * @param {string} campo Clave del campo devuelta por el servidor.
   * @param {string} valor Texto ya formateado en pesos.
   */
  function pintarCampo(campo, valor) {
    var destino = document.querySelector('[data-campo="' + campo + '"]');
    if (!destino) {
      return;
    }
    destino.textContent = valor;
  }

  /**
   * Pinta una deducción de ley en todos los destinos `data-deduccion`.
   *
   * Existen dos destinos para salud y pensión (el bloque resumen y la tabla
   * final), por eso se recorre la lista completa en lugar de usar un único
   * `querySelector`. SRS v1.5: en la caja de deducciones el valor va en rojo y
   * sin signo menos; el título ya indica que es un descuento.
   *
   * @param {string} clave Identificador de la deducción (`salud`, `pension` o `incapacidad`).
   * @param {string} valor Texto ya formateado en pesos.
   */
  function pintarDeduccion(clave, valor) {
    var destinos = document.querySelectorAll('[data-deduccion="' + clave + '"]');
    for (var i = 0; i < destinos.length; i += 1) {
      destinos[i].textContent = valor;
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
      item.textContent =
        typeof window.limpiarMensajeError === "function"
          ? window.limpiarMensajeError(mensaje)
          : mensaje;
      lista.appendChild(item);
    });

    bloqueErrores.innerHTML = "<strong>Revisa los datos:</strong>";
    bloqueErrores.appendChild(lista);
    bloqueErrores.hidden = false;
  }

  /**
   * Reconstruye la tabla de recargos con el desglose devuelto.
   *
   * Solo muestra concepto, horas y valor: el factor no aporta al lector.
   *
   * @param {Array<{etiqueta: string, horas: string, valor: string}>} filas
   */
  function pintarDetalle(filas) {
    if (!cuerpoDetalle) {
      return;
    }

    cuerpoDetalle.innerHTML = "";

    if (!filas || filas.length === 0) {
      var vacia = document.createElement("tr");
      var celda = document.createElement("td");
      celda.colSpan = 3;
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

      var horas = document.createElement("td");
      horas.className = "tabla__numero";
      horas.textContent = fila.horas;

      var valor = document.createElement("td");
      valor.className = "tabla__numero";
      valor.textContent = fila.valor;

      tr.appendChild(concepto);
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
    if (datos.deduccion_incapacidad) {
      pintarDeduccion("incapacidad", datos.deduccion_incapacidad);
    }
    if (datos.auxilio_transporte) {
      pintarValorAuxilio(datos.auxilio_transporte, respuesta.aplica_auxilio);
    }
    // SRS v1.5: total de la caja (salud + pensión + incapacidad + fijas).
    if (respuesta.total_deducciones_ley) {
      pintarTexto("[data-total-deducciones]", respuesta.total_deducciones_ley);
    }

    pintarDetalle(respuesta.detalle);
    pintarAuxilio(respuesta.mensaje_auxilio, respuesta.aplica_auxilio);
    pintarQuincenas(respuesta.quincenas || []);
    pintarIncapacidad(
      respuesta.incapacidad,
      respuesta.datos ? respuesta.datos.deduccion_incapacidad : undefined
    );
    pintarErrores([]);
  }

  /**
   * Reconstruye la tabla de tramos mensuales de la incapacidad.
   *
   * @param {HTMLElement|null} cuerpo Destino `data-incapacidad-tramos`.
   * @param {Array<Object>} tramos Tramos devueltos por el servidor.
   */
  function pintarTramos(cuerpo, tramos) {
    if (!cuerpo) {
      return;
    }
    cuerpo.innerHTML = "";
    tramos.forEach(function (tramo) {
      var tr = document.createElement("tr");
      if (tramo.actual) {
        tr.className = "fila-periodo";
      }

      var periodo = document.createElement("td");
      periodo.textContent = tramo.periodo;

      var dias = document.createElement("td");
      dias.textContent = String(tramo.dias);

      var descuento = document.createElement("td");
      descuento.className = "tabla__numero";
      descuento.textContent = tramo.descuento;

      tr.appendChild(periodo);
      tr.appendChild(dias);
      tr.appendChild(descuento);
      cuerpo.appendChild(tr);
    });
  }

  /**
   * Muestra la incapacidad del periodo y su desglose por mes (SRS v1.5).
   *
   * El número de días lo calcula el servidor a partir de las fechas. El descuento
   * aplicado es solo el tramo del mes elegido; los demás tramos se listan para
   * que el usuario sepa en qué periodo se descontarán.
   *
   * @param {{dias_mes: number, dias_al_100: number, dias_al_66: number,
   *   descuento: string, tramos: Array<Object>}|null} detalle
   * @param {string} descuentoTotal Descuento del periodo ya formateado.
   */
  function pintarIncapacidad(detalle, descuentoTotal) {
    var oculto = formulario.querySelector('input[name="deduccion_incapacidad"]');
    if (oculto && descuentoTotal !== undefined) {
      oculto.value = descuentoTotal;
    }

    var dias = document.querySelector("[data-incapacidad-dias]");
    var resumen = document.querySelector("[data-incapacidad-resumen]");
    var desglose = document.querySelector("[data-incapacidad-desglose]");
    var cuerpo = document.querySelector("[data-incapacidad-tramos]");

    if (!detalle) {
      if (dias) {
        dias.textContent = "—";
      }
      if (resumen) {
        resumen.hidden = true;
        resumen.textContent = "";
      }
      if (desglose) {
        desglose.hidden = true;
      }
      if (cuerpo) {
        cuerpo.innerHTML = "";
      }
      return;
    }

    var tramos = detalle.tramos || [];
    var totalDias = 0;
    tramos.forEach(function (tramo) {
      totalDias += tramo.dias;
    });

    if (dias) {
      dias.textContent = String(totalDias);
    }
    if (resumen) {
      resumen.hidden = false;
      resumen.textContent =
        detalle.dias_mes + " día(s) en el periodo · " +
        detalle.dias_al_100 + " sin descuento (empleador) · " +
        detalle.dias_al_66 + " al 66,67 % (EPS) · Descuento aplicado: " +
        detalle.descuento + ".";
    }
    pintarTramos(cuerpo, tramos);
    if (desglose) {
      desglose.hidden = tramos.length === 0;
    }
  }

  /**
   * Actualiza las tarjetas de Quincena 1 y 2 (SRS v1.4, REQ-04 y REQ-05).
   *
   * Cada tarjeta se identifica por el número de pago que devuelve el servidor.
   * El saldo libre cambia de color cuando queda negativo.
   *
   * @param {Array<{numero: number, ingreso: string,
   *   saldo_libre: string, negativo: boolean}>} filas
   */
  function pintarQuincenas(filas) {
    filas.forEach(function (fila) {
      var saldo = document.querySelector('[data-saldo-quincena="' + fila.numero + '"]');
      if (saldo) {
        saldo.textContent = fila.saldo_libre;
        saldo.classList.toggle("valor-negativo", Boolean(fila.negativo));
      }
      pintarTexto('[data-ingreso-quincena="' + fila.numero + '"]', fila.ingreso);
    });
  }

  /**
   * Escribe un texto en el primer elemento que coincida con el selector.
   *
   * @param {string} selector Selector CSS del destino.
   * @param {string} texto Texto ya formateado.
   */
  function pintarTexto(selector, texto) {
    var destino = document.querySelector(selector);
    if (destino) {
      destino.textContent = texto;
    }
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

  formulario.addEventListener("input", function () {
    marcarCambios();
    programarCalculo();
  });

  // SRS v1.4, REQ-05: las fechas de la incapacidad viven fuera del formulario de
  // liquidación; cualquier cambio en ellas recalcula el sueldo y las quincenas.
  var avisoIncapacidad = document.querySelector("[data-incapacidad-aviso]");

  document.querySelectorAll("[data-incapacidad-inicio], [data-incapacidad-fin]").forEach(function (campo) {
    campo.addEventListener("input", function () {
      incapacidadOmitida = false;
      if (avisoIncapacidad) {
        avisoIncapacidad.hidden = true;
      }
      programarCalculo();
    });
    campo.addEventListener("change", programarCalculo);
    // SRS v1.6: Enter solo recalcula; nunca envía el formulario de guardado.
    campo.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter") {
        evento.preventDefault();
        calcular();
      }
    });
  });

  var botonLimpiarIncapacidad = document.querySelector("[data-incapacidad-limpiar]");
  if (botonLimpiarIncapacidad) {
    botonLimpiarIncapacidad.addEventListener("click", function () {
      var inicioLimpio = document.querySelector("[data-incapacidad-inicio]");
      var finLimpio = document.querySelector("[data-incapacidad-fin]");
      var diasLimpio = document.querySelector("[data-incapacidad-dias]");
      if (inicioLimpio) {
        inicioLimpio.value = "";
      }
      if (finLimpio) {
        finLimpio.value = "";
      }
      if (diasLimpio) {
        diasLimpio.textContent = "—";
      }
      incapacidadOmitida = true;
      if (avisoIncapacidad) {
        avisoIncapacidad.hidden = false;
      }
      calcular();
    });
  }

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

  // El copiado de atajos lo gestiona `app.js` de forma global: una sola
  // confirmación «¡Copiado!» que vuelve a «Copiar» a los 5 segundos.

  // Reactividad al entrar: el primer cálculo llega sin esperar a que el usuario
  // toque un campo. Se difiere un ciclo para no competir con el render inicial.
  window.setTimeout(calcular, 0);
})();
