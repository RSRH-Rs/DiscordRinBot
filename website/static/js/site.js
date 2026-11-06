/* 官网公共脚本：中英切换、每页的属性文字、导航底线、宽屏侧栏的滚动高亮。 */
window.RinSite = (() => {
    const root = document.documentElement;

    /* 页面用 <script type="application/json" id="attr-i18n"> 提供标题、描述这类没法用成对 span 的文字 */
    function strings() {
        try {
            const el = document.getElementById('attr-i18n');
            return el ? JSON.parse(el.textContent || '{}') : {};
        } catch (e) {
            return {};
        }
    }

    function applyAttrs(lang) {
        const t = strings()[lang];
        if (!t) return;
        if (t.title) document.title = t.title;
        const meta = document.querySelector('meta[name="description"]');
        if (meta && t.description) meta.setAttribute('content', t.description);
        const toggle = document.getElementById('lang-toggle');
        if (toggle && t.toggle) toggle.setAttribute('aria-label', t.toggle);
        document.querySelectorAll('[data-i18n-alt]').forEach(el => {
            const value = t[el.getAttribute('data-i18n-alt')];
            if (value) el.setAttribute('alt', value);
        });
        document.querySelectorAll('[data-i18n-aria]').forEach(el => {
            const value = t[el.getAttribute('data-i18n-aria')];
            if (value) el.setAttribute('aria-label', value);
        });
    }

    function setLang(lang) {
        root.setAttribute('data-lang', lang);
        root.lang = lang === 'zh' ? 'zh-CN' : 'en';
        try { localStorage.setItem('rinbot_lang', lang); } catch (e) {}
        applyAttrs(lang);
        document.dispatchEvent(new CustomEvent('rin:lang', {detail: {lang}}));
    }

    applyAttrs(root.getAttribute('data-lang'));

    /* 宽屏侧栏：滚到哪个区块，就高亮哪个频道 */
    const spyLinks = document.querySelectorAll('[data-spy]');
    if (spyLinks.length && 'IntersectionObserver' in window) {
        const spyIO = new IntersectionObserver(entries => {
            entries.forEach(e => {
                if (!e.isIntersecting) return;
                document.querySelectorAll('[data-spy]').forEach(a => {
                    const on = a.getAttribute('data-spy') === e.target.id;
                    a.classList.toggle('on', on);
                    if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
                });
            });
        }, {rootMargin: '-45% 0px -50% 0px'});
        spyLinks.forEach(a => {
            const target = document.getElementById(a.getAttribute('data-spy'));
            if (target) spyIO.observe(target);
        });
    }

    /* 导航滚动后加一条底线 */
    const nav = document.getElementById('nav');
    if (nav) addEventListener('scroll', () => { nav.classList.toggle('scrolled', scrollY > 8); }, {passive: true});

    return {setLang, applyAttrs};
})();
window.rinSetLang = window.RinSite.setLang;
