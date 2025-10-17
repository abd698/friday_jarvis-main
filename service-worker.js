// Service Worker - Friday AI PWA
const CACHE_NAME = 'friday-v1';
const urlsToCache = [
  '/',
  '/client.html',
  '/client.css',
  '/client.js',
  '/3000-sentences.html',
  '/sentences-client.js',
  '/podcast.html',
  '/podcast-client.js'
];

self.addEventListener('install', event => {
  console.log('[SW] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .catch(err => console.error('[SW] Cache error:', err))
  );
});

self.addEventListener('activate', event => {
  console.log('[SW] Activating...');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
      .catch(() => caches.match('/client.html'))
  );
});
