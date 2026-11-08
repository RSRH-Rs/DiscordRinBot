/* Ctrl K settings search. Entries are read from the page itself (pages, tabs, setting rows), so they never drift from the UI. */
window.CommandPalette = (() => {
    const el = id => document.getElementById(id);
    const tr = key => DashboardUI.tr(key);
    let shown = [], index = 0, opener = null;
    const shortcutLabel = platform => /Mac|iPhone|iPad/.test(platform) ? '⌘K' : 'Ctrl K';

    function collect(pages) {
        const out = [], seen = new Set();
        const add = entry => { if (!entry.label || seen.has(entry.label)) return; seen.add(entry.label); out.push(entry); };
        for (const page of pages) {
            const {slug, title} = page.dataset, where = page.dataset.group || tr('nav.overview');
            add({label: title, where, slug, tab: null, row: null});
            page.querySelectorAll('[role="tab"][data-tab]').forEach(tab => add({label: `${title} › ${tab.dataset.label}`, where, slug, tab: tab.dataset.tab, row: null}));
            page.querySelectorAll('.row-title').forEach(row => add({label: `${title} › ${row.textContent.trim()}`, where, slug,
                tab: row.closest('[data-panel]')?.dataset.panel ?? null, row}));
        }
        return out;
    }
    function filter(entries, query, limit = 12) {
        const q = query.trim();
        return (q ? entries.filter(e => DashboardExtras.matches(e.label + ' ' + e.where, q)) : entries).slice(0, limit);
    }

    function render() {
        const list = el('palette-list'), input = el('palette-input');
        if (!shown.length) {
            const empty = document.createElement('p');
            empty.className = 'palette-empty'; empty.textContent = tr('palette.empty');
            list.replaceChildren(empty);
            input.setAttribute('aria-activedescendant', '');
            return;
        }
        list.replaceChildren(...shown.map((entry, i) => {
            const item = document.createElement('div');
            item.id = 'palette-opt-' + i; item.className = 'palette-item'; item.dataset.index = String(i);
            item.setAttribute('role', 'option'); item.setAttribute('aria-selected', String(i === index));
            const label = document.createElement('span'); label.textContent = entry.label;
            const where = document.createElement('small'); where.textContent = entry.where;
            item.append(label, where);
            return item;
        }));
        input.setAttribute('aria-activedescendant', 'palette-opt-' + index);
    }
    function update() {
        shown = filter(collect([...document.querySelectorAll('.page[data-slug]')]), el('palette-input').value);
        index = 0;
        render();
    }
    const isOpen = () => !!el('palette') && !el('palette').hidden;
    function open() {
        if (!el('palette')) return;
        opener = document.activeElement;
        el('palette').hidden = false;
        el('palette-input').value = '';
        update();
        el('palette-input').focus();
    }
    function close() {
        if (!isOpen()) return;
        el('palette').hidden = true;
        opener?.focus?.();
    }
    // Goes to the page and tab first; when unsaved changes block the page switch, nothing else happens.
    function jump(entry) {
        close();
        if (!Console.go(entry.slug, entry.tab, {instant: true})) return false;
        DashboardUI.closeSidebar?.(false);
        const row = entry.row?.closest('.row');
        if (row) {
            row.scrollIntoView({block: 'center'});
            row.classList.add('is-flash');
            setTimeout(() => row.classList.remove('is-flash'), 1000);
        }
        return true;
    }

    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') {
            if (e.isComposing || !el('palette')) return;
            e.preventDefault();
            if (isOpen()) close(); else open();
            return;
        }
        if (!isOpen() || e.isComposing) return;
        if (e.key === 'Escape') { e.preventDefault(); close(); }
        else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            if (!shown.length) return;
            index = (index + (e.key === 'ArrowDown' ? 1 : -1) + shown.length) % shown.length;
            render();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (shown[index]) jump(shown[index]);
        }
    });
    document.addEventListener('DOMContentLoaded', () => {
        if (!el('palette')) return;
        el('palette-btn')?.addEventListener('click', open);
        const hint = el('palette-btn')?.querySelector?.('kbd');
        if (hint) hint.textContent = shortcutLabel(navigator.platform);
        el('palette-input').addEventListener('input', update);
        el('palette').addEventListener('click', e => {
            const item = e.target.closest?.('[data-index]');
            if (item) jump(shown[Number(item.dataset.index)]);
            else if (e.target === el('palette')) close();
        });
    });
    return {collect, filter, open, close, jump, shortcutLabel};
})();
