const CACHE_NAME = 'pmit-20260825_1643-data-3c27e155b6b0ba8a';
const DATA_REVISION = '3c27e155b6b0ba8a';
const SHELL_ASSETS = [
  './', './index.html', './manifest.json',
  './icon-180.png', './icon-192.png', './icon-512.png', './data_meta.json', './data/tw_holidays.json'
];

const isSameOrigin = request => new URL(request.url).origin === self.location.origin;
const isDataRequest = url => url.pathname.endsWith('.json') || url.pathname.includes('/data/');
const isNavigation = (request, url) => request.mode === 'navigate' || request.destination === 'document' || url.pathname.endsWith('.html') || url.pathname.endsWith('/');

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      try {
        await cache.addAll(['./', './index.html', './manifest.json']);
      } catch (err) {
        console.warn('SW core cache warning:', err);
      }
        await Promise.allSettled(SHELL_ASSETS.slice(3).map(url => cache.add(url)));

    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll())
      .then(clients => clients.forEach(client => client.postMessage({ type: 'sw-updated', version: CACHE_NAME, dataRevision: DATA_REVISION })))
  );
});

async function networkFirst(request, fallbackRequest, cacheResponse) {
  try {
    const networkResponse = await fetch(request, { cache: 'no-store' });
    if (networkResponse && networkResponse.ok && cacheResponse) {
      // A response is cached only under the current revision's cache. The
      // data_meta revision provides an additional revalidation key.
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (_) {
    return caches.match(fallbackRequest || request).then(cached => cached || null);
  }
}

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || !isSameOrigin(event.request)) return;
  const url = new URL(event.request.url);
  if (url.pathname.includes('/data/night_session/')) return;

  if (isNavigation(event.request, url)) {
    event.respondWith(networkFirst(event.request, event.request, true));
    return;
  }
  if (isDataRequest(url)) {
    // data_meta and package JSON are never served stale when online. If the
    // network is unavailable, the same revision's cache is still a safe fallback.
    event.respondWith(networkFirst(event.request, event.request, true));
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(cache => cache.match(event.request).then(cached => {
      const revalidate = fetch(event.request).then(response => {
        if (response && response.ok) cache.put(event.request, response.clone());
        return response;
      }).catch(() => cached);
      return cached || revalidate;
    }))
  );
});
