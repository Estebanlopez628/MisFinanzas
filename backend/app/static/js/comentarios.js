/**
 * Cambio de estado en el panel administrativo de reportes (SRS v2.0, 5.5).
 *
 * Al resolver un reporte se actualiza el contador del badge de la tarjeta del
 * dashboard para que el administrador vea el cambio sin recargar la página.
 */
(function () {
  "use strict";

  document.querySelectorAll("[data-estado-reporte]").forEach(function (selector) {
    selector.addEventListener("change", function () {
      var fila = selector.closest("[data-reporte-fila]");
      if (!fila) {
        return;
      }
      fetch("/feedback/" + fila.getAttribute("data-id") + "/estado", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify({ estado: selector.value })
      })
        .then(function (respuesta) {
          if (!respuesta.ok) {
            throw new Error("No se pudo actualizar el estado.");
          }
          return respuesta.json();
        })
        .then(function (cuerpo) {
          document.querySelectorAll("[data-pendientes]").forEach(function (etiqueta) {
            etiqueta.textContent = cuerpo.pendientes;
          });
          document.querySelectorAll("[data-contador-comentarios]").forEach(function (badge) {
            badge.textContent = cuerpo.pendientes;
            badge.classList.toggle("tarjeta__badge--activo", cuerpo.pendientes > 0);
          });
        })
        .catch(function () {
          var aviso = document.querySelector("[data-comentario-error]");
          if (aviso) {
            aviso.textContent = "No se pudo actualizar el estado. Intenta de nuevo.";
            aviso.hidden = false;
          }
        });
    });
  });
})();
