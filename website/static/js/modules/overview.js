/* Server overview: Rin's duty card, attention notices, module cards with config summaries and quick switches. */
window.Overview = (() => {
    const {tr} = Console;
    const TOGGLE_SLUGS = ['welcome', 'automod', 'botlog', 'serverlog'];
    const el = id => document.getElementById(id);

    // Returns {text, warn} built from this server's saved config, or null to fall back to the module blurb.
    // channels === null means the channel list could not be read: never claim a channel was deleted then.
    function summaryText(slug, summary, channels) {
        if (!summary) return null;
        let deleted = false, unknown = false;
        const channel = id => {
            if (channels === null) { unknown = true; return ''; }
            const name = Console.channelName(id, channels);
            if (name === null) deleted = true;
            return name;
        };
        const parts = [];
        let warn = null;
        if (slug === 'welcome') {
            if (!summary.welcome_channel && !summary.farewell_channel && !summary.auto_roles_count) warn = 'overview.welcome.unset';
            if (summary.welcome_channel) parts.push(tr('overview.sends_to', {channel: channel(summary.welcome_channel)}));
            if (summary.auto_roles_count) parts.push(tr('overview.welcome.roles', {n: summary.auto_roles_count}));
            if (summary.farewell_channel) parts.push(tr('overview.welcome.farewell', {channel: channel(summary.farewell_channel)}));
        } else if (slug === 'botlog' || slug === 'serverlog') {
            if (!summary.channel_id) warn = 'overview.log.unset';
            else parts.push(tr('overview.sends_to', {channel: channel(summary.channel_id)}));
        } else if (slug === 'automod') {
            parts.push(tr('overview.automod.rules', {n: summary.rules_on}));
            if (summary.log_channel) parts.push(tr('overview.logs_to', {channel: channel(summary.log_channel)}));
        } else if (slug === 'moderation') {
            parts.push(summary.log_channel ? tr('overview.logs_to', {channel: channel(summary.log_channel)}) : tr('overview.moderation.no_log'));
            if (summary.mute_at) parts.push(tr('overview.moderation.mute_at', {n: summary.mute_at}));
        } else if (slug === 'music') {
            parts.push(summary.notify_channel ? tr('overview.music.notify', {channel: channel(summary.notify_channel)}) : tr('overview.music.default'));
            if (summary.dj_role) parts.push(tr('overview.music.dj'));
        } else if (slug === 'roles') {
            parts.push(summary.panels ? tr('overview.roles.panels', {n: summary.panels}) : tr('overview.roles.none'));
        } else if (slug === 'giveaway') {
            parts.push(summary.active ? tr('overview.giveaway.active', {n: summary.active}) : tr('overview.giveaway.none'));
        } else {
            return null;
        }
        if (unknown) return null;
        if (deleted) return {text: tr('overview.channel_deleted'), warn: true};
        if (warn) return {text: tr(warn), warn: true};
        return {text: parts.join(' · '), warn: false};
    }

    // Modules whose saved config needs the owner's attention (no channel, deleted channel...), in page order, at most three.
    function attention(modules, channels) {
        return modules.map(m => ({slug: m.slug, summary: summaryText(m.slug, m.summary, channels)}))
            .filter(a => a.summary?.warn).slice(0, 3).map(a => ({slug: a.slug, text: a.summary.text}));
    }

    function notice({slug, text}) {
        const line = document.createElement('p');
        line.className = 'notice notice--warn';
        const label = document.createElement('span');
        label.textContent = tr('overview.attention_item', {module: tr('nav.module.' + slug), text});
        const link = document.createElement('a');
        link.href = '#' + slug; link.dataset.mod = slug; link.textContent = tr('overview.attention_go');
        line.append(label, link);
        return line;
    }

    async function toggle(slug, enabled, input) {
        const holder = input.closest('.tog');
        if (DashboardUI.dirty('pg-' + slug)) {
            input.checked = !enabled;
            Console.toast(tr('overview.toggle_blocked'), 'bad');
            return false;
        }
        input.disabled = true; input.dataset.busy = '1';
        holder?.setAttribute('aria-busy', 'true');
        try {
            await Console.api(`/modules/${slug}/enabled`, 'POST', {enabled});
            Console.invalidate(slug);
            Console.refreshModules();
            return true;
        } catch (e) {
            input.checked = !enabled;
            Console.toast(tr('overview.toggle_failed', {reason: e.message}), 'bad');
            return false;
        } finally {
            input.disabled = false; delete input.dataset.busy;
            holder?.removeAttribute('aria-busy');
        }
    }

    function joinDuration(iso) {
        const days = Math.floor((Date.now() - new Date(iso)) / 86400000);
        if (days < 1) return tr('overview.duration.today');
        if (days < 30) return tr('overview.duration.days', {n: days});
        if (days < 365) return tr('overview.duration.months', {n: Math.floor(days / 30)});
        const y = Math.floor(days / 365), m = Math.floor((days % 365) / 30);
        return m ? tr('overview.duration.years_months', {y, m}) : tr('overview.duration.years', {n: y});
    }

    async function loadInfo() {
        const facts = [];
        try {
            const info = await Console.api('/info');
            if (info.bot_joined_at) el('ov-headline').textContent = tr('overview.hero', {time: joinDuration(info.bot_joined_at)});
            if (info.member_count) {
                facts.push(tr('overview.fact.members', {n: info.member_count.toLocaleString()}));
                const sub = el('switcher-sub'); if (sub) sub.textContent = tr('switcher.members', {n: info.member_count.toLocaleString()});
            }
            if (info.online_count) facts.push(tr('overview.fact.online', {n: info.online_count.toLocaleString()}));
            if (info.text_channels) facts.push(tr('overview.fact.text', {n: info.text_channels}));
        } catch { /* the card keeps its default line */ }
        try {
            const commands = await Console.commands();
            facts.push(tr('overview.fact.commands', {on: commands.filter(c => c.enabled).length, total: commands.length}));
        } catch { /* optional */ }
        el('ov-facts').textContent = facts.join(' · ');
    }

    let rendered = false;
    async function render(data) {
        let list = null;
        try { list = await Console.channels(); } catch { /* summaries fall back to blurbs */ }
        if (!list?.length) list = null;
        const notices = attention(data.modules, list), box = el('ov-attention');
        if (box) { box.replaceChildren(...notices.map(notice)); box.hidden = !notices.length; }
        for (const m of data.modules) {
            const row = document.querySelector(`[data-row="${m.slug}"]`);
            if (!row) continue;
            const node = row.querySelector('[data-summary]');
            const summary = summaryText(m.slug, m.summary, list);
            node.textContent = summary ? summary.text : node.dataset.blurb;
            node.classList.toggle('is-warn', !!summary?.warn);
            const input = row.querySelector('input[data-toggle]');
            if (input && !input.dataset.busy) {
                input.disabled = false;
                input.checked = m.summary ? !!m.summary.enabled : m.config_state !== 'disabled';
            }
            row.classList.toggle('is-on', !input || input.checked);
            row.querySelector('[data-state]').textContent = Console.stateLabel(m);
        }
        rendered = true;
        const grid = el('ov-modules'), error = el('ov-error');
        if (grid) { grid.hidden = false; grid.setAttribute('aria-busy', 'false'); }
        if (error) error.hidden = true;
    }

    // Only the very first load can fail visibly; later polling failures keep the cards that already loaded.
    function failed() {
        if (rendered) return;
        const grid = el('ov-modules'), error = el('ov-error');
        if (grid) grid.hidden = true;
        if (error) error.hidden = false;
    }
    function retry() {
        const grid = el('ov-modules'), error = el('ov-error');
        if (error) error.hidden = true;
        if (grid) grid.hidden = false;
        Console.refreshModules();
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!el('pg-overview')) return;
        document.addEventListener('console:modules', e => render(e.detail));
        document.addEventListener('console:modules-failed', failed);
        el('ov-retry')?.addEventListener('click', retry);
        document.querySelectorAll('input[data-toggle]').forEach(input => {
            input.addEventListener('change', () => toggle(input.dataset.toggle, input.checked, input));
        });
        loadInfo();
    });

    return {TOGGLE_SLUGS, summaryText, attention, toggle, joinDuration, render};
})();
