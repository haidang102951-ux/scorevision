const CACHE_NAME = 'scorevision-v3';
const ASSETS = [
    './',
    './index.html',
    './tai-app.html',
    './lich-dau.html',
    './du-doan.html',
    './bang-xep-hang.html',
    './thong-ke.html',
    './tin-nong.html',
    './ket-qua.html',
    './livescore.html',
    './gop-y.html',
    './manifest.json',
    'https://cdn-icons-png.flaticon.com/512/1041/1041916.png'
];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(ASSETS);
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

self.addEventListener('fetch', e => {
    e.respondWith(
        caches.match(e.request).then(r => {
            return r || fetch(e.request).then(res => {
                return caches.open(CACHE_NAME).then(cache => {
                    cache.put(e.request, res.clone());
                    return res;
                });
            });
        })
    );
});
