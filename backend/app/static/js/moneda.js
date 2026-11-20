/**
 * Formato de los campos de pesos mientras se escriben (SRS v1.9).
 *
 * Responsabilidad
 * ---------------
 * Los campos marcados con `data-moneda` muestran separadores de miles al escribir
 * o pegar: `3484000` se ve como `3.484.000`. La coma separa los centavos, como en el
 * formato colombiano. Los porcentajes y las cantidades no llevan la marca y no cambian.
 *
 * El servidor ya acepta ambos formatos (`parsear_monto`), y los cálculos de OLB_BYTE
 * y del planificador leen los puntos de miles, así que el valor visible es el mismo
 * que se envía.
 */
(function () {
  "use strict";

  function formatear(texto) {
    var limpio = String(texto || "").replace(/[^\d,]/g, "");
    var posicionComa = limpio.indexOf(",");
    var entero = posicionComa === -1 ? limpio : limpio.slice(0, posicionComa);
    var decimales = posicionComa === -1 ? null : limpio.slice(posicionComa + 1).replace(/,/g, "").slice(0, 2);

    entero = entero.replace(/^0+(?=\d)/, "");
    var agrupado = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    if (posicionComa === -1) {
      return agrupado;
    }
    return (agrupado || "0") + "," + (decimales || "");
  }

  function cuantosDigitos(texto) {
    return (texto.match(/\d/g) || []).length;
  }

  // Devuelve la posición del cursor que deja la misma cantidad de dígitos a su derecha.
  function posicionCursor(texto, digitosDerecha) {
    var posicion = texto.length;
    var contados = 0;
    while (posicion > 0 && contados < digitosDerecha) {
      posicion -= 1;
      if (/\d/.test(texto.charAt(posicion))) {
        contados += 1;
      }
    }
    return posicion;
  }

  function alEscribir(evento) {
    var campo = evento.target;
    var original = campo.value;
    var formateado = formatear(original);
    if (formateado === original) {
      return;
    }
    var cursor = campo.selectionStart;
    var digitosDerecha = cuantosDigitos(original.slice(cursor === null ? original.length : cursor));
    campo.value = formateado;
    try {
      var nueva = posicionCursor(formateado, digitosDerecha);
      campo.setSelectionRange(nueva, nueva);
    } catch (error) {
      // Algunos navegadores no permiten mover el cursor en este tipo de campo.
    }
  }

  function iniciar() {
    document.querySelectorAll("input[data-moneda]").forEach(function (campo) {
      if (campo.value) {
        campo.value = formatear(campo.value);
      }
      campo.addEventListener("input", alEscribir);
    });
  }

  iniciar();
})();
