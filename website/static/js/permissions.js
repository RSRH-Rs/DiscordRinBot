/* 邀请权限：取消勾选后在右侧列出受影响的功能，并按当前勾选生成邀请链接。划掉名称和"取消后"提示由 CSS 完成。 */
window.RinPermissions = (() => {
    const bitsFor = bits => bits.reduce((sum, bit) => sum | (1n << BigInt(bit)), 0n);

    /* 只换掉链接里的 permissions，其余参数原样保留 */
    function inviteHref(base, bits) {
        const url = new URL(base);
        url.searchParams.set('permissions', String(bits));
        return url.href;
    }

    const missing = (perms, unticked) => perms.filter(p => unticked.has(p.bit));

    const api = {bitsFor, inviteHref, missing};
    const dataEl = document.getElementById('perms-data');
    if (!dataEl) return api;

    const perms = JSON.parse(dataEl.textContent).permissions;
    const boxes = [...document.querySelectorAll('.perm input[data-bit]')];
    const body = document.getElementById('sum-body');
    const invite = document.getElementById('invite');
    const reset = document.getElementById('reset');
    const base = invite.href;
    const allDone = body.innerHTML;
    const allLabel = invite.innerHTML;
    const esc = s => String(s).replace(/[&<>"]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[ch]);
    const both = (zh, en) => `<span data-l="zh">${zh}</span><span data-l="en" lang="en">${en}</span>`;

    function render() {
        const unticked = new Set(boxes.filter(b => !b.checked).map(b => +b.dataset.bit));
        const lost = missing(perms, unticked);
        invite.href = inviteHref(base, bitsFor(boxes.filter(b => b.checked).map(b => +b.dataset.bit)));
        reset.hidden = lost.length === 0;
        if (!lost.length) {
            body.innerHTML = allDone;
            invite.innerHTML = allLabel;
            return;
        }
        body.innerHTML = `<h3>${both(`取消了 ${lost.length} 项`, `${lost.length} unticked`)}</h3>
            <p>${both('这些功能会受影响：', 'These will stop working:')}</p>
            <ul>${lost.map(p => `<li>${both(`<b>${esc(p.zh)}</b>：${esc(p.lose_zh)}`, `<b>${esc(p.en)}</b>: ${esc(p.lose_en)}`)}</li>`).join('')}</ul>`;
        invite.innerHTML = both('按这里的勾选邀请小凛', 'Invite Rin with these ticks');
    }

    boxes.forEach(b => b.addEventListener('change', render));
    reset.addEventListener('click', () => { boxes.forEach(b => { b.checked = true; }); render(); });
    render();
    return api;
})();
