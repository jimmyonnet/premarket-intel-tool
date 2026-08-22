const CACHE = 'premarket-v1';
const PRECACHE = [
  './',
  './index.html',
  './manifest.json',
  './embed/att.html',
  './embed/fin.html',
  './embed/rev.html',
  './icon-192.png',
  './icon-512.png'
];
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  // 只快取同源；夜盤 jsonl 與 chengwaye 站內 / Google AdSense / GA 全部略過
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes('/data/night_session/')) return;
  e.respondWith(
    caches.open(CACHE).then(c =>
      c.match(e.request).then(r =>
        r ? r : fetch(e.request).then(resp => {
          // 只快取靜態資源（HTML/CSS/字體/圖片）
          if (resp.ok && /text\/html|application\/javascript|text\/css|image\//.test(resp.headers.get('content-type') || '')) {
            c.put(e.request, resp.clone());
          }
          return resp;
        }).catch(() => r || caches.match('./index.html'))
      )
    )
  );
});
