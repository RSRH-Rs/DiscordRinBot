/* Role panel page: message, role buttons with emoji, destination, sent panels. */
(() => {
    const {tr, escapeHtml} = Console;
    const el = id => document.getElementById(id);
    const MAX_ROWS = 20;
    let available = [], loaded = false;

    /* ── Emoji picker (one shared popup) ── */
    let tab = 'default', target = null, custom = null;
    const DEFAULT_EMOJIS = [
        {e: '😀', k: '笑 smile happy'}, {e: '😂', k: '笑哭 lol'}, {e: '🥰', k: '爱 love'}, {e: '😎', k: '酷 cool'},
        {e: '🥺', k: '求 pleading'}, {e: '😭', k: '哭 cry'}, {e: '😡', k: '怒 angry'}, {e: '🤔', k: '想 think'},
        {e: '😴', k: '睡 sleep'}, {e: '🤗', k: '抱 hug'}, {e: '😏', k: '坏笑 smirk'}, {e: '🙄', k: '翻白眼 eyeroll'},
        {e: '👍', k: '赞 thumbs up like'}, {e: '👎', k: '踩 thumbs down'}, {e: '👏', k: '拍手 clap'}, {e: '🙏', k: '谢谢 thanks pray'},
        {e: '✌️', k: '胜利 peace'}, {e: '🤝', k: '握手 handshake'}, {e: '💪', k: '肌肉 strong'}, {e: '🫡', k: '敬礼 salute'},
        {e: '❤️', k: '红心 heart love'}, {e: '🧡', k: '橙心 orange heart'}, {e: '💛', k: '黄心 yellow heart'}, {e: '💚', k: '绿心 green heart'},
        {e: '💙', k: '蓝心 blue heart'}, {e: '💜', k: '紫心 purple heart'}, {e: '🖤', k: '黑心 black heart'}, {e: '🤍', k: '白心 white heart'},
        {e: '💖', k: '闪心 sparkle heart'}, {e: '💗', k: '粉心 pink heart'}, {e: '💕', k: '两颗心 two hearts'}, {e: '✨', k: '闪 sparkles'},
        {e: '🔥', k: '火 fire'}, {e: '⭐', k: '星 star'}, {e: '🌟', k: '闪星 glow star'}, {e: '⚡', k: '闪电 lightning'},
        {e: '🎉', k: '庆祝 party'}, {e: '🎊', k: '彩带 confetti'}, {e: '🎁', k: '礼物 gift'}, {e: '🏆', k: '奖杯 trophy'},
        {e: '🌸', k: '樱花 cherry blossom'}, {e: '🌺', k: '花 flower'}, {e: '🌷', k: '郁金香 tulip'}, {e: '🌻', k: '向日葵 sunflower'},
        {e: '🌹', k: '玫瑰 rose'}, {e: '🍀', k: '四叶草 clover'}, {e: '🌈', k: '彩虹 rainbow'}, {e: '☀️', k: '太阳 sun'},
        {e: '🌙', k: '月亮 moon'}, {e: '⛅', k: '云 cloud'}, {e: '❄️', k: '雪 snow'}, {e: '🎵', k: '音符 music'},
        {e: '🎮', k: '游戏 game'}, {e: '🕹️', k: '摇杆 joystick'}, {e: '🎲', k: '骰子 dice'}, {e: '🎯', k: '目标 target'},
        {e: '🍕', k: '披萨 pizza'}, {e: '🍔', k: '汉堡 burger'}, {e: '🍣', k: '寿司 sushi'}, {e: '🍰', k: '蛋糕 cake'},
        {e: '☕', k: '咖啡 coffee'}, {e: '🍺', k: '啤酒 beer'}, {e: '🐱', k: '猫 cat'}, {e: '🐶', k: '狗 dog'},
        {e: '🐼', k: '熊猫 panda'}, {e: '🦊', k: '狐狸 fox'}, {e: '🐰', k: '兔子 bunny'}, {e: '🦄', k: '独角兽 unicorn'},
        {e: '✅', k: '对 check yes'}, {e: '❌', k: '错 cross no'}, {e: '⚠️', k: '警告 warning'}, {e: '❓', k: '问号 question'},
        {e: '❗', k: '感叹号 exclamation'}, {e: '💯', k: '满分 100'}, {e: '🚀', k: '火箭 rocket'}, {e: '💎', k: '钻石 diamond'},
    ];
    function positionPicker() {
        const picker = el('emoji-picker');
        if (!picker || picker.hidden || !target) return;
        const rect = target.getBoundingClientRect(), width = picker.offsetWidth, height = picker.offsetHeight;
        picker.style.left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)) + 'px';
        picker.style.top = Math.max(12, Math.min(rect.bottom + 6, window.innerHeight - height - 12)) + 'px';
    }
    function closePicker(restoreFocus = false) {
        const picker = el('emoji-picker'); if (!picker || picker.hidden) return;
        picker.hidden = true;
        document.removeEventListener('pointerdown', outside);
        if (restoreFocus) target?.focus();
    }
    function outside(e) { if (!el('emoji-picker').contains(e.target) && !target?.contains(e.target)) closePicker(); }
    async function openPicker(button) {
        target = button;
        if (custom === null) { try { custom = await Console.api('/emojis'); } catch { custom = []; } }
        if (!button.isConnected || !button.closest('.page.is-active')) return;
        el('emoji-picker').hidden = false;
        el('ep-search').value = '';
        renderGrid();
        positionPicker();
        el('ep-search').focus();
        document.addEventListener('pointerdown', outside);
    }
    function renderGrid() {
        const q = el('ep-search').value.toLowerCase().trim(), grid = el('ep-grid');
        const items = tab === 'default'
            ? DEFAULT_EMOJIS.filter(x => !q || x.k.includes(q) || x.e === q).map(x => ({code: x.e, label: x.e}))
            : (custom || []).filter(x => !q || x.name.toLowerCase().includes(q)).map(x => ({code: `<${x.animated ? 'a' : ''}:${x.name}:${x.id}>`, url: x.url, name: x.name}));
        grid.replaceChildren(...items.map(item => {
            const b = document.createElement('button');
            b.type = 'button'; b.className = 'ep-item';
            if (item.url) { const img = document.createElement('img'); img.src = item.url; img.alt = ''; b.append(img); b.title = ':' + item.name + ':'; }
            else b.textContent = item.label;
            b.addEventListener('click', () => pick(item.code, item.url));
            return b;
        }));
        if (!items.length) { const p = document.createElement('p'); p.className = 'ep-empty'; p.textContent = tr(tab === 'default' ? 'roles.emoji_none' : 'roles.emoji_none_custom'); grid.append(p); }
        positionPicker();
    }
    function pick(code, url) {
        if (!target) return;
        target.closest('.rr-row').querySelector('.rr-emoji').value = code;
        if (url) { const img = document.createElement('img'); img.src = url; img.alt = ''; target.replaceChildren(img); }
        else target.textContent = code;
        closePicker(true);
        DashboardUI.changed('pg-roles');
        window.DashboardPreview?.refresh();
    }

    /* ── Rows ── */
    function addRow() {
        const list = el('rr-roles-list');
        if (list.children.length >= MAX_ROWS) { Console.toast(tr('roles.max_rows', {n: MAX_ROWS}), 'bad'); return; }
        const row = document.createElement('div'); row.className = 'rr-row';
        const emoji = document.createElement('button');
        emoji.type = 'button'; emoji.className = 'emoji-trigger'; emoji.setAttribute('aria-label', tr('roles.pick_emoji'));
        emoji.innerHTML = '<span class="ep-placeholder" aria-hidden="true">🎮</span>';
        emoji.addEventListener('click', () => openPicker(emoji));
        const hidden = document.createElement('input'); hidden.type = 'hidden'; hidden.className = 'rr-emoji'; hidden.value = '';
        const select = document.createElement('select'); select.className = 'select rr-role'; select.setAttribute('aria-label', tr('roles.pick_role'));
        select.append(...available.map(r => new Option(r.name, r.id)));
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'btn btn--icon'; remove.setAttribute('aria-label', tr('roles.remove_row'));
        remove.innerHTML = `<svg class="icon" width="16" height="16" aria-hidden="true"><use href="/static/icons.svg#i-x"/></svg>`;
        remove.addEventListener('click', () => { row.remove(); DashboardUI.changed('pg-roles'); window.DashboardPreview?.refresh(); });
        row.append(emoji, hidden, select, remove);
        list.append(row);
        window.DashboardExtras?.enhanceSelects(row);
        DashboardUI.changed('pg-roles');
    }

    async function loadPanels() {
        const box = el('rr-existing');
        const panels = await Console.api('/reactionroles');
        if (!panels?.length) { box.innerHTML = `<p class="section-hint">${escapeHtml(tr('roles.no_panels'))}</p>`; return; }
        box.innerHTML = panels.map(p => {
            const mappings = typeof p.mappings === 'string' ? JSON.parse(p.mappings) : p.mappings;
            return `<div class="item"><span class="item-text"><b>${escapeHtml(p.title || tr('roles.default_title'))}</b> · ${escapeHtml(tr('roles.panel_meta', {n: Object.keys(mappings).length}))}</span><span class="item-meta">#${escapeHtml(p.channel_id)}</span></div>`;
        }).join('');
    }

    async function send() {
        const channel = el('rr-ch').value;
        if (channel === '0') { Console.toast(tr('roles.need_channel'), 'bad'); return; }
        const rows = [...document.querySelectorAll('#rr-roles-list .rr-row')];
        if (!rows.length) { Console.toast(tr('roles.need_role'), 'bad'); return; }
        const mappings = [];
        for (const row of rows) {
            const emoji = row.querySelector('.rr-emoji').value.trim(), select = row.querySelector('.rr-role');
            if (!emoji) { Console.toast(tr('roles.need_emoji'), 'bad'); return; }
            mappings.push({emoji, role_id: select.value, role_name: select.selectedOptions[0]?.textContent || ''});
        }
        const button = el('rr-send');
        await DashboardUI.saving('pg-roles', async () => {
            button.disabled = true; button.textContent = tr('roles.sending');
            try {
                const result = await Console.api('/reactionroles/send', 'POST', {
                    channel_id: channel, title: el('rr-title').value || tr('roles.default_title'),
                    content: el('rr-content').value || tr('roles.default_content'), mappings, exclusive: el('rr-exclusive').checked,
                });
                if (!result.ok) throw new Error(result.error || tr('roles.send_failed_plain'));
                el('rr-title').value = ''; el('rr-content').value = ''; el('rr-roles-list').replaceChildren();
                DashboardUI.clean('pg-roles');
                Console.toast(tr('roles.sent'), 'ok');
                await loadPanels().catch(() => {});
                Console.refreshModules();
            } catch (e) {
                Console.toast(tr('roles.send_failed', {reason: e.message}), 'bad');
            } finally { button.disabled = false; button.textContent = tr('roles.send'); }
        });
    }

    Console.module({
        slug: 'roles',
        isLoaded: () => loaded,
        async load() {
            const [channels, roles] = await Promise.all([Console.channels(), Console.roles()]);
            Console.channelOptions(el('rr-ch'), channels, 0, 'roles.pick_channel');
            available = roles;
            await loadPanels();
            loaded = true;
        },
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!el('pg-roles')) return;
        el('rr-add').addEventListener('click', addRow);
        el('rr-send').addEventListener('click', send);
        el('ep-search').addEventListener('input', renderGrid);
        document.querySelectorAll('.ep-tab').forEach(b => b.addEventListener('click', () => {
            tab = b.dataset.tab;
            document.querySelectorAll('.ep-tab').forEach(t => t.setAttribute('aria-pressed', String(t === b)));
            renderGrid();
        }));
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && !el('emoji-picker').hidden) { e.preventDefault(); closePicker(true); } });
        el('main').addEventListener('scroll', positionPicker, {passive: true});
        window.addEventListener('resize', positionPicker);
        document.addEventListener('console:page', () => closePicker());
    });

    window.RolePanel = {positionPicker, setTarget: t => { target = t; }};
})();
