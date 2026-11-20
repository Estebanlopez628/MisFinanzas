/**
 * Interacción de las gráficas tipo dona (capacidad de endeudamiento y cartera).
 *
 * Responsabilidad
 * ---------------
 * Al pasar el cursor, tocar o enfocar un arco, el centro de la dona muestra el
 * nombre, el porcentaje y el valor de ese arco. Al pasar sobre un elemento de la
 * leyenda se resalta el arco correspondiente. Sin JavaScript la dona sigue viéndose
 * con su leyenda y sus `<title>`.
 *
 * Los textos por defecto del centro quedan en `data-valor-defecto` y
 * `data-etiqueta-defecto`; al salir del arco se vuelven a escribir.
 */
(function () {
  "use strict";

  function centro(contenedor) {
    return {
      valor: contenedor.querySelector("[data-centro-valor]"),
      etiqueta: contenedor.querySelector("[data-centro-etiqueta]"),
      detalle: contenedor.querySelector("[data-centro-detalle]")
    };
  }

  function mostrar(contenedor, etiqueta, porcentaje, valor) {
    var partes = centro(contenedor);
    if (partes.valor) {
      partes.valor.textContent = porcentaje;
    }
    if (partes.etiqueta) {
      partes.etiqueta.textContent = etiqueta;
    }
    if (partes.detalle) {
      partes.detalle.textContent = valor;
    }
    contenedor.querySelectorAll(".dona__arco").forEach(function (arco) {
      arco.classList.toggle("dona__arco--activo", arco.getAttribute("data-etiqueta") === etiqueta);
    });
  }

  function restaurar(contenedor) {
    var partes = centro(contenedor);
    if (partes.valor) {
      partes.valor.textContent = partes.valor.getAttribute("data-valor-defecto") || "";
    }
    if (partes.etiqueta) {
      partes.etiqueta.textContent = partes.etiqueta.getAttribute("data-etiqueta-defecto") || "";
    }
    if (partes.detalle) {
      partes.detalle.textContent = "";
    }
    contenedor.querySelectorAll(".dona__arco--activo").forEach(function (arco) {
      arco.classList.remove("dona__arco--activo");
    });
  }

  function iniciar(contenedor) {
    var fijado = false;

    contenedor.querySelectorAll(".dona__arco").forEach(function (arco) {
      var datos = function () {
        return [
          arco.getAttribute("data-etiqueta") || "",
          arco.getAttribute("data-porcentaje") || "",
          arco.getAttribute("data-valor") || ""
        ];
      };
      arco.addEventListener("mouseenter", function () {
        if (!fijado) {
          mostrar.apply(null, [contenedor].concat(datos()));
        }
      });
      arco.addEventListener("mouseleave", function () {
        if (!fijado) {
          restaurar(contenedor);
        }
      });
      arco.addEventListener("focus", function () {
        mostrar.apply(null, [contenedor].concat(datos()));
      });
      arco.addEventListener("blur", function () {
        if (!fijado) {
          restaurar(contenedor);
        }
      });
      // En celular no hay cursor: el toque fija el arco. Tocar el mismo arco de nuevo
      // lo quita; tocar otro cambia la selección. Tocar el centro o el fondo no hace nada.
      arco.addEventListener("click", function () {
        var yaActivo = arco.classList.contains("dona__arco--activo");
        if (fijado && yaActivo) {
          fijado = false;
          restaurar(contenedor);
          return;
        }
        fijado = true;
        mostrar.apply(null, [contenedor].concat(datos()));
      });
    });

    contenedor.querySelectorAll("[data-leyenda-etiqueta]").forEach(function (elemento) {
      var etiqueta = elemento.getAttribute("data-leyenda-etiqueta");
      var arco = contenedor.querySelector(".dona__arco[data-etiqueta='" + etiqueta.replace(/'/g, "\\'") + "']");
      if (!arco) {
        return;
      }
      elemento.addEventListener("mouseenter", function () {
        if (!fijado) {
          mostrar(contenedor, etiqueta, arco.getAttribute("data-porcentaje") || "", arco.getAttribute("data-valor") || "");
        }
      });
      elemento.addEventListener("mouseleave", function () {
        if (!fijado) {
          restaurar(contenedor);
        }
      });
    });

  }

  document.querySelectorAll("[data-dona-contenedor]").forEach(iniciar);
})();
