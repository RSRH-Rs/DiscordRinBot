/* Leveling: the server leaderboard. */
(() => {
    const {tr, escapeHtml} = Console;
    const MEDALS = ['🥇', '🥈', '🥉'];
    let loaded = false;
    Console.module({
        slug: 'leveling',
        isLoaded: () => loaded,
        async load() {
            const list = await Console.api('/leaderboard');
            const box = document.getElementById('lb-list');
            if (!list?.length) {
                box.innerHTML = `<div class="empty"><img src="/static/images/rin/confused-480.webp" alt="" width="96" height="96" loading="lazy"><p>${escapeHtml(tr('leveling.empty'))}</p></div>`;
            } else {
                box.innerHTML = list.map((u, i) => `<div class="lb-row${i < 3 ? ' lb-row--top' : ''}"><span class="lb-rank">${MEDALS[i] || '#' + (i + 1)}</span><span class="lb-name" title="${escapeHtml(u.username)}">${escapeHtml(u.username)}</span><span class="lb-stat">Lv.${escapeHtml(u.level)} · ${escapeHtml(Number(u.xp).toLocaleString())} XP</span></div>`).join('');
            }
            loaded = true;
        },
    });
})();
