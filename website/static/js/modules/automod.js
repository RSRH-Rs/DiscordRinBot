/* Automod page: master switch, log channel, spam, banned words, link whitelist, caps and repeats. */
(() => {
    const el = id => document.getElementById(id);
    const SWITCHES = {'am-enabled': 'enabled', 'am-spam': 'anti_spam', 'am-bw': 'anti_badword', 'am-link': 'anti_link', 'am-caps': 'anti_caps', 'am-repeat': 'anti_repeat'};
    const NUMBERS = {'am-st': ['spam_threshold', 5], 'am-si': ['spam_interval', 5], 'am-ct': ['caps_threshold', 70], 'am-rt': ['repeat_threshold', 3]};
    const tags = id => [...el(id).querySelectorAll('.chip')].map(chip => chip.dataset.value);

    function addTag(prefix) {
        const input = el(prefix + '-new'), list = el(prefix + '-tags'), word = input.value.trim();
        if (!word) return;
        input.value = '';
        const current = tags(prefix + '-tags');
        if (!current.includes(word)) DashboardUI.renderTags(list, [...current, word]);
        DashboardUI.changed('pg-automod');
    }

    Console.module({
        slug: 'automod',
        async load() {
            const [cfg, channels] = await Promise.all([Console.api('/automod'), Console.channels()]);
            Console.channelOptions(el('am-log'), channels, cfg.log_channel);
            for (const [id, key] of Object.entries(SWITCHES)) el(id).checked = !!cfg[key];
            for (const [id, [key, fallback]] of Object.entries(NUMBERS)) el(id).value = cfg[key] || fallback;
            el('am-mute').value = String(cfg.mute_duration || 300);
            el('am-mute').dispatchEvent(new Event('change', {bubbles: true}));
            DashboardUI.renderTags(el('am-bw-tags'), cfg.badwords || []);
            DashboardUI.renderTags(el('am-wl-tags'), cfg.link_whitelist || []);
        },
        async save() {
            Console.duration.check(el('am-mute'));
            const payload = {log_channel: el('am-log').value, badwords: tags('am-bw-tags'), link_whitelist: tags('am-wl-tags'), mute_duration: +el('am-mute').value};
            for (const [id, key] of Object.entries(SWITCHES)) payload[key] = el(id).checked ? 1 : 0;
            for (const [id, [key]] of Object.entries(NUMBERS)) payload[key] = +el(id).value;
            await Console.api('/automod', 'POST', payload);
        },
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!el('pg-automod')) return;
        for (const prefix of ['am-bw', 'am-wl']) {
            el(prefix + '-add').addEventListener('click', () => addTag(prefix));
            el(prefix + '-new').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); addTag(prefix); } });
        }
    });
})();
