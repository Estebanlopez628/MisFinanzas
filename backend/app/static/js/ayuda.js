/**
 * Envío de reportes desde «Ayuda y comentarios» (SRS v2.0, sección 5.3).
 *
 * El formulario usa la API JSON de la Fase A. El dispositivo lo detecta el
 * servidor desde el `User-Agent`, así que no se envía desde aquí.
 */
(function () {
  "use strict";

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
