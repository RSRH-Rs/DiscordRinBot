/* Music page: DJ role and now-playing channel. */
(() => {
    const el = id => document.getElementById(id);
    Console.module({
        slug: 'music',
        async load() {
            const [channels, roles, cfg] = await Promise.all([Console.channels(), Console.roles(), Console.api('/music')]);
            Console.channelOptions(el('mu-ch'), channels, cfg.notify_channel || 0);
            Console.roleOptions(el('mu-dj'), roles, cfg.dj_role || 0);
        },
        async save() {
            await Console.api('/music', 'POST', {dj_role: el('mu-dj').value, notify_channel: el('mu-ch').value});
        },
    });
})();
