(function () {
    // 1. Top reading progress bar
    const bar = document.createElement('div');
    bar.className = 'sv-progress-bar';
    document.body.prepend(bar);

    function updateProgress() {
        const scrollTop = window.scrollY || document.documentElement.scrollTop;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const pct = docHeight > 0 ? Math.min(100, (scrollTop / docHeight) * 100) : 0;
        bar.style.width = pct + '%';
    }
    window.addEventListener('scroll', updateProgress, { passive: true });
    updateProgress();

    // 2. Smooth Scroll Reveal (GPU-only transform/opacity)
    const targets = document.querySelectorAll('.sv-card, .section, .hero, .intro, .box-thongtin, .disclaimer');
    if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        const io = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('sv-visible');
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });

        targets.forEach((el) => {
            el.classList.add('sv-reveal');
            io.observe(el);
        });
    }
})();
