/* Bot log and server event log: channel, master switch, levels/categories, test message. */
(() => {
    const {tr} = Console;
    const el = id => document.getElementById(id);
    const PAGES = {botlog: {prefix: 'bl', field: 'levels'}, serverlog: {prefix: 'sl', field: 'categories'}};

    for (const [slug, {prefix, field}] of Object.entries(PAGES)) {
        const chips = () => [...document.querySelectorAll(`#pg-${slug} [data-log-kind]`)];
        Console.module({
            slug,
            async load() {
                const [channels, cfg] = await Promise.all([Console.channels(), Console.api('/' + slug)]);
                Console.channelOptions(el(prefix + '-ch'), channels, cfg.channel_id, 'logs.off');
                el(prefix + '-enabled').checked = !!cfg.enabled;
                const wanted = new Set(cfg[field] || []);
                chips().forEach(input => { input.checked = wanted.has(input.value); });
            },
            async save() {
                await Console.api('/' + slug, 'POST', {
                    channel_id: el(prefix + '-ch').value,
                    enabled: el(prefix + '-enabled').checked,
                    [field]: chips().filter(i => i.checked).map(i => i.value),
                });
            },
        });
        document.addEventListener('DOMContentLoaded', () => {
            const button = el(prefix + '-test'); if (!button) return;
            button.addEventListener('click', async () => {
                if (DashboardUI.dirty('pg-' + slug)) { DashboardUI.shake(); return; }
                button.disabled = true; button.textContent = tr('logs.testing');
                try { await Console.api(`/${slug}/test`, 'POST', {}); Console.toast(tr('logs.test_sent'), 'ok'); }
                catch (e) { Console.toast(tr('logs.test_failed', {reason: e.message}), 'bad'); }
                finally { button.disabled = false; button.textContent = tr('logs.test'); }
            });
        });
    }
})();
