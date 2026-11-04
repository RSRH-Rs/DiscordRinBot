/* Moderation page: log channel, warning thresholds and recent cases. */
(() => {
    const {tr, escapeHtml} = Console;
    const el = id => document.getElementById(id);
    const FIELDS = {'mod-mt': ['warn_mute_threshold', 3], 'mod-md': ['warn_mute_duration', 600], 'mod-kt': ['warn_kick_threshold', 0], 'mod-bt': ['warn_ban_threshold', 0]};
    const ACTIONS = ['warn', 'mute', 'unmute', 'kick', 'ban', 'tempban', 'unban', 'purge'];

    function renderCases(cases) {
        const box = el('mod-cases');
        if (!cases?.length) { box.innerHTML = `<div class="empty"><p>${escapeHtml(tr('moderation.no_cases'))}</p></div>`; return; }
        box.innerHTML = cases.map(c => {
            const time = new Date(c.created_at * 1000);
            const when = time.toLocaleDateString('zh-CN') + ' ' + time.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
            const kind = ACTIONS.includes(c.action) ? c.action : 'other';
            const details = [tr('moderation.case_user', {user: c.user_name || c.user_id}), tr('moderation.case_mod', {mod: c.mod_name || c.mod_id}), tr('moderation.case_reason', {reason: c.reason})];
            if (c.duration) details.push(tr('moderation.case_duration', {duration: c.duration}));
            return `<div class="case"><div class="case-head"><span class="chip chip--static chip--${kind}">#${escapeHtml(c.case_no ?? c.id)} ${escapeHtml(tr('moderation.action.' + kind))}</span><span class="item-meta">${escapeHtml(when)}</span></div><p class="case-body">${details.map(escapeHtml).join(' · ')}</p></div>`;
        }).join('');
    }

    Console.module({
        slug: 'moderation',
        async load() {
            const [cfg, channels, cases] = await Promise.all([Console.api('/moderation'), Console.channels(), Console.api('/moderation/cases')]);
            Console.channelOptions(el('mod-log'), channels, cfg.log_channel);
            for (const [id, [key, fallback]] of Object.entries(FIELDS)) el(id).value = cfg[key] ?? fallback;
            el('mod-md').dispatchEvent(new Event('change', {bubbles: true}));
            renderCases(cases);
        },
        async save() {
            Console.duration.check(el('mod-md'));
            const payload = {log_channel: el('mod-log').value};
            for (const [id, [key]] of Object.entries(FIELDS)) payload[key] = +el(id).value;
            await Console.api('/moderation', 'POST', payload);
        },
    });
})();
