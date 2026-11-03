/* Sidebar server switcher: a searchable popover of the viewer's servers. Leaving the page is guarded by Console.leaveClick. */
window.ServerSwitcher = (() => {
    const el = id => document.getElementById(id);
    const items = () => [...document.querySelectorAll('[data-switcher-item]')];
    function filter(query) {
        let count = 0;
        const all = items();
        all.forEach(item => {
            item.hidden = !DashboardExtras.matches(item.dataset.name, query);
            if (!item.hidden) count++;
        });
        document.querySelectorAll('[data-switcher-group]').forEach(group => {
            group.hidden = !all.some(item => item.dataset.group === group.dataset.switcherGroup && !item.hidden);
        });
        const empty = el('switcher-empty'); if (empty) empty.hidden = count > 0;
        return count;
    }
    function isOpen() { const pop = el('switcher-pop'); return !!pop && !pop.hidden; }
    function open() {
        const pop = el('switcher-pop'); if (!pop) return;
        pop.hidden = false;
        el('switcher-btn')?.setAttribute('aria-expanded', 'true');
        const search = el('switcher-search');
        if (search) { search.value = ''; filter(''); search.focus(); }
    }
    function close() {
        if (!isOpen()) return;
        el('switcher-pop').hidden = true;
        el('switcher-btn')?.setAttribute('aria-expanded', 'false');
    }
    document.addEventListener('DOMContentLoaded', () => {
        const button = el('switcher-btn'); if (!button) return;
        button.addEventListener('click', () => { if (isOpen()) close(); else open(); });
        el('switcher-search')?.addEventListener('input', e => filter(e.target.value));
    });
    document.addEventListener('click', e => { if (isOpen() && !el('switcher')?.contains(e.target)) close(); });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && isOpen()) { close(); el('switcher-btn')?.focus(); }
    });
    return {open, close, filter};
})();
