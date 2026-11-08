/* Draft lifecycle, the unsaved-changes bar and the mobile drawer. Nothing is auto-saved. */
window.DashboardUI = (() => {
    const drafts = new Map(), saveHandlers = new Map();
    let menuOpener = null, strings = null, blockedTimer = null;
    const rootOf = id => typeof id === 'string' ? document.getElementById(id) : id;
    const el = id => document.getElementById(id);
    function tr(key, vars = {}) {
        if (strings === null) {
            try { strings = JSON.parse(el('console-strings')?.textContent || '{}'); } catch { strings = {}; }
        }
        const text = strings[key];
        if (text === undefined) { if (globalThis.console) console.warn('missing console string', key); return key; }
        return Object.entries(vars).reduce((out, [name, value]) => out.replaceAll('{' + name + '}', String(value)), text);
    }
    const keyOf = field => field.id || field.name || field.className;
    // Unnamed controls (e.g. log level chips) are told apart by their position in the page.
    const keyed = root => fieldsOf(root).map((field, i) => [keyOf(field) || '#' + i, field]);
    const fieldsOf = root => [...root.querySelectorAll('input,select,textarea')].filter(f => !f.matches('[data-draft-ignore]'));
    const valueOf = field => field.type === 'file' ? [...field.files].map(f => [f.name, f.size, f.lastModified]) :
        /^(checkbox|radio)$/.test(field.type) ? field.checked : field.value;
    const tagsOf = root => [...root.querySelectorAll('[data-tags]')].map(list => [list.id, [...list.querySelectorAll('.chip')].map(c => c.dataset.value)]);
    function snapshot(root) {
        return JSON.stringify([fieldsOf(root).map(f => [keyOf(f), valueOf(f)]), tagsOf(root)]);
    }
    const inline = root => root.dataset?.draftInline !== undefined;
    const barRoots = () => [...drafts.keys()].filter(root => !inline(root));
    function activeRoot() {
        const dirtyRoots = barRoots().filter(dirty);
        return dirtyRoots.find(root => root.classList.contains('is-active')) || dirtyRoots[0] || null;
    }
    function updateBar() {
        const bar = el('unsaved-bar'); if (!bar) return;
        const open = barRoots().some(dirty), busy = [...drafts.values()].some(s => s.saving);
        bar.classList.toggle('is-open', open);
        bar.setAttribute('aria-hidden', String(!open));
        for (const id of ['unsaved-save', 'unsaved-reset']) { const button = el(id); if (button) button.disabled = busy || !open; }
        const text = el('unsaved-text'); if (text && !blockedTimer) text.textContent = tr('bar.unsaved');
        if (!open) { const error = el('unsaved-error'); if (error) { error.hidden = true; error.textContent = ''; } }
    }
    function refresh(root) {
        const state = drafts.get(root);
        if (!state) return;
        const isDirty = snapshot(root) !== state.saved;
        root.classList.toggle('has-unsaved', isDirty);
        if (inline(root)) {
            const hint = root.querySelector('.draft-hint');
            if (hint) hint.textContent = state.saving ? tr('bar.saving') : isDirty ? tr('bar.unsaved') : '';
        }
        updateBar();
        document.dispatchEvent?.(new Event('dashboard:drafts-changed'));
    }
    function register(root) {
        if (drafts.has(root)) return;
        drafts.set(root, {saved: snapshot(root), values: null, tags: null, saving: false});
        record(root);
        if (inline(root) && !root.querySelector('.draft-hint')) {
            const hint = document.createElement('p');
            hint.className = 'draft-hint'; hint.setAttribute('aria-live', 'polite');
            root.append(hint);
        }
        refresh(root);
    }
    function record(root) {
        const state = drafts.get(root);
        state.values = new Map(keyed(root).filter(([, f]) => f.type !== 'file').map(([key, f]) => [key, valueOf(f)]));
        state.tags = new Map(tagsOf(root));
    }
    function clean(id) {
        const root = rootOf(id); if (!root) return;
        register(root);
        drafts.get(root).saved = snapshot(root);
        record(root);
        refresh(root);
    }
    function changed(id) { const root = rootOf(id); if (root) refresh(root); }
    // Whether anything inside one part of a draft (e.g. one tab) differs from the last saved values.
    function changedWithin(id, container) {
        const root = rootOf(id), state = root && drafts.get(root);
        if (!state?.values || !container) return false;
        for (const [key, field] of keyed(root)) {
            if (!container.contains(field)) continue;
            if (field.type === 'file') { if (field.files?.length) return true; continue; }
            if (!state.values.has(key) || valueOf(field) !== state.values.get(key)) return true;
        }
        for (const list of container.querySelectorAll('[data-tags]')) {
            const values = [...list.querySelectorAll('.chip')].map(c => c.dataset.value);
            if (JSON.stringify(values) !== JSON.stringify(state.tags.get(list.id) || [])) return true;
        }
        return false;
    }
    function dirty(id) { const root = rootOf(id), state = drafts.get(root); return !!state && (state.saving || snapshot(root) !== state.saved); }
    function chip(value) {
        const node = document.createElement('span');
        node.className = 'chip'; node.dataset.value = value;
        const label = document.createElement('span'); label.textContent = value;
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'chip-remove';
        remove.setAttribute('aria-label', tr('common.remove_item', {item: value}));
        remove.textContent = '×';
        node.append(label, remove);
        return node;
    }
    function renderTags(list, values) { list.replaceChildren(...values.map(chip)); }
    function reset(id) {
        const root = id ? rootOf(id) : activeRoot();
        const state = root && drafts.get(root);
        if (!state || state.saving) return;
        for (const [key, field] of keyed(root)) {
            if (field.type === 'file' || !state.values.has(key)) continue;
            const saved = state.values.get(key);
            if (valueOf(field) === saved) continue;
            if (/^(checkbox|radio)$/.test(field.type)) field.checked = saved; else field.value = saved;
            field.dispatchEvent(new Event('input', {bubbles: true}));
            field.dispatchEvent(new Event('change', {bubbles: true}));
        }
        for (const list of root.querySelectorAll('[data-tags]')) if (state.tags.has(list.id)) renderTags(list, state.tags.get(list.id));
        refresh(root);
    }
    function onSave(id, fn) { const root = rootOf(id); if (root) { register(root); saveHandlers.set(root, fn); } }
    async function save() {
        const root = activeRoot(), handler = root && saveHandlers.get(root);
        if (!handler || drafts.get(root).saving) return;
        const error = el('unsaved-error');
        if (error) { error.hidden = true; error.textContent = ''; }
        try { await saving(root, handler); clean(root); }
        catch (e) { if (error) { error.textContent = tr('bar.save_failed', {reason: e.message}); error.hidden = false; } }
    }
    function shake() {
        const bar = el('unsaved-bar'), text = el('unsaved-text');
        if (!bar) return;
        bar.classList.remove('is-shaking');
        void bar.offsetWidth;
        bar.classList.add('is-shaking');
        if (text) text.textContent = tr('bar.blocked');
        clearTimeout(blockedTimer);
        blockedTimer = setTimeout(() => { blockedTimer = null; bar.classList.remove('is-shaking'); updateBar(); }, 2000);
    }
    function confirmSwitch(id) { const root = rootOf(id); return confirmLeave(root ? [root] : []); }
    function confirmLeave(roots) {
        if (roots.some(root => drafts.get(root)?.saving)) return false;
        const dirtyRoots = roots.filter(dirty);
        if (!dirtyRoots.length) return true;
        if (dirtyRoots.every(inline)) return window.confirm(tr('bar.leave_confirm'));
        shake();
        return false;
    }
    async function saving(id, action) {
        const root = rootOf(id); if (!root) return action();
        register(root);
        const state = drafts.get(root);
        if (state.saving) return;
        state.saving = true;
        const wasInert = root.inert;
        root.inert = true; root.setAttribute('aria-busy', 'true'); refresh(root);
        try { return await action(); }
        finally { state.saving = false; root.inert = wasInert || !!state.unread; root.removeAttribute('aria-busy'); refresh(root); }
    }
    async function loading(id, action, retry) {
        const root = rootOf(id);
        register(root);
        const state = drafts.get(root);
        state.unread = true;
        const feedbackId = id + '-load-feedback';
        document.getElementById(feedbackId)?.remove();
        root.inert = true;
        root.setAttribute('aria-busy', 'true');
        try { await action(); state.unread = false; clean(root); root.inert = state.saving; }
        catch (e) {
            const feedback = document.createElement('div');
            feedback.id = feedbackId; feedback.className = 'load-feedback'; feedback.setAttribute('role', 'alert');
            if (root.classList.contains('page')) { feedback.dataset.forModule = root.id; feedback.hidden = !root.classList.contains('is-active'); }
            feedback.append(document.createTextNode(tr('common.load_failed')));
            const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn--secondary';
            button.textContent = tr('common.retry'); button.onclick = retry;
            feedback.append(button); root.before(feedback);
            // Keep the unread/default form inert until a successful retry.
        } finally { root.removeAttribute('aria-busy'); }
    }
    const shell = () => document.querySelector('.shell');
    function closeSidebar(restoreFocus = true) {
        shell()?.classList.remove('is-drawer-open');
        el('menuBtn')?.setAttribute('aria-expanded', 'false');
        if (restoreFocus) menuOpener?.focus();
    }
    function toggleSidebar() {
        const root = shell(); if (!root) return;
        if (root.classList.contains('is-drawer-open')) return closeSidebar();
        menuOpener = el('menuBtn');
        root.classList.add('is-drawer-open');
        menuOpener?.setAttribute('aria-expanded', 'true');
        (el('switcher-btn') || root.querySelector('.sidebar a[href],.sidebar button'))?.focus();
    }
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            if (!e.isComposing && activeRoot()) save();
            return;
        }
        const side = document.querySelector('.shell.is-drawer-open .sidebar');
        if (!side) return;
        if (e.key === 'Escape') { e.preventDefault(); closeSidebar(); }
        if (e.key === 'Tab') {
            const focusable = [...side.querySelectorAll('a[href],button,[tabindex="0"]')].filter(f => !f.disabled && f.getClientRects().length);
            const first = focusable[0], last = focusable.at(-1);
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
        }
    });
    window.addEventListener('beforeunload', e => {
        if ([...drafts.keys()].some(dirty)) { e.preventDefault(); e.returnValue = ''; }
    });
    document.addEventListener('click', e => {
        const remove = e.target.closest?.('.chip-remove');
        if (!remove) return;
        const root = remove.closest('[data-draft]');
        remove.closest('.chip').remove();
        if (root) refresh(root);
    });
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-draft]').forEach(register);
        for (const event of ['input', 'change']) document.addEventListener(event, e => {
            const root = e.target.closest('[data-draft]'); if (root) refresh(root);
        });
        el('unsaved-save')?.addEventListener('click', event => { if (window.Console?.busy) Console.busy(event.currentTarget, save); else save(); });
        el('unsaved-reset')?.addEventListener('click', () => reset());
        el('menuBtn')?.addEventListener('click', toggleSidebar);
        document.querySelector('.drawer-backdrop')?.addEventListener('click', () => closeSidebar());
        window.matchMedia('(min-width:860px)').addEventListener('change', e => { if (e.matches) closeSidebar(false); });
    });
    return {tr, snapshot, clean, changed, changedWithin, dirty, confirmSwitch, confirmLeave, saving, loading, onSave, save, reset, shake, renderTags, toggleSidebar, closeSidebar};
})();
