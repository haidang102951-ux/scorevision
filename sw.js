const CACHE_NAME = 'scorevision-v2';
const ASSETS = [
    './',
    './index.html',
    './du-doan.html',
    './bang-xep-hang.html',
    './gop-y.html',
    './gioi-thieu.html',
    './ket-qua.html',
    './lich-dau.html',
    './lien-he.html',
    './livescore.html',
    './thong-ke.html',
    './tin-nong.html',
    './tai-app.html',     // ✅ THÊM DÒNG NÀY LÀ ĐỦ
    './manifest.json',
    './ads.txt'
];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache =>
            cache.addAll(ASSETS).then(() => self.skipWaiting())
        )
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    e.respondWith(
        fetch(e.request)
            .then(res => {
                const resClone = res.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(e.request, resClone));
                return res;
            })
            .catch(() => caches.match(e.request))
    );
});
