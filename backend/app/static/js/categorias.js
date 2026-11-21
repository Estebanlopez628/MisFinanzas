/**
 * Selector cerrado de categorías, vinculación con deudas y conservación de
 * formularios (SRS v1.9, secciones 1.2 y 3.2).
 *
 * Responsabilidad
 * ---------------
 * - Desplegar las ocho categorías del catálogo al hacer clic en el cuadro y
 *   pegar el nombre exacto al elegir una. El cuadro es de solo lectura.
 * - Mostrar la pregunta SI/NO cuando la categoría es «Créditos y Obligaciones»:
 *   con SI se habilita el desplegable de deudas; con NO se deshabilita guardar
 *   y se ofrece el acceso rápido al módulo de deudas.
 * - Guardar en `sessionStorage` los datos del formulario al enviarlo o al ir a
 *   registrar la deuda, y restaurarlos al volver (con SI y la deuda elegida).
 */
(function () {
  "use strict";

  var CATEGORIA_CREDITO = "Créditos y Obligaciones";
  // SRS v2.0, sección 2: una sola clave para todo el ciclo de ida y vuelta.
  var CLAVE_PENDIENTE = "misfinanzas_pending_debt_link";
  var ORIGENES = {
    deducciones: {
      modulo: "deducciones_fijas",
      etiqueta: "Deducciones Fijas",
      destino: "/presupuesto"
    },
    finanzas: {
      modulo: "finanzas_gastos_fijos",
      etiqueta: "Gastos Fijos - Finanzas",
      destino: "/finanzas"
    },
    trabajos: {
      modulo: "trabajos_extras_gastos_fijos",
      etiqueta: "Gastos Fijos - Trabajos Extras",
      destino: "/trabajos-extras"
    }
  };

  function datosFormulario(formulario) {
    var datos = {};
    Array.prototype.forEach.call(formulario.elements, function (campo) {
      if (!campo.name) {
        return;
      }
      if (campo.type === "checkbox") {
        datos[campo.name] = campo.checked ? "on" : "";
      } else if (campo.type === "radio") {
        if (campo.checked) {
          datos[campo.name] = campo.value;
        }
      } else {
        datos[campo.name] = campo.value;
      }
    });
    return datos;
  }

  function restaurarDatos(formulario, guardado) {
    Object.keys(guardado).forEach(function (nombre) {
      formulario.querySelectorAll('[name="' + nombre + '"]').forEach(function (campo) {
        if (campo.type === "checkbox") {
          campo.checked = guardado[nombre] === "on";
        } else if (campo.type === "radio") {
          campo.checked = campo.value === guardado[nombre];
        } else {
          campo.value = guardado[nombre];
        }
      });
    });
    // Avisar a los componentes condicionales de que los valores cambiaron.
    formulario
      .querySelectorAll("[data-categoria-entrada], [data-vincular-si], [data-vincular-no]")
      .forEach(function (campo) {
        campo.dispatchEvent(new Event("change", { bubbles: true }));
      });
  }

  function cerrar(raiz) {
    var lista = raiz.querySelector("[data-categoria-lista]");
    var boton = raiz.querySelector("[data-categoria-boton]");
    if (lista) {
      lista.hidden = true;
    }
    if (boton) {
      boton.setAttribute("aria-expanded", "false");
    }
  }

  function abrir(raiz) {
    var lista = raiz.querySelector("[data-categoria-lista]");
    var boton = raiz.querySelector("[data-categoria-boton]");
    if (lista) {
      lista.hidden = false;
      var primera = lista.querySelector("[data-categoria-opcion]");
      if (primera) {
        primera.focus();
      }
    }
    if (boton) {
      boton.setAttribute("aria-expanded", "true");
    }
  }

  document.querySelectorAll("[data-selector-categoria]").forEach(function (raiz) {
    var entrada = raiz.querySelector("[data-categoria-entrada]");
    var boton = raiz.querySelector("[data-categoria-boton]");
    var lista = raiz.querySelector("[data-categoria-lista]");
    if (!entrada || !boton || !lista) {
      return;
    }

    function alternar() {
      if (lista.hidden) {
        abrir(raiz);
      } else {
        cerrar(raiz);
      }
    }

    entrada.addEventListener("click", alternar);
    boton.addEventListener("click", function (evento) {
      evento.stopPropagation();
      alternar();
    });

    lista.querySelectorAll("[data-categoria-opcion]").forEach(function (opcion) {
      opcion.addEventListener("click", function () {
        entrada.value = opcion.getAttribute("data-categoria-opcion");
        entrada.dispatchEvent(new Event("change", { bubbles: true }));
        cerrar(raiz);
        entrada.focus();
      });
    });

    raiz.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") {
        cerrar(raiz);
        return;
      }
      if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
        evento.preventDefault();
        var opciones = Array.prototype.slice.call(
          lista.querySelectorAll("[data-categoria-opcion]")
        );
        if (!opciones.length) {
          return;
        }
        var actual = opciones.indexOf(document.activeElement);
        var siguiente =
          evento.key === "ArrowDown"
            ? (actual + 1) % opciones.length
            : (actual <= 0 ? opciones.length - 1 : actual - 1);
        opciones[siguiente].focus();
      }
    });

    document.addEventListener("click", function (evento) {
      if (!raiz.contains(evento.target)) {
        cerrar(raiz);
      }
    });
  });

  // Pregunta condicional de la sección 3.2.
  document.querySelectorAll("[data-vinculo-condicional]").forEach(function (bloque) {
    var formulario = bloque.closest("form");
    if (!formulario) {
      return;
    }
    var entradaCategoria = formulario.querySelector("[data-categoria-entrada]");
    var botonGuardar = formulario.querySelector('button[type="submit"]');
    var selectorDeuda = bloque.querySelector("[data-deuda-selector]");
    var aviso = bloque.querySelector("[data-sin-deuda]");
    var opcionNo = bloque.querySelector("[data-vincular-no]");

    function sincronizar() {
      var esCredito =
        entradaCategoria && entradaCategoria.value === CATEGORIA_CREDITO;
      bloque.hidden = !esCredito;
      if (botonGuardar) {
        botonGuardar.disabled = false;
      }
      if (!esCredito) {
        return;
      }
      var eligioNo = opcionNo && opcionNo.checked;
      if (selectorDeuda) {
        selectorDeuda.hidden = !!eligioNo;
      }
      if (aviso) {
        aviso.hidden = !eligioNo;
      }
      if (botonGuardar) {
        botonGuardar.disabled = !!eligioNo;
      }
    }

    bloque.querySelectorAll('input[name="vinculacion"]').forEach(function (opcion) {
      opcion.addEventListener("change", sincronizar);
    });
    if (entradaCategoria) {
      entradaCategoria.addEventListener("change", sincronizar);
    }
    sincronizar();
  });

  document.querySelectorAll("[data-vincular-deuda]").forEach(function (caja) {
    var contenedor = caja.closest("[data-vinculo-deuda]");
    if (!contenedor) {
      return;
    }
    var selector = contenedor.querySelector("[data-deuda-selector]");
    var opciones = contenedor.querySelector("[data-deuda-opciones]");

    function sincronizar() {
      if (selector) {
        selector.hidden = !caja.checked;
      }
      if (!caja.checked && opciones) {
        opciones.value = "";
      }
    }

    caja.addEventListener("change", sincronizar);
    sincronizar();
  });

  // SRS v2.0, sección 3.2: al elegir una deuda el valor se autocompleta con su
  // cuota oficial y queda bloqueado mientras siga vinculado. Si se cambia a
  // otra deuda se toma la nueva cuota; si se desvincula (checkbox sin marcar,
  // respuesta NO o categoría distinta) vuelve a ser editable.
  document.querySelectorAll("[data-deuda-opciones]").forEach(function (selectorDeuda) {
    var formulario = selectorDeuda.closest("form");
    var campoValor = formulario && formulario.querySelector('input[name="valor"]');
    if (!campoValor) {
      return;
    }
    var contenedor = selectorDeuda.closest(
      "[data-vinculo-deuda], [data-vinculo-condicional]"
    );
    var caja = contenedor && contenedor.querySelector("[data-vincular-deuda]");
    var opcionNo = contenedor && contenedor.querySelector("[data-vincular-no]");
    var opcionSi = contenedor && contenedor.querySelector("[data-vincular-si]");
    var nota = contenedor && contenedor.querySelector("[data-nota-sincronizada]");
    var notaAcreedor = nota && nota.querySelector("[data-nota-acreedor]");
    var entradaCategoria = formulario && formulario.querySelector("[data-categoria-entrada]");

    function vinculado() {
      if (!selectorDeuda.value) {
        return false;
      }
      if (caja && !caja.checked) {
        return false;
      }
      if (opcionNo && opcionNo.checked) {
        return false;
      }
      return true;
    }

    function sincronizarValor() {
      // En la edición de un gasto, cambiar a otra categoría desvincula la
      // deuda y devuelve el valor al usuario (SRS v2.0, 3.2). Se limita a los
      // formularios de gastos para no alterar las libranzas de deducciones.
      var accion = formulario && formulario.getAttribute("action");
      var esEdicionGasto = accion && accion.indexOf("/gastos/") !== -1;
      if (
        esEdicionGasto &&
        entradaCategoria &&
        entradaCategoria.value !== CATEGORIA_CREDITO &&
        selectorDeuda.value
      ) {
        selectorDeuda.value = "";
        if (caja) {
          caja.checked = false;
          caja.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
      var loEsta = vinculado();
      var opcion = selectorDeuda.options[selectorDeuda.selectedIndex];
      if (loEsta && opcion) {
        var cuota = opcion.getAttribute("data-cuota");
        if (cuota) {
          campoValor.value = cuota;
        }
        if (nota) {
          nota.hidden = false;
          if (notaAcreedor) {
            notaAcreedor.textContent = opcion.textContent.split("·")[0].trim();
          }
        }
      } else if (nota) {
        nota.hidden = true;
      }
      campoValor.readOnly = loEsta;
      // SRS v3.0, punto 9: el bloqueo debe verse, no solo sentirse al intentar
      // escribir. El candado y el fondo gris viven en CSS.
      if (campoValor.classList) {
        campoValor.classList.toggle("campo__control--bloqueado", loEsta);
      }
    }

    selectorDeuda.addEventListener("change", sincronizarValor);
    if (caja) {
      caja.addEventListener("change", sincronizarValor);
    }
    if (opcionNo) {
      opcionNo.addEventListener("change", sincronizarValor);
    }
    if (opcionSi) {
      opcionSi.addEventListener("change", sincronizarValor);
    }
    if (entradaCategoria) {
      entradaCategoria.addEventListener("change", sincronizarValor);
    }
    sincronizarValor();
  });

  // Ir a registrar la deuda: se serializa el formulario y se guarda el módulo,
  // la etiqueta legible y todos los valores diligenciados (SRS v2.0, 2.1).
  document.querySelectorAll("[data-ir-a-deudas]").forEach(function (enlace) {
    enlace.addEventListener("click", function () {
      var formulario = enlace.closest("form");
      var modulo = enlace.getAttribute("data-origen");
      if (!formulario || !modulo) {
        return;
      }
      var origen = ORIGENES[modulo] || {
        modulo: modulo,
        etiqueta: modulo,
        destino: "/"
      };
      var pendiente = {
        origin_module: origen.modulo,
        origin_label: origen.etiqueta,
        origin_destino: origen.destino,
        form_data: datosFormulario(formulario)
      };
      try {
        sessionStorage.setItem(CLAVE_PENDIENTE, JSON.stringify(pendiente));
        // Clave heredada: conserva el respaldo sin JS de versiones anteriores.
        sessionStorage.setItem(
          "deuda-origen:" + modulo,
          JSON.stringify(pendiente.form_data)
        );
      } catch (error) {
        // Sin sessionStorage el formulario sigue funcionando igual.
      }
    });
  });

  // Restauración al volver de registrar la deuda (SRS v2.0, 2.3).
  var parametros = new URLSearchParams(location.search);
  if (parametros.has("guardado_deuda")) {
    var pendiente = null;
    try {
      pendiente = JSON.parse(sessionStorage.getItem(CLAVE_PENDIENTE) || "null");
    } catch (error) {
      pendiente = null;
    }
    document.querySelectorAll("form[data-origen-modulo]").forEach(function (formulario) {
      var modulo = formulario.getAttribute("data-origen-modulo");
      var clave = "deuda-origen:" + modulo;
      var guardado = null;
      try {
        guardado = JSON.parse(sessionStorage.getItem(clave) || "null");
      } catch (error) {
        guardado = null;
      }
      // La clave nueva manda; la antigua es solo respaldo.
      if (pendiente && pendiente.form_data) {
        guardado = pendiente.form_data;
      }
      if (!guardado) {
        return;
      }
      restaurarDatos(formulario, guardado);

      // La especificación pide marcar SI por defecto al regresar. No se toca la
      // validación de categoría: solo se preselecciona la respuesta.
      var opcionSi = formulario.querySelector("[data-vincular-si]");
      if (opcionSi) {
        opcionSi.checked = true;
        opcionSi.dispatchEvent(new Event("change", { bubbles: true }));
      }
      var deudaId = parametros.get("deuda_id");
      var selectorDeuda = formulario.querySelector("[data-deuda-opciones]");
      if (selectorDeuda && deudaId) {
        selectorDeuda.value = deudaId;
        selectorDeuda.dispatchEvent(new Event("change", { bubbles: true }));
      }
      try {
        sessionStorage.removeItem(clave);
      } catch (error) {
        // Nada que limpiar si el almacenamiento no está disponible.
      }
    });
    // La restauración terminó: la clave se elimina una sola vez.
    try {
      sessionStorage.removeItem(CLAVE_PENDIENTE);
    } catch (error) {
      // Sin almacenamiento no hay nada que limpiar.
    }
  }

  // Conservación ante errores de validación del propio formulario.
  document.querySelectorAll("form[data-guardar-formulario]").forEach(function (formulario) {
    var identificador = formulario.getAttribute("data-guardar-formulario");
    var clave = "formulario:" + location.pathname + ":" + identificador;
    var volvioConError = parametros.has("error") || parametros.has("error_gasto");

    if (volvioConError) {
      var guardado = null;
      try {
        guardado = JSON.parse(sessionStorage.getItem(clave) || "null");
      } catch (error) {
        guardado = null;
      }
      if (guardado) {
        restaurarDatos(formulario, guardado);
      }
    }
    try {
      sessionStorage.removeItem(clave);
    } catch (error) {
      // Almacenamiento no disponible: el formulario sigue funcionando igual.
    }

    formulario.addEventListener("submit", function () {
      try {
        sessionStorage.setItem(clave, JSON.stringify(datosFormulario(formulario)));
      } catch (error) {
        // Sin sessionStorage no se pierde ninguna funcionalidad.
      }
    });
  });
})();
