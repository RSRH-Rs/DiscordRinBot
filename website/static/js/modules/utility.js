/* Command toggles: every switch saves immediately; bulk switches only touch the current filter. */
window.CommandToggles = (() => {
    const {tr} = Console;
    const el = id => document.getElementById(id);
    let data = null, saving = false;

    const cogLabel = cog => { const key = 'cogs.' + cog, label = tr(key); return label === key ? cog : label; };
    function matching() {
        const query = el('command-search').value, state = el('command-filter').value;
        return (data || []).filter(c => DashboardExtras.matches(c.name + ' ' + c.desc + ' ' + c.cog + ' ' + cogLabel(c.cog), query) &&
            (state === 'all' || (state === 'enabled' ? c.enabled : !c.enabled)));
    }
    function toggleSwitch(checked, disabled, label, onChange) {
        const wrap = document.createElement('label'); wrap.className = 'tog';
        const input = document.createElement('input');
        input.type = 'checkbox'; input.checked = checked; input.disabled = disabled;
        input.setAttribute('role', 'switch'); input.setAttribute('aria-label', label); input.setAttribute('data-draft-ignore', '');
        input.addEventListener('change', () => onChange(input.checked));
        const track = document.createElement('span'); track.className = 'tog-track';
        wrap.append(input, track);
        return wrap;
    }
    function render() {
        if (!data) return;
        const box = el('util-commands');
        const filtering = !!el('command-search').value.trim() || el('command-filter').value !== 'all';
        const visible = matching(), groups = new Map();
        visible.forEach(c => { if (!groups.has(c.cog)) groups.set(c.cog, []); groups.get(c.cog).push(c); });
        box.replaceChildren();
        for (const [cog, commands] of groups) {
            const group = document.createElement('details');
            group.className = 'fold cmd-group'; group.open = true; group.dataset.cog = cog;
            const summary = document.createElement('summary');
            summary.textContent = cogLabel(cog) + ' · ' + tr('utility.group_count', {n: commands.length});
            const editable = commands.filter(c => !c.protected), allOn = editable.length > 0 && editable.every(c => c.enabled);
            const bulk = document.createElement('button');
            bulk.type = 'button'; bulk.className = 'btn btn--text cmd-bulk';
            bulk.textContent = tr(allOn ? (filtering ? 'utility.bulk_off_filtered' : 'utility.bulk_off') : (filtering ? 'utility.bulk_on_filtered' : 'utility.bulk_on'), {n: editable.length});
            bulk.disabled = saving || !editable.length;
            bulk.addEventListener('click', e => { e.preventDefault(); toggleCategory(cog, !allOn); });
            summary.append(bulk);
            const list = document.createElement('div'); list.className = 'list';
            for (const c of commands) {
                const row = document.createElement('div'); row.className = 'row row--switch'; row.id = 'cr-' + c.name;
                const text = document.createElement('div'); text.className = 'row-text';
                const name = document.createElement('span'); name.className = 'row-title'; name.textContent = '/' + c.name;
                const desc = document.createElement('span'); desc.className = 'row-hint'; desc.textContent = c.desc + (c.protected ? tr('utility.protected') : '');
                text.append(name, desc);
                row.append(text, toggleSwitch(c.enabled, c.protected || saving, tr('utility.toggle_label', {name: c.name}), checked => toggleCommand(c.name, checked)));
                list.append(row);
            }
            group.append(summary, list);
            box.append(group);
        }
        if (!visible.length) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = tr('utility.no_match'); box.append(empty); }
        box.inert = saving;
        el('util-search-status').textContent = tr('utility.showing', {n: visible.length, total: data.length});
        el('util-summary').textContent = tr('utility.summary', {total: data.length, on: data.filter(c => c.enabled).length});
    }
    async function change(commands, enabled) {
        if (saving || !commands.length) return;
        saving = true;
        el('util-commands').inert = true;
        try {
            const body = commands.length === 1 ? {name: commands[0].name, enabled} : {names: commands.map(c => c.name), enabled};
            const result = await Console.api(commands.length === 1 ? '/commands/toggle' : '/commands/bulk-toggle', 'POST', body);
            if (!result.ok) throw new Error(result.error || tr('utility.failed_plain'));
            commands.forEach(c => { c.enabled = enabled; });
            Console.toast(tr(enabled ? 'utility.turned_on' : 'utility.turned_off', {n: commands.length}), 'ok');
        } catch (e) {
            Console.toast(tr('utility.failed', {reason: e.message}), 'bad');
        } finally { saving = false; render(); }
    }
    const toggleCommand = (name, enabled) => change((data || []).filter(c => c.name === name && !c.protected), enabled);
    const toggleCategory = (cog, enabled) => change(matching().filter(c => c.cog === cog && !c.protected), enabled);

    let loaded = false;
    Console.module({
        slug: 'utility',
        isLoaded: () => loaded,
        async load() { data = await Console.commands(); loaded = true; render(); },
    });
    window.addEventListener('beforeunload', e => { if (saving) { e.preventDefault(); e.returnValue = ''; } });
    document.addEventListener('DOMContentLoaded', () => {
        if (!el('pg-utility')) return;
        el('command-search').addEventListener('input', render);
        el('command-filter').addEventListener('change', render);
    });

    return {cogLabel, render, toggleCommand, toggleCategory, data: () => data, setData: d => { data = d; }, isSaving: () => saving};
})();
