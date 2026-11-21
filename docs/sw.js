/* Service worker: deja la pagina instalable y usable sin conexion para lo estatico.
 * Estrategia "red primero, cache de respaldo": asi un cambio en config.js o en el codigo
 * llega apenas hay conexion, y sin conexion se abre la ultima version guardada.
 * No toca Gmail ni el inicio de sesion de Google: esas llamadas siempre van a la red. */
const VERSION = "radiografia-v2";
const ESTATICOS = ["./", "index.html", "app.html", "analisis.js", "cargador.js", "config.js", "chart.umd.min.js",
                   "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(ESTATICOS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;   // Google y Gmail: siempre red
  e.respondWith(
    fetch(req).then((res) => {
      if (res && res.ok) { const copia = res.clone(); caches.open(VERSION).then((c) => c.put(req, copia)); }
      return res;
    }).catch(() => caches.match(req).then((r) => r || caches.match("index.html")))
  );
});
