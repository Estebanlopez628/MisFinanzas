/**
 * Comportamiento de la pestaña «Migración de Cartera» de OLB BYTE.
 *
 * Responsabilidad
 * ---------------
 * - Permitir varias filas de productos con «+ Agregar otro producto».
 * - Abrir WhatsApp directamente desde «Pegar Numero», sin libreta de contactos
 *   ni portapapeles (SRS Migración §4).
 *
 * Toda la validación y los cálculos viven en el servidor; aquí solo se manipula
 * el DOM del formulario.
 */

(function () {
  "use strict";

  var formulario = document.querySelector("[data-migracion-form]");
  if (!formulario) {
    return;
  }

  var lista = formulario.querySelector("[data-lista-productos]");
  var plantilla = formulario.querySelector("[data-plantilla-producto]");
  var mensajeVacio = formulario.querySelector("[data-lista-vacia]");
  var botonAgregar = formulario.querySelector("[data-agregar-producto]");
  var campoTelefono = formulario.querySelector("[data-cliente-telefono]");
  var botonNumero = formulario.querySelector("[data-pegar-numero]");

  /** Actualiza el aviso de tabla vacía según las filas visibles. */
  function actualizarVacia() {
    if (!mensajeVacio || !lista) {
      return;
    }
    mensajeVacio.hidden = lista.querySelectorAll("[data-fila-producto]").length > 0;
  }

  /** Agrega una fila de producto en blanco al final de la tabla. */
  function agregarProducto() {
    if (!lista || !plantilla) {
      return;
    }
    lista.appendChild(plantilla.content.cloneNode(true));
    actualizarVacia();
    var filas = lista.querySelectorAll("[data-fila-producto]");
    var ultima = filas[filas.length - 1];
    if (ultima) {
      var campo = ultima.querySelector('input[name="producto_nombre"]');
      if (campo) {
        campo.focus();
      }
    }
  }

  if (botonAgregar) {
    botonAgregar.addEventListener("click", agregarProducto);
  }

  if (lista) {
    lista.addEventListener("click", function (evento) {
      var objetivo = evento.target instanceof Element ? evento.target : null;
      if (!objetivo) {
        return;
      }
      var boton = objetivo.closest("[data-eliminar-producto]");
      if (!boton) {
        return;
      }
      var fila = boton.closest("[data-fila-producto]");
      if (fila && fila.parentNode) {
        fila.parentNode.removeChild(fila);
      }
      actualizarVacia();
    });
  }

  /** Normaliza el celular mientras se escribe o se pega. */
  function normalizarTelefono(texto) {
    var digitos = String(texto || "").replace(/\D/g, "");
    if (digitos.length === 12 && digitos.indexOf("57") === 0) {
      digitos = digitos.slice(2);
    }
    return digitos.slice(0, 10);
  }

  if (campoTelefono) {
    campoTelefono.addEventListener("input", function () {
      campoTelefono.value = normalizarTelefono(campoTelefono.value);
    });
    campoTelefono.addEventListener("blur", function () {
      campoTelefono.value = normalizarTelefono(campoTelefono.value);
    });
  }

  /** Abre WhatsApp para que el usuario copie el número del contacto. */
  function abrirWhatsappNumero() {
    var texto = encodeURIComponent("Hola");
    if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
      window.location.href = "whatsapp://send?text=" + texto;
    } else {
      window.open(
        "https://wa.me/?text=" + texto,
        "_blank",
        "noopener,noreferrer"
      );
    }
  }

  if (botonNumero) {
    botonNumero.addEventListener("click", abrirWhatsappNumero);
  }

  actualizarVacia();
})();
