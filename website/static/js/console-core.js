/* Shared console runtime: api, toast, caches, module pages, duration fields, polling. */
window.Console = (() => {
    const tr = (key, vars) => DashboardUI.tr(key, vars);
    const el = id => document.getElementById(id);
    const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

    async function request(url, method = 'GET', body = null) {
        const options = {method, headers: {'Content-Type': 'application/json'}};
        if (body !== null) options.body = JSON.stringify(body);
        const response = await fetch(url, options);
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.error || tr('common.request_failed', {status: response.status}));
        }
        return response.json();
    }
    const api = (path, method, body) => request(`/api/guild/${window.GID}${path}`, method, body);
    const apiGlobal = (path, method, body) => request(path, method, body);

    let toastTimer = null;
    function toast(message, kind = 'info') {
        const node = el('toast'); if (!node) return;
        node.textContent = message;
        node.className = 'toast is-shown' + (kind === 'info' ? '' : ' toast--' + kind);
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => node.classList.remove('is-shown'), kind === 'bad' ? 6000 : 3000);
    }

    const caches = {};
    function cached(name, path) {
        return () => {
            const entry = caches[name] ||= {};
            if (entry.value) return Promise.resolve(entry.value);
            entry.pending ||= api(path).then(value => { entry.value = value; return value; }).finally(() => { entry.pending = null; });
            return entry.pending;
        };
    }
    const channels = cached('channels', '/channels');
    const roles = cached('roles', '/roles');
    const commands = cached('commands', '/commands');
    const channelName = (id, list) => list.find(c => String(c.id) === String(id))?.name ?? null;
    function channelOptions(select, list, selected, emptyKey = 'common.not_set') {
        select.replaceChildren(new Option(tr(emptyKey), '0'), ...list.map(c => new Option('# ' + c.name, c.id, false, String(c.id) === String(selected))));
        if (!list.some(c => String(c.id) === String(selected))) select.value = '0';
    }
    function roleOptions(select, list, selected, emptyKey = 'common.no_limit') {
        select.replaceChildren(new Option(tr(emptyKey), '0'), ...list.map(r => new Option('@ ' + r.name, r.id, false, String(r.id) === String(selected))));
        if (!list.some(r => String(r.id) === String(selected))) select.value = '0';
    }

    /* ── Duration fields: segmented presets + custom amount/unit, synced to a hidden number input ── */
    const UNITS = {minute: 60, hour: 3600, day: 86400};
    const PRESETS = [60, 300, 3600, 86400];
    const duration = {
        split(seconds) {
            seconds = Math.max(0, Number(seconds) || 0);
            const preset = PRESETS.includes(seconds) ? seconds : null;
            const unit = ['day', 'hour', 'minute'].find(u => seconds && seconds % UNITS[u] === 0) || 'minute';
            return {preset, amount: Math.round(seconds / UNITS[unit]), unit: preset ? (seconds % 3600 ? 'minute' : seconds % 86400 ? 'hour' : 'day') : unit};
        },
        join: (amount, unit) => Math.round(Number(amount) * UNITS[unit]),
        mount(seg) {
            const input = el(seg.dataset.for);
            const options = PRESETS.map(value => {
                const b = document.createElement('button');
                b.type = 'button'; b.className = 'seg-option'; b.dataset.value = value;
                b.textContent = tr('duration.preset_' + value);
                return b;
            });
            const custom = document.createElement('button');
            custom.type = 'button'; custom.className = 'seg-option'; custom.textContent = tr('duration.custom');
            const box = document.createElement('div'); box.className = 'seg-custom'; box.hidden = true;
            const amount = document.createElement('input');
            amount.type = 'number'; amount.className = 'num'; amount.min = '1'; amount.setAttribute('data-draft-ignore', '');
            amount.setAttribute('aria-label', tr('duration.amount'));
            const unit = document.createElement('select');
            unit.className = 'select'; unit.setAttribute('data-draft-ignore', ''); unit.setAttribute('aria-label', tr('duration.unit'));
            for (const u of Object.keys(UNITS)) unit.append(new Option(tr('duration.' + u), u));
            box.append(amount, unit);
            seg.replaceChildren(...options, custom);
            seg.after(box);
            const write = seconds => { input.value = String(seconds); input.dispatchEvent(new Event('input', {bubbles: true})); input.dispatchEvent(new Event('change', {bubbles: true})); };
            const show = () => {
                const parts = duration.split(input.value), isCustom = parts.preset === null || seg.dataset.custom === 'true';
                options.forEach(b => b.setAttribute('aria-pressed', String(!isCustom && Number(b.dataset.value) === parts.preset)));
                custom.setAttribute('aria-pressed', String(isCustom));
                box.hidden = !isCustom;
                if (isCustom) { amount.value = parts.amount; unit.value = parts.unit; }
            };
            options.forEach(b => b.addEventListener('click', () => { seg.dataset.custom = 'false'; write(b.dataset.value); show(); }));
            custom.addEventListener('click', () => { seg.dataset.custom = 'true'; show(); amount.focus(); });
            const fromCustom = () => { if (amount.value) write(duration.join(amount.value, unit.value)); };
            amount.addEventListener('input', fromCustom); unit.addEventListener('change', fromCustom);
            input.addEventListener('change', () => { if (document.activeElement !== amount) show(); });
            show();
            return {show};
        },
        check(input) {
            if (input.disabled) return;
            const value = Number(input.value), min = Number(input.min), max = Number(input.max);
            if (!Number.isFinite(value) || (input.min && value < min) || (input.max && value > max)) {
                throw new Error(tr('duration.out_of_range', {min: duration.label(min), max: duration.label(max)}));
            }
        },
        label(seconds) {
            const {amount, unit} = duration.split(seconds);
            return amount + ' ' + tr('duration.' + unit);
        },
    };

    /* ── Rows that depend on a switch ── */
    function dependencies(root = document) {
        root.querySelectorAll('[data-depends-on]').forEach(row => {
            const source = el(row.dataset.dependsOn); if (!source) return;
            const apply = () => {
                const on = source.checked && !source.closest('[aria-disabled="true"]');
                row.setAttribute('aria-disabled', String(!on));
                row.querySelectorAll('input,select,textarea,button').forEach(control => { control.disabled = !on; });
            };
            if (!row.dataset.dependsReady) { row.dataset.dependsReady = 'true'; source.addEventListener('change', () => dependencies(root)); }
            apply();
        });
        root.querySelectorAll('[data-master-hint]').forEach(hint => {
            const source = el(hint.dataset.masterHint);
            if (source) hint.hidden = source.checked;
        });
    }

    /* ── Module pages ── */
    const modules = new Map();
    function module(def) {
        const state = {def, loaded: false, pending: null};
        modules.set(def.slug, state);
        if (def.save) DashboardUI.onSave('pg-' + def.slug, async () => { await def.save(); toast(tr('toast.saved'), 'ok'); refreshModules(); });
        return state;
    }
    function load(slug) {
        const state = modules.get(slug);
        if (!state?.def.load || state.loaded) return Promise.resolve();
        if (state.pending) return state.pending;
        const root = el('pg-' + slug);
        const run = () => {
            state.pending = DashboardUI.loading(root, async () => {
                await state.def.load();
                state.loaded = true;
                window.DashboardExtras?.refreshSelects?.();
                window.DashboardPreview?.refresh?.();
                dependencies(root);
            }, run).finally(() => { state.pending = null; });
            return state.pending;
        };
        return run();
    }
    function invalidate(slug) {
        const state = modules.get(slug);
        if (state && !DashboardUI.dirty('pg-' + slug)) state.loaded = false;
    }
    let router = null;
    function show(slug, initial) {
        window.DashboardExtras?.closeSelects?.();
        DashboardUI.closeSidebar(false);
        document.querySelectorAll('.page').forEach(page => page.classList.toggle('is-active', page.dataset.slug === slug));
        document.querySelectorAll('.load-feedback[data-for-module]').forEach(f => { f.hidden = f.dataset.forModule !== 'pg-' + slug; });
        document.querySelectorAll('#side-modules [data-mod]').forEach(link => {
            if (link.dataset.mod === slug) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
        });
        const page = el('pg-' + slug), name = page?.dataset.title || '';
        const title = el('page-title'); if (title) title.textContent = name;
        const home = slug === 'overview';
        const group = el('crumb-group'); if (group) { group.hidden = home || !page?.dataset.group; group.textContent = page?.dataset.group || ''; }
        const current = el('crumb-current'); if (current) { current.hidden = home; current.textContent = name; }
        document.title = tr('title.page', {page: name, guild: document.body?.dataset.currentGuild || ''});
        const heading = page?.querySelector('h2');
        if (heading && !initial) { heading.tabIndex = -1; heading.focus({preventScroll: true}); }
        el('main')?.scrollTo(0, 0);
        load(slug);
        document.dispatchEvent(new CustomEvent('console:page', {detail: {slug}}));
    }
    const go = (slug, tab = null) => router?.navigate(slug, {tab}) || false;
    // Shows one tab panel of a page; unknown tabs fall back to the first. Pages without tabs return null.
    function selectTab(slug, tab) {
        const page = el('pg-' + slug); if (!page) return null;
        const panels = [...page.querySelectorAll('[data-panel]')]; if (!panels.length) return null;
        const active = panels.find(p => p.dataset.panel === tab) || panels[0];
        panels.forEach(p => { p.hidden = p !== active; });
        page.querySelectorAll('[role="tab"][data-tab]').forEach(t => {
            const on = t.dataset.tab === active.dataset.panel;
            t.setAttribute('aria-selected', String(on));
            t.tabIndex = on ? 0 : -1;
        });
        return active.dataset.panel;
    }
    // A dot on every tab whose panel holds unsaved changes.
    function markTabs() {
        document.querySelectorAll('.page[data-slug]').forEach(page => {
            page.querySelectorAll('[role="tab"][data-tab]').forEach(tab => {
                const panel = page.querySelector(`[data-panel="${tab.dataset.tab}"]`), dot = tab.querySelector('.tab-dot');
                if (dot) dot.hidden = !DashboardUI.changedWithin(page, panel);
            });
        });
    }
    // Switching server from the sidebar obeys the same draft guard as in-page links; invites open a new tab and need none.
    function leaveClick(event) {
        const link = event.target.closest?.('#switcher-pop a');
        if (!link || link.target === '_blank') return;
        if (!DashboardUI.confirmLeave([...document.querySelectorAll('[data-draft]')])) { event.preventDefault(); return; }
        if (router && link.dataset.guild) link.href = '/dashboard/server/' + link.dataset.guild + '#' + router.current();
    }

    /* ── Module status polling (server pages only) ── */
    let signature = null;
    function dotState(m) {
        if (m.loaded !== true) return m.loaded === false ? 'off' : 'unknown';
        if (m.config_state === 'unknown') return 'unknown';
        if (m.config_state === 'disabled') return 'off';
        if (m.config_state === 'unconfigured') return 'warn';
        return 'on';
    }
    function stateLabel(m) {
        if (m.loaded === false) return tr('module_state.not_loaded');
        if (m.loaded !== true) return tr('status.unknown');
        return tr('module_state.' + (m.config_state || 'available'));
    }
    function setBotStatus(state) {
        document.querySelectorAll('[data-bot-status]').forEach(node => {
            node.dataset.state = state;
            node.textContent = tr('status.' + state);
        });
    }
    async function refreshModules() {
        if (!window.GID) return;
        try {
            const data = await api('/modules');
            setBotStatus(data.bot_state);
            const next = JSON.stringify(data.modules);
            if (next === signature) return;
            signature = next;
            for (const m of data.modules) {
                document.querySelectorAll(`[data-dot="${m.slug}"]`).forEach(dot => {
                    dot.className = 'nav-dot nav-dot--' + dotState(m);
                    dot.setAttribute('aria-label', stateLabel(m));
                    dot.title = stateLabel(m);
                });
            }
            document.dispatchEvent(new CustomEvent('console:modules', {detail: data}));
        } catch (e) {
            signature = null;
            setBotStatus('unknown');
            document.dispatchEvent(new CustomEvent('console:modules-failed', {detail: e}));
        }
    }

    /* ── Server list search (dashboard home) ── */
    function serverSearch() {
        const search = el('server-search'); if (!search) return;
        const cards = [...document.querySelectorAll('[data-guild-name]')];
        const filter = () => {
            let count = 0;
            cards.forEach(card => {
                card.hidden = !DashboardExtras.matches(card.dataset.guildName + ' ' + card.dataset.guildId, search.value);
                if (!card.hidden) count++;
            });
            document.querySelectorAll('[data-server-group]').forEach(group => {
                const visible = [...group.querySelectorAll('[data-guild-name]')].filter(card => !card.hidden).length;
                group.hidden = !visible;
                group.querySelector('[data-count]').textContent = visible;
            });
            el('server-search-result').textContent = search.value ? tr('servers.found', {n: count}) : '';
            el('server-no-results').hidden = count > 0;
        };
        search.addEventListener('input', filter);
        el('server-search-clear').addEventListener('click', () => { search.value = ''; filter(); search.focus(); });
        filter();
    }

    document.addEventListener('DOMContentLoaded', () => {
        serverSearch();
        document.addEventListener('click', leaveClick);
        const pages = [...document.querySelectorAll('.page[data-slug]')];
        if (pages.length) {
            router = DashboardExtras.createHashRouter({
                ids: pages.map(p => p.dataset.slug), fallback: pages[0].dataset.slug, show,
                canLeave: slug => DashboardUI.confirmSwitch('pg-' + slug), showTab: selectTab,
            });
            document.addEventListener('click', e => {
                const tab = e.target.closest('a[data-tab]');
                if (!tab || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
                e.preventDefault();
                router.navigate(tab.closest('.page').dataset.slug, {tab: tab.dataset.tab});
            });
            document.addEventListener('keydown', e => {
                const tab = e.target.closest?.('[role="tablist"] [data-tab]');
                if (!tab || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
                const tabs = [...tab.parentElement.querySelectorAll('[data-tab]')];
                const next = tabs[(tabs.indexOf(tab) + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
                e.preventDefault(); next.focus();
            });
            document.addEventListener('dashboard:drafts-changed', markTabs);
            document.addEventListener('click', e => {
                const link = e.target.closest('a[data-mod]');
                if (!link || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
                e.preventDefault();
                if (router.current() === link.dataset.mod) DashboardUI.closeSidebar(false); else go(link.dataset.mod);
            });
        }
        document.querySelectorAll('[data-duration]').forEach(seg => duration.mount(seg));
        dependencies();
        if (window.GID) {
            refreshModules();
            setInterval(() => { if (!document.hidden) refreshModules(); }, 30000);
        }
    });

    return {tr, api, apiGlobal, toast, escapeHtml, channels, roles, commands, channelName, channelOptions, roleOptions,
        duration, dependencies, module, load, invalidate, go, selectTab, leaveClick, refreshModules, stateLabel, dotState};
})();
