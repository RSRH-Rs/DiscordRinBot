/* Appearance: day, follow system (''), or night. The choice is a per-viewer convenience; blocked storage means "follow system". */
window.Theme = (() => {
    const KEY = 'rin-theme';
    const valid = value => value === 'light' || value === 'dark' ? value : '';
    function get() {
        try { return valid(localStorage.getItem(KEY)); } catch { return ''; }
    }
    function mark(value) {
        document.querySelectorAll('[data-theme-set]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeSet === value)));
    }
    function set(value) {
        value = valid(value);
        if (value) document.documentElement.dataset.theme = value; else delete document.documentElement.dataset.theme;
        try { localStorage.setItem(KEY, value); } catch { /* storage blocked: the page still switches */ }
        mark(value);
    }
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-theme-set]').forEach(button => button.addEventListener('click', () => set(button.dataset.themeSet)));
        mark(get());
    });
    return {get, set};
})();
