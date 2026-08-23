const CACHE_NAME = 'pmit-20260823_1553';
const CORE = [
  './', './index.html', './manifest.json',
  './assets/tokens.css', './assets/layout.css', './assets/app.js',
  './data/meta.json', './data/disposition.json', './data/candidates.json',
  './icon-192.png', './icon-512.png'
];
const SWR = ['/data/macro.json', '/data/news.json'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE).catch(() => undefined)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

async function putInCache(request, response) {
  if (response && response.ok) {
    const cache = await caches.open(CACHE_NAME);
    await cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  const path = url.pathname;
  const isNavigation = event.request.mode === 'navigate' || event.request.destination === 'document' || path.endsWith('/');
  const isMeta = path.endsWith('/data/meta.json');
  const isSWR = SWR.some((prefix) => path.endsWith(prefix));
  const isData = path.includes('/data/') && path.endsWith('.json');

  if (isMeta) {
    event.respondWith(fetch(event.request).then((response) => putInCache(event.request, response)).catch(() => caches.match(event.request)));
    return;
  }
  if (isSWR) {
    event.respondWith(caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(event.request);
      const network = fetch(event.request).then((response) => putInCache(event.request, response)).catch(() => cached);
      return cached || network;
    }));
    return;
  }
  if (isNavigation) {
    event.respondWith(fetch(event.request).then((response) => putInCache(event.request, response)).catch(() => caches.match(event.request).then((cached) => cached || caches.match('./index.html'))));
    return;
  }
  if (isData || event.request.destination === 'script' || event.request.destination === 'style' || event.request.destination === 'image') {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => putInCache(event.request, response))));
  }
});
