/**
 * Envío de reportes desde «Ayuda y comentarios» (SRS v2.0, sección 5.3).
 *
 * El formulario usa la API JSON de la Fase A. El dispositivo lo detecta el
 * servidor desde el `User-Agent`, así que no se envía desde aquí.
 */
(function () {
  "use strict";

  /**
   * Escapa texto del servidor antes de insertarlo en el DOM.
   *
   * @param {string} texto Texto a mostrar.
   * @returns {string} Texto seguro para HTML.
   */
  function escapar(texto) {
    var nodo = document.createElement("span");
    nodo.textContent = texto || "";
    return nodo.innerHTML;
  }

  /**
   * Pinta el historial de reportes del usuario con su estado actual.
   */
  function cargarMisReportes() {
    var lista = document.querySelector("[data-mis-reportes]");
    if (!lista) {
      return;
    }
    fetch("/api/feedback/mios", {
      headers: { "X-Requested-With": "fetch" }
    })
      .then(function (respuesta) {
        return respuesta.ok ? respuesta.json() : { reportes: [] };
      })
      .then(function (cuerpo) {
        lista.textContent = "";
        var reportes = cuerpo.reportes || [];
        if (!reportes.length) {
          var vacio = document.createElement("li");
          vacio.className = "mis-reportes__vacio";
          vacio.textContent = "Todavía no has enviado ningún reporte.";
          lista.appendChild(vacio);
          return;
        }
        reportes.forEach(function (reporte) {
          var item = document.createElement("li");
          item.className = "mis-reportes__item";
          var resuelto = reporte.estado === "Resuelto";
          item.innerHTML =
            '<div class="mis-reportes__cabecera">' +
            "<strong>" + escapar(reporte.modulo) + "</strong>" +
            '<span class="mis-reportes__estado' + (resuelto ? " mis-reportes__estado--resuelto" : "") + '">' +
            escapar(reporte.estado) + "</span>" +
            "</div>" +
            '<p class="mis-reportes__texto">' + escapar(reporte.descripcion) + "</p>" +
            '<small class="mis-reportes__fecha">' + escapar(reporte.fecha_creacion.slice(0, 10)) + "</small>";
          lista.appendChild(item);
        });
      })
      .catch(function () {
        lista.textContent = "";
        var aviso = document.createElement("li");
        aviso.className = "mis-reportes__vacio";
        aviso.textContent = "No se pudo cargar tu historial. Intenta de nuevo.";
        lista.appendChild(aviso);
      });
  }

  cargarMisReportes();

  document.querySelectorAll("[data-formulario-feedback]").forEach(function (formulario) {
    var exito = formulario.querySelector("[data-feedback-exito]");
    var error = formulario.querySelector("[data-feedback-error]");
    var boton = formulario.querySelector('button[type="submit"]');

    formulario.addEventListener("submit", function (evento) {
      evento.preventDefault();
      if (exito) {
        exito.hidden = true;
      }
      if (error) {
        error.hidden = true;
      }
      var datos = {
        tipo_reporte: formulario.elements.tipo_reporte.value,
        modulo: formulario.elements.modulo.value,
        descripcion: formulario.elements.descripcion.value
      };
      if (boton) {
        boton.disabled = true;
      }
      fetch("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify(datos)
      })
        .then(function (respuesta) {
          if (!respuesta.ok) {
            return respuesta.json().then(function (cuerpo) {
              throw new Error(cuerpo.detail || "No se pudo enviar el reporte.");
            });
          }
          formulario.reset();
          if (exito) {
            exito.hidden = false;
          }
          cargarMisReportes();
        })
        .catch(function (fallo) {
          if (error) {
            error.textContent = fallo.message || "No se pudo enviar el reporte.";
            error.hidden = false;
          }
        })
        .then(function () {
          if (boton) {
            boton.disabled = false;
          }
        });
    });
  });
})();
