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

  // Ir a registrar la deuda: se guardan los datos y el módulo de origen.
  document.querySelectorAll("[data-ir-a-deudas]").forEach(function (enlace) {
    enlace.addEventListener("click", function () {
      var formulario = enlace.closest("form");
      var modulo = enlace.getAttribute("data-origen");
      if (!formulario || !modulo) {
        return;
      }
      try {
        sessionStorage.setItem(
          "deuda-origen:" + modulo,
          JSON.stringify(datosFormulario(formulario))
        );
      } catch (error) {
        // Sin sessionStorage el formulario sigue funcionando igual.
      }
    });
  });

  // Restauración al volver de registrar la deuda.
  var parametros = new URLSearchParams(location.search);
  if (parametros.has("guardado_deuda")) {
    document.querySelectorAll("form[data-origen-modulo]").forEach(function (formulario) {
      var modulo = formulario.getAttribute("data-origen-modulo");
      var clave = "deuda-origen:" + modulo;
      var guardado = null;
      try {
        guardado = JSON.parse(sessionStorage.getItem(clave) || "null");
      } catch (error) {
        guardado = null;
      }
      if (!guardado) {
        return;
      }
      restaurarDatos(formulario, guardado);

      // La especificación pide marcar SI por defecto al regresar.
      var opcionSi = formulario.querySelector("[data-vincular-si]");
      if (opcionSi) {
        opcionSi.checked = true;
        opcionSi.dispatchEvent(new Event("change", { bubbles: true }));
      }
      var deudaId = parametros.get("deuda_id");
      var selectorDeuda = formulario.querySelector("[data-deuda-opciones]");
      if (selectorDeuda && deudaId) {
        selectorDeuda.value = deudaId;
      }
      try {
        sessionStorage.removeItem(clave);
      } catch (error) {
        // Nada que limpiar si el almacenamiento no está disponible.
      }
    });
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
