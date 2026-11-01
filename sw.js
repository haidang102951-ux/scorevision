const CACHE_NAME = 'scorevision-v4';
const STATIC_ASSETS = [
    './',
    './favicon.png',
    './logo.png',
    './manifest.json'
];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(STATIC_ASSETS);
        }).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(names => {
            return Promise.all(
                names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n))
            );
        }).then(() => self.clients.claim())
    );
});

// Network-First for HTML & Live Data; Stale-While-Revalidate for Static Assets
self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);

    // Bỏ qua không cache quảng cáo và analytics
    if (url.hostname.includes('googlesyndication') || 
        url.hostname.includes('google-analytics') || 
        url.hostname.includes('googletagmanager') ||
        url.hostname.includes('n6wxm.com')) {
        return;
    }

    // Network-First cho HTML pages và Google Sheets CSV data
    if (e.request.mode === 'navigate' || 
        url.pathname.endsWith('.html') || 
        url.hostname.includes('docs.google.com')) {
        e.respondWith(
            fetch(e.request)
                .then(res => {
                    if (res && res.status === 200) {
                        const copy = res.clone();
                        caches.open(CACHE_NAME).then(cache => cache.put(e.request, copy));
                    }
                    return res;
                })
                .catch(() => caches.match(e.request))
        );
        return;
    }

    // Stale-While-Revalidate cho static assets
    e.respondWith(
        caches.match(e.request).then(cached => {
            const networkFetch = fetch(e.request).then(res => {
                if (res && res.status === 200) {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(e.request, copy));
                }
                return res;
            }).catch(() => cached);
            return cached || networkFetch;
        })
    );
});
