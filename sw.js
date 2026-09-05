// Cachea la app para que funcione sin cobertura (Clot).
// Los datos NO pasan por aquí: viven en localStorage y suben a GitHub.
var CACHE = 'sistema-v2';
var ASSETS = ['./', './index.html', './manifest.webmanifest', './icon-180.png', './icon-512.png'];

self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(ASSETS); }).catch(function () {}));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (ks) {
      return Promise.all(ks.map(function (k) { return k === CACHE ? null : caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  // Nunca cachear las llamadas a la API de GitHub.
  if (url.hostname === 'api.github.com') return;
  if (e.request.method !== 'GET') return;

  e.respondWith(
    fetch(e.request)
      .then(function (r) {
        if (r && r.ok && url.origin === self.location.origin) {
          var copy = r.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return r;
      })
      .catch(function () {
        return caches.match(e.request).then(function (m) {
          return m || caches.match('./index.html');
        });
      })
  );
});
