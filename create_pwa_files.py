import json

# 1. إنشاء manifest.json
manifest = {
    "name": "Friday - English Learning AI",
    "short_name": "Friday AI",
    "description": "تعلم اللغة الإنجليزية مع مساعد AI الصوتي",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#4F46E5",
    "orientation": "portrait-primary",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
    ],
    "categories": ["education", "productivity"],
    "lang": "ar",
    "dir": "rtl"
}

with open('manifest.json', 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

# 2. إنشاء service-worker.js
sw_content = """// Service Worker - Friday AI PWA
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
"""

with open('service-worker.js', 'w', encoding='utf-8') as f:
    f.write(sw_content)

print("✅ تم إنشاء manifest.json و service-worker.js بنجاح!")