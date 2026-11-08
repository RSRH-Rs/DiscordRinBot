/* Giveaways: create one (prize, winners, channel, end time, role) and list past ones. */
(() => {
    const {tr, escapeHtml} = Console;
    const el = id => document.getElementById(id);
    const HOUR = 3600 * 1000;
    let loaded = false;

    // datetime-local wants local wall-clock time, not UTC.
    const localInput = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    function setEnd(ms) { el('gw-end').value = localInput(new Date(Date.now() + ms)); el('gw-end').dispatchEvent(new Event('input', {bubbles: true})); }

    async function loadList() {
        const box = el('gw-list');
        const list = await Console.api('/giveaways');
        if (!list?.length) {
            box.innerHTML = `<div class="empty"><img src="/static/images/rin/confused-480.webp" alt="" width="96" height="96" loading="lazy"><p>${escapeHtml(tr('giveaway.empty'))}</p></div>`;
            return;
        }
        box.innerHTML = list.map(g => {
            const end = new Date(g.end_time * 1000).toLocaleString('zh-CN', {dateStyle: 'medium', timeStyle: 'short'});
            const state = g.ended ? tr('giveaway.ended') : tr('giveaway.running');
            return `<div class="case"><div class="case-head"><span class="chip chip--static${g.ended ? '' : ' chip--unban'}">${escapeHtml(state)}</span><span class="item-meta">${escapeHtml(end)}</span></div><p class="case-body"><b>#${escapeHtml(g.id)} ${escapeHtml(g.prize)}</b> · ${escapeHtml(tr('giveaway.winners_n', {n: g.winners_count}))}</p></div>`;
        }).join('');
    }

    async function create() {
        const prize = el('gw-prize').value.trim(), channel = el('gw-ch').value, endText = el('gw-end').value, role = el('gw-role').value;
        if (!prize) return Console.toast(tr('giveaway.need_prize'), 'bad');
        if (channel === '0') return Console.toast(tr('giveaway.need_channel'), 'bad');
        if (!endText) return Console.toast(tr('giveaway.need_end'), 'bad');
        const end = Math.floor(new Date(endText).getTime() / 1000), now = Math.floor(Date.now() / 1000);
        if (end <= now) return Console.toast(tr('giveaway.end_past'), 'bad');
        if (end > now + 365 * 86400) return Console.toast(tr('giveaway.end_far'), 'bad');
        const button = el('gw-create-btn');
        await DashboardUI.saving('pg-giveaway', () => Console.busy(button, async () => {
            try {
                const result = await Console.api('/giveaway/create', 'POST', {prize, winners_count: +el('gw-winners').value, channel_id: channel, end_time: end, restrict_role: role !== '0' ? role : null});
                if (!result.ok) throw new Error(result.error || tr('giveaway.create_failed_plain'));
                el('gw-prize').value = '';
                DashboardUI.clean('pg-giveaway');
                Console.toast(tr('giveaway.created'), 'ok');
                await loadList().catch(() => {});
                Console.refreshModules();
            } catch (e) { Console.toast(tr('giveaway.create_failed', {reason: e.message}), 'bad'); }
        }));
    }

    Console.module({
        slug: 'giveaway',
        isLoaded: () => loaded,
        async load() {
            const [channels, roles] = await Promise.all([Console.channels(), Console.roles()]);
            Console.channelOptions(el('gw-ch'), channels, 0, 'giveaway.pick_channel');
            Console.roleOptions(el('gw-role'), roles, 0);
            el('gw-end').value = localInput(new Date(Date.now() + 24 * HOUR));
            await loadList();
            loaded = true;
        },
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!el('pg-giveaway')) return;
        el('gw-create-btn').addEventListener('click', create);
        document.querySelectorAll('[data-end-in]').forEach(b => b.addEventListener('click', () => {
            document.querySelectorAll('[data-end-in]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
            if (b.dataset.endIn !== 'custom') setEnd(Number(b.dataset.endIn) * HOUR);
            el('gw-end').hidden = b.dataset.endIn !== 'custom';
            if (b.dataset.endIn === 'custom') el('gw-end').focus();
        }));
    });
})();
