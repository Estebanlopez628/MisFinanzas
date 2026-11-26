/**
 * Service worker de la PWA.
 *
 * Responsabilidad
 * ---------------
 * Cachear los recursos estáticos (CSS, JavaScript e íconos) para acelerar la
 * carga y permitir que la interfaz se vea bien con red lenta.
 *
 * Decisión de privacidad: **no se cachean documentos HTML** porque contienen
 * datos financieros del usuario autenticado. Las navegaciones van siempre a la
 * red, de modo que cerrar sesión no deja páginas privadas en el caché.
 */

"use strict";

var CACHE = "olb-finanzas-v155";
var RECURSOS = [
  "/estaticos/css/estilos.css",
  "/estaticos/js/app.js",
  "/estaticos/js/finanzas.js",
  "/estaticos/js/olb_byte.js",
  "/estaticos/js/factura.js",
  "/estaticos/js/vendor/html-to-image.js",
  "/estaticos/js/perfil.js",
  "/estaticos/js/dona.js",
  "/estaticos/js/moneda.js",
  "/estaticos/js/categorias.js",
  "/estaticos/js/deudas.js",
  "/estaticos/img/favicon.svg",
  "/estaticos/img/icono-180.png",
  "/estaticos/img/icono-192.png",
  "/estaticos/img/icono-512.png",
  "/estaticos/img/icono-512-maskable.png"
];

self.addEventListener("install", function (evento) {
  evento.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(RECURSOS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (evento) {
  evento.waitUntil(
    caches.keys().then(function (claves) {
      return Promise.all(
        claves.map(function (clave) {
          return clave === CACHE ? null : caches.delete(clave);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function (evento) {
  var solicitud = evento.request;
  if (solicitud.method !== "GET") {
    return;
  }

  var url = new URL(solicitud.url);
  if (url.origin !== self.location.origin || url.pathname.indexOf("/estaticos/") !== 0) {
    return;
  }

  evento.respondWith(
    caches.match(solicitud).then(function (enCache) {
      if (enCache) {
        return enCache;
      }
      return fetch(solicitud).then(function (respuesta) {
        var copia = respuesta.clone();
        caches.open(CACHE).then(function (cache) {
          cache.put(solicitud, copia);
        });
        return respuesta;
      });
    })
  );
});
