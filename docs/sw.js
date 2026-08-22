const CACHE_NAME = 'premarket-v3';
const SHELL_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './embed/att.html',
  './embed/fin.html',
  './embed/rev.html',
  './icon-192.png',
  './icon-512.png',
  './data_meta.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // Skip cross-origin ads, tracking, or external APIs
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes('/data/night_session/')) return;

  const isDataRequest = url.pathname.endsWith('.json') || url.pathname.includes('/data/');

  if (isDataRequest) {
    // Network-first strategy for dynamic data with 5-minute TTL / cache fallback
    event.respondWith(
      fetch(event.request)
        .then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return networkResponse;
        })
        .catch(() => caches.match(event.request))
    );
  } else {
    // Stale-while-revalidate for Shell assets
    event.respondWith(
      caches.open(CACHE_NAME).then(cache => {
        return cache.match(event.request).then(cachedResponse => {
          const fetchPromise = fetch(event.request)
            .then(networkResponse => {
              if (networkResponse && networkResponse.status === 200) {
                cache.put(event.request, networkResponse.clone());
              }
              return networkResponse;
            })
            .catch(() => cachedResponse || cache.match('./index.html'));

          return cachedResponse || fetchPromise;
        });
      })
    );
  }
});
