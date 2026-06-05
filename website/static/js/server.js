const GID = window.GID || "";
let _ch = null, _roles = null;

/* ── Navigation ── */
function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('open');
    document.getElementById('sidebarBackdrop').classList.toggle('show');
}
function closeSidebar() {
    document.querySelector('.sidebar').classList.remove('open');
    document.getElementById('sidebarBackdrop').classList.remove('show');
}
// 让键盘用户能用 Enter/空格 触发导航项（它们是 <a> 无 href，靠 onclick）
document.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.nav-link[role="button"]')) {
        e.preventDefault();
        e.target.click();
    }
});
function go(mod) {
    closeSidebar();
    document.querySelectorAll('.mod-page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('#side-modules .nav-link').forEach(l => l.classList.remove('active'));
    const pg = document.getElementById('pg-' + mod);
    const nl = document.querySelector(`[data-mod="${mod}"]`);
    if (pg) pg.classList.add('active');
    if (nl) nl.classList.add('active');
    window.scrollTo(0, 0);
    // lazy load data
    if (mod === 'welcome') loadWelcome();
    if (mod === 'automod') loadAutoMod();
    if (mod === 'moderation') loadModeration();
    if (mod === 'giveaway') loadGiveaways();
    if (mod === 'leveling') loadLeaderboard();
    if (mod === 'music') loadMusicSelects();
    if (mod === 'personalizer') loadPersonalizer();
    if (mod === 'roles') loadRolesPage();
    if (mod === 'giveaway') loadGiveawayPage();
    if (mod === 'utility') loadUtility();
    if (mod === 'botlog') loadBotLog();
    if (mod === 'serverlog') loadServerLog();
    // Re-render Lucide icons for newly visible content
    if (window.lucide) lucide.createIcons();
}

/* ── API helper with error handling ── */
async function api(path, method='GET', body=null) {
    const opts = { method, headers: {'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(`/api/guild/${GID}${path}`, opts);
    if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.error || `请求失败 (${r.status})`);
    }
    return r.json();
}
async function apiGlobal(path, method='GET', body=null) {
    const opts = { method, headers: {'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.error || `请求失败 (${r.status})`);
    }
    return r.json();
}
async function getCh() { if (!_ch) try { _ch = await api('/channels'); } catch(e) { _ch = []; } return _ch || []; }
async function getRoles() { if (!_roles) try { _roles = await api('/roles'); } catch(e) { _roles = []; } return _roles || []; }

/* ── Skeleton loading ── */
function showSkeleton(elId, count=3) {
    const el = document.getElementById(elId);
    if (el) el.innerHTML = Array(count).fill('<div class="skel skel-row"></div>').join('');
}
function showError(elId, msg) {
    const el = document.getElementById(elId);
    if (el) el.innerHTML = `<div class="error-state">❌ ${msg}</div>`;
}

/* ── Dirty tracking (unsaved changes) ── */
function markDirty(barId) {
    const bar = document.getElementById(barId);
    if (bar) { bar.classList.add('dirty'); bar.querySelector('.save-hint').textContent = '⚠️ 你有未保存的更改'; }
}
function markClean(barId) {
    const bar = document.getElementById(barId);
    if (bar) { bar.classList.remove('dirty'); bar.querySelector('.save-hint').textContent = '修改后记得保存哦~'; }
}

function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function chOpts(sel, channels, selected) {
    const el = document.getElementById(sel);
    el.innerHTML = '<option value="0">— 未设置 —</option>' +
        channels.map(c => `<option value="${c.id}" ${String(c.id)===String(selected)?'selected':''}># ${escapeHtml(c.name)}</option>`).join('');
}

/* ── Welcome ── */
let _wLoaded = false;
async function loadWelcome() {
    if (_wLoaded) return; _wLoaded = true;
    try {
        const [cfg, ch, roles] = await Promise.all([api('/welcome'), getCh(), getRoles()]);
        chOpts('w-ch', ch, cfg.welcome_channel);
        chOpts('w-fch', ch, cfg.farewell_channel);
        document.getElementById('w-msg').value = cfg.welcome_msg || '';
        document.getElementById('w-fmsg').value = cfg.farewell_msg || '';
        const autoRoles = cfg.auto_roles ? cfg.auto_roles.split(',').filter(Boolean) : [];
        document.getElementById('w-roles').innerHTML = roles.map(r =>
            `<label class="role-opt"><input type="checkbox" value="${r.id}" ${autoRoles.includes(String(r.id))?'checked':''} onchange="markDirty('w-savebar')"> ${escapeHtml(r.name)}</label>`
        ).join('');
        // Attach dirty listeners
        document.querySelectorAll('#w-ch,#w-fch,#w-msg,#w-fmsg').forEach(el => el.addEventListener('input', () => markDirty('w-savebar')));
    } catch(e) { showToast('❌ 加载欢迎配置失败: ' + e.message); }
}
async function saveWelcome() {
    const btn = document.getElementById('w-save'); btn.disabled = true; btn.textContent = '保存中…';
    const checked = [...document.querySelectorAll('#w-roles input:checked')].map(i => i.value);
    await api('/welcome', 'POST', {
        welcome_channel: document.getElementById('w-ch').value,
        farewell_channel: document.getElementById('w-fch').value,
        auto_roles: checked.join(','),
        welcome_msg: document.getElementById('w-msg').value,
        farewell_msg: document.getElementById('w-fmsg').value,
    });
    btn.textContent = '✅ 已保存！'; showToast('✅ 欢迎配置已保存！'); markClean('w-savebar');
    setTimeout(() => { btn.disabled = false; btn.textContent = '储存设定'; }, 1500);
}

/* ── AutoMod ── */
let _amLoaded = false;
async function loadAutoMod() {
    if (_amLoaded) return; _amLoaded = true;
    try {
        const [cfg, ch] = await Promise.all([api('/automod'), getCh()]);
    chOpts('am-log', ch, cfg.log_channel);
    document.getElementById('am-enabled').checked = !!cfg.enabled;
    document.getElementById('am-spam').checked = !!cfg.anti_spam;
    document.getElementById('am-st').value = cfg.spam_threshold || 5;
    document.getElementById('am-si').value = cfg.spam_interval || 5;
    document.getElementById('am-mute').value = cfg.mute_duration || 300;
    document.getElementById('am-bw').checked = !!cfg.anti_badword;
    document.getElementById('am-link').checked = !!cfg.anti_link;
    document.getElementById('am-caps').checked = !!cfg.anti_caps;
    document.getElementById('am-ct').value = cfg.caps_threshold || 70;
    document.getElementById('am-repeat').checked = !!cfg.anti_repeat;
    document.getElementById('am-rt').value = cfg.repeat_threshold || 3;
    renderTags('am-bw-tags', cfg.badwords || []);
    renderTags('am-wl-tags', cfg.link_whitelist || []);
    // Dirty listeners
    document.querySelectorAll('#am-enabled,#am-spam,#am-bw,#am-link,#am-caps,#am-repeat,#am-log,#am-st,#am-si,#am-mute,#am-ct,#am-rt').forEach(el => el.addEventListener('change', () => markDirty('am-savebar')));
    } catch(e) { showToast('❌ 加载审核配置失败: ' + e.message); }
}
async function saveAutoMod() {
    const btn = document.getElementById('am-save'); btn.disabled = true; btn.textContent = '保存中…';
    await api('/automod', 'POST', {
        enabled: document.getElementById('am-enabled').checked ? 1 : 0,
        log_channel: document.getElementById('am-log').value,
        anti_spam: document.getElementById('am-spam').checked ? 1 : 0,
        spam_threshold: +document.getElementById('am-st').value,
        spam_interval: +document.getElementById('am-si').value,
        anti_badword: document.getElementById('am-bw').checked ? 1 : 0,
        badwords: collectTags('am-bw-tags'),
        anti_link: document.getElementById('am-link').checked ? 1 : 0,
        link_whitelist: collectTags('am-wl-tags'),
        anti_caps: document.getElementById('am-caps').checked ? 1 : 0,
        caps_threshold: +document.getElementById('am-ct').value,
        anti_repeat: document.getElementById('am-repeat').checked ? 1 : 0,
        repeat_threshold: +document.getElementById('am-rt').value,
        mute_duration: +document.getElementById('am-mute').value,
    });
    btn.textContent = '✅ 已保存！'; showToast('✅ 审核配置已保存！'); markClean('am-savebar');
    setTimeout(() => { btn.disabled = false; btn.textContent = '储存设定'; }, 1500);
}

/* ── Moderation ── */
let _modLoaded = false;
async function loadModeration() {
    if (_modLoaded) return; _modLoaded = true;
    showSkeleton('mod-cases', 4);
    try {
        const [cfg, ch, cases] = await Promise.all([api('/moderation'), getCh(), api('/moderation/cases')]);
    chOpts('mod-log', ch, cfg.log_channel);
    document.getElementById('mod-mt').value = cfg.warn_mute_threshold || 3;
    document.getElementById('mod-md').value = cfg.warn_mute_duration || 600;
    document.getElementById('mod-kt').value = cfg.warn_kick_threshold || 0;
    document.getElementById('mod-bt').value = cfg.warn_ban_threshold || 0;
    const el = document.getElementById('mod-cases');
    if (!cases || cases.length === 0) { el.innerHTML = '<div class="empty-state-sm">暂无管理记录</div>'; return; }
    const colors = {kick:'#E8899A',ban:'#E24B4A',tempban:'#E24B4A',mute:'#EF9F27',warn:'#FFD166',unban:'#5A9E6F',unmute:'#5A9E6F',purge:'#85B7EB'};
    el.innerHTML = cases.map(c => {
        const d = new Date(c.created_at * 1000);
        const ts = d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
        return `<div class="case-item"><div class="case-head"><span class="case-action" style="color:${colors[c.action]||'var(--text)'}">#${c.id} ${c.action}</span><span class="case-time">${ts}</span></div><div class="case-body">${escapeHtml(c.user_name || c.user_id)} · 管理员: ${escapeHtml(c.mod_name || c.mod_id)} · 原因: ${escapeHtml(c.reason)}${c.duration?' · 时长: '+c.duration:''}</div></div>`;
    }).join('');
    // Dirty listeners
    document.querySelectorAll('#mod-log,#mod-mt,#mod-md,#mod-kt,#mod-bt').forEach(el => el.addEventListener('change', () => markDirty('mod-savebar')));
    } catch(e) { showToast('❌ 加载管理配置失败: ' + e.message); showError('mod-cases', e.message); }
}
async function saveModeration() {
    const btn = document.getElementById('mod-save'); btn.disabled = true; btn.textContent = '保存中…';
    try {
        await api('/moderation', 'POST', {
            log_channel: document.getElementById('mod-log').value,
            warn_mute_threshold: +document.getElementById('mod-mt').value,
            warn_mute_duration: +document.getElementById('mod-md').value,
            warn_kick_threshold: +document.getElementById('mod-kt').value,
            warn_ban_threshold: +document.getElementById('mod-bt').value,
        });
        btn.textContent = '✅ 已保存！'; showToast('✅ 管理配置已保存！'); markClean('mod-savebar');
    } catch(e) { showToast('❌ 保存失败: ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '储存设定'; }, 1500);
}

/* ── Music config ── */
let _muLoaded = false;
async function loadMusicSelects() {
    if (_muLoaded) return; _muLoaded = true;
    try {
        const [ch, roles, cfg] = await Promise.all([getCh(), getRoles(), api('/music').catch(()=>({}))]);
        chOpts('mu-ch', ch, cfg.notify_channel || 0);
        const djSel = document.getElementById('mu-dj');
        djSel.innerHTML = '<option value="0">— 不限制 —</option>' + roles.map(r =>
            `<option value="${r.id}" ${String(r.id)===String(cfg.dj_role||0)?'selected':''}>@ ${escapeHtml(r.name)}</option>`
        ).join('');
        document.querySelectorAll('#mu-dj,#mu-ch').forEach(el => el.addEventListener('change', () => markDirty('mu-savebar')));
    } catch(e) { showToast('❌ 加载音乐配置失败: ' + e.message); }
}
async function saveMusic() {
    const btn = document.getElementById('mu-save'); btn.disabled = true; btn.textContent = '保存中…';
    try {
        await api('/music', 'POST', {
            dj_role: document.getElementById('mu-dj').value,
            notify_channel: document.getElementById('mu-ch').value,
        });
        btn.textContent = '✅ 已保存！'; showToast('✅ 音乐配置已保存！'); markClean('mu-savebar');
    } catch(e) { showToast('❌ 保存失败: ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '储存设定'; }, 1500);
}

/* ── Giveaway list ── */
async function loadGiveaways() {
    showSkeleton('gw-list', 2);
    try {
        const data = await api('/giveaways');
        const el = document.getElementById('gw-list');
        if (!data || data.length === 0) { el.innerHTML = '<div class="empty-state-sm" style="padding:40px;">＋<br><br>还没有任何抽奖活动</div>'; return; }
        el.innerHTML = data.map(g => {
            const d = new Date(g.end_time * 1000);
            return `<div class="case-item"><div class="case-head"><span class="case-action" style="color:${g.ended?'var(--text-muted)':'var(--green)'}">#${g.id} ${escapeHtml(g.prize)}</span><span class="case-time">${g.ended?'已结束':'进行中'} · ${d.toLocaleDateString('zh-CN')}</span></div><div class="case-body">名额: ${g.winners_count}</div></div>`;
        }).join('');
    } catch(e) { showError('gw-list', '加载失败: ' + e.message); }
}

/* ── Leaderboard ── */
async function loadLeaderboard() {
    showSkeleton('lb-list', 3);
    try {
        const data = await api('/leaderboard');
        const el = document.getElementById('lb-list');
        if (!data || data.length === 0) { el.innerHTML = '<div class="empty-state-sm">暂无等级数据</div>'; return; }
        const medals = ['🥇','🥈','🥉'];
        el.innerHTML = data.map((u, i) =>
            `<div class="case-item"><div style="display:flex;align-items:center;gap:12px;"><span style="font-size:1rem;width:24px;text-align:center;">${medals[i]||'#'+(i+1)}</span><span style="font-weight:700;flex:1;">${escapeHtml(u.username)}</span><span style="font-size:.82rem;color:var(--text-muted);">Lv.${u.level} · ${u.xp.toLocaleString()} XP</span></div></div>`
        ).join('');
    } catch(e) { showError('lb-list', '加载失败: ' + e.message); }
}

/* ── Tag helpers ── */
function renderTags(id, arr) {
    document.getElementById(id).innerHTML = arr.map(w =>
        `<span class="tag-chip">${escapeHtml(w)}<span class="tag-rm" onclick="this.parentElement.remove()">×</span></span>`
    ).join('');
}
function addTag(prefix) {
    const inp = document.getElementById(prefix + '-new');
    const w = inp.value.trim(); if (!w) return; inp.value = '';
    document.getElementById(prefix + '-tags').insertAdjacentHTML('beforeend',
        `<span class="tag-chip">${w}<span class="tag-rm" onclick="this.parentElement.remove()">×</span></span>`);
}
function collectTags(id) {
    return [...document.querySelectorAll('#' + id + ' .tag-chip')].map(t => t.firstChild.textContent.trim());
}

/* ── Utility (Command Toggle) ── */
let _utLoaded = false, _cmdData = null;

async function loadOverviewStats() {
    try {
        const cmds = await api('/commands');
        _cmdData = cmds;
        const total = cmds.length;
        const enabled = cmds.filter(c => c.enabled).length;
        const disabled = total - enabled;
        const ov1 = document.getElementById('ov-enabled');
        const ov2 = document.getElementById('ov-disabled');
        if (ov1) ov1.innerHTML = `${enabled} <span class="accent">/ ${total}</span>`;
        if (ov2) ov2.textContent = disabled > 0 ? disabled : '0';
    } catch(e) {
        console.error('Overview stats failed:', e);
        const ov1 = document.getElementById('ov-enabled');
        if (ov1) ov1.innerHTML = '— <span class="accent">/ —</span>';
    }
}

async function loadUtility() {
    showSkeleton('util-commands', 4);
    if (!_cmdData) await loadOverviewStats();
    const cmds = _cmdData;
    const el = document.getElementById('util-commands');
    if (!cmds || cmds.length === 0) { el.innerHTML = '<div class="empty-state-sm">没有可用指令</div>'; return; }

    const total = cmds.length;
    const enabled = cmds.filter(c => c.enabled).length;
    document.getElementById('util-summary').textContent = `共 ${total} 个指令，${enabled} 个已启用`;

    const groups = {};
    for (const c of cmds) {
        if (!groups[c.cog]) groups[c.cog] = [];
        groups[c.cog].push(c);
    }

    let html = '';
    for (const [cog, commands] of Object.entries(groups)) {
        const cogEnabled = commands.filter(c => c.enabled).length;
        const cogTotal = commands.length;
        const allOn = cogEnabled === cogTotal;

        html += `<div class="cmd-group-header" id="cg-${cog}" onclick="toggleCollapse('${cog}')" style="cursor:pointer;">
            <div style="display:flex;align-items:center;">
                <svg class="cmd-group-chevron" id="chev-${cog}" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                <span class="cmd-group-label">${cog}</span>
                <span class="cmd-group-count" id="cgc-${cog}">${cogEnabled} / ${cogTotal}</span>
            </div>
            <label class="cfg-tog" onclick="event.stopPropagation()">
                <input type="checkbox" ${allOn?'checked':''} onchange="toggleCategory('${cog}', this.checked)">
                <span class="track"></span>
                <span class="thumb"></span>
            </label>
        </div>`;

        html += `<div class="cmd-group-body collapsed" id="cgb-${cog}">`;
        for (const c of commands) {
            const checked = c.enabled ? 'checked' : '';
            const disabled = c.protected ? 'disabled' : '';
            const opacity = !c.enabled && !c.protected ? 'opacity:.5;' : c.protected ? 'opacity:.6;' : '';
            html += `<div class="cmd-row" id="cr-${c.name}" data-cog="${cog}" style="${opacity}">
                <div class="cmd-info">
                    <div class="cmd-name">${c.name}</div>
                    <div class="cmd-desc">${c.desc}</div>
                </div>
                <div class="cmd-toggle">
                    <label class="cfg-tog">
                        <input type="checkbox" ${checked} ${disabled} onchange="toggleCommand('${c.name}', this.checked, '${cog}')">
                        <span class="track"></span>
                        <span class="thumb"></span>
                    </label>
                </div>
            </div>`;
        }
        html += `</div>`;
    }
    el.innerHTML = html;
    if (window.lucide) lucide.createIcons();
}

function toggleCollapse(cog) {
    const body = document.getElementById('cgb-' + cog);
    const chev = document.getElementById('chev-' + cog);
    if (!body) return;
    if (body.classList.contains('collapsed')) {
        body.style.maxHeight = body.scrollHeight + 'px';
        body.classList.remove('collapsed');
        if (chev) chev.classList.add('open');
    } else {
        body.style.maxHeight = body.scrollHeight + 'px';
        requestAnimationFrame(() => { body.style.maxHeight = '0'; });
        body.classList.add('collapsed');
        if (chev) chev.classList.remove('open');
    }
}

async function toggleCommand(name, enabled, cog) {
    try {
        const r = await api('/commands/toggle', 'POST', { name, enabled });
        if (r.ok) {
            const row = document.getElementById('cr-' + name);
            if (row) row.style.opacity = enabled ? '' : '.5';
            // Update local data
            if (_cmdData) {
                const c = _cmdData.find(x => x.name === name);
                if (c) c.enabled = enabled;
            }
            updateCogCount(cog);
            updateSummary();
            showToast(enabled ? `✅ /${name} 已启用` : `⏹ /${name} 已禁用`);
        } else { showToast('❌ ' + (r.error || '操作失败')); }
    } catch(e) { showToast('❌ 网络错误'); }
}

async function toggleCategory(cog, enabled) {
    if (!_cmdData) return;
    const cmds = _cmdData.filter(c => c.cog === cog && !c.protected);
    const promises = cmds.map(c => api('/commands/toggle', 'POST', { name: c.name, enabled }));
    try {
        await Promise.all(promises);
        for (const c of cmds) {
            c.enabled = enabled;
            const row = document.getElementById('cr-' + c.name);
            if (row) {
                row.style.opacity = enabled ? '' : '.5';
                const cb = row.querySelector('input[type=checkbox]');
                if (cb) cb.checked = enabled;
            }
        }
        updateCogCount(cog);
        updateSummary();
        showToast(enabled ? `✅ ${cog} 全部指令已启用` : `⏹ ${cog} 全部指令已禁用`);
    } catch(e) { showToast('❌ 批量操作失败'); }
}

function updateCogCount(cog) {
    if (!_cmdData) return;
    const cmds = _cmdData.filter(c => c.cog === cog);
    const en = cmds.filter(c => c.enabled).length;
    const el = document.getElementById('cgc-' + cog);
    if (el) el.textContent = `${en} / ${cmds.length}`;
    // Update category toggle checkbox
    const header = document.getElementById('cg-' + cog);
    if (header) {
        const cb = header.querySelector('input[type=checkbox]');
        if (cb) cb.checked = en === cmds.length;
    }
}

function updateSummary() {
    if (!_cmdData) return;
    const total = _cmdData.length;
    const enabled = _cmdData.filter(c => c.enabled).length;
    const disabled = total - enabled;
    const sumEl = document.getElementById('util-summary');
    if (sumEl) sumEl.textContent = `共 ${total} 个指令，${enabled} 个已启用`;
    const ov1 = document.getElementById('ov-enabled');
    const ov2 = document.getElementById('ov-disabled');
    if (ov1) ov1.innerHTML = `${enabled} <span class="accent">/ ${total}</span>`;
    if (ov2) ov2.textContent = disabled > 0 ? disabled : '0';
}

/* ── Reaction Roles config ── */
let _rrLoaded = false, _rrRoleCount = 0;
async function loadRolesPage() {
    if (_rrLoaded) return; _rrLoaded = true;
    showSkeleton('rr-existing', 2);
    const [ch, roles] = await Promise.all([getCh(), getRoles()]);
    chOpts('rr-ch', ch, 0);
    window._rrAvailRoles = roles;
    try {
        const panels = await api('/reactionroles');
        const el = document.getElementById('rr-existing');
        if (!panels || panels.length === 0) { el.innerHTML = '<div class="empty-state-sm">还没有任何面板</div>'; }
        else {
            el.innerHTML = panels.map(p => {
                const mappings = typeof p.mappings === 'string' ? JSON.parse(p.mappings) : p.mappings;
                const count = Object.keys(mappings).length;
                return `<div class="case-item"><div class="case-head"><span class="case-action" style="color:var(--pink);">${escapeHtml(p.title || '身份组面板')}</span><span class="case-time">消息 ID: ${p.message_id} · ${count} 个映射</span></div><div class="case-body">频道 ID: ${p.channel_id}</div></div>`;
            }).join('');
        }
    } catch(e) { showError('rr-existing', '加载失败: ' + e.message); showToast('❌ 加载面板列表失败: ' + e.message); }
    if (window.lucide) lucide.createIcons();
}
function addRoleRow() {
    if (_rrRoleCount >= 20) { showToast('最多 20 个身份组'); return; }
    _rrRoleCount++;
    const roles = window._rrAvailRoles || [];
    const ropts = roles.map(r => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join('');
    document.getElementById('rr-roles-list').insertAdjacentHTML('beforeend', `
        <div class="rr-row" style="display:flex;align-items:center;gap:8px;padding:10px 12px;background:var(--bg);border:1px solid var(--border-light);border-radius:10px;max-width:560px;">
            <button type="button" class="emoji-trigger rr-emoji-trigger" onclick="openEmojiPicker(this)" aria-label="选择 emoji"><span class="ep-placeholder">🎮</span></button>
            <input type="hidden" class="rr-emoji" value="">
            <select class="cfg-select rr-role" style="flex:1;max-width:none;" aria-label="选择身份组">${ropts}</select>
            <button onclick="this.parentElement.remove();_rrRoleCount--;" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1.1rem;padding:4px 8px;" title="移除" aria-label="移除这一行">✕</button>
        </div>
    `);
}

/* ── Emoji Picker ── */
let _epTab = 'default', _epTarget = null, _epCustom = null;
const EP_DEFAULT_EMOJIS = [
    {e:'😀',k:'笑 smile happy'},{e:'😂',k:'笑哭 lol'},{e:'🥰',k:'爱 love'},{e:'😎',k:'酷 cool'},
    {e:'🥺',k:'求 pleading'},{e:'😭',k:'哭 cry'},{e:'😡',k:'怒 angry'},{e:'🤔',k:'想 think'},
    {e:'😴',k:'睡 sleep'},{e:'🤗',k:'抱 hug'},{e:'😏',k:'坏笑 smirk'},{e:'🙄',k:'翻白眼 eyeroll'},
    {e:'👍',k:'赞 thumbs up like'},{e:'👎',k:'踩 thumbs down'},{e:'👏',k:'拍手 clap'},{e:'🙏',k:'谢谢 thanks pray'},
    {e:'✌️',k:'胜利 peace'},{e:'🤝',k:'握手 handshake'},{e:'💪',k:'肌肉 strong'},{e:'🫡',k:'敬礼 salute'},
    {e:'❤️',k:'红心 heart love'},{e:'🧡',k:'橙心 orange heart'},{e:'💛',k:'黄心 yellow heart'},{e:'💚',k:'绿心 green heart'},
    {e:'💙',k:'蓝心 blue heart'},{e:'💜',k:'紫心 purple heart'},{e:'🖤',k:'黑心 black heart'},{e:'🤍',k:'白心 white heart'},
    {e:'💖',k:'闪心 sparkle heart'},{e:'💗',k:'粉心 pink heart'},{e:'💕',k:'两颗心 two hearts'},{e:'✨',k:'闪 sparkles'},
    {e:'🔥',k:'火 fire'},{e:'⭐',k:'星 star'},{e:'🌟',k:'闪星 glow star'},{e:'⚡',k:'闪电 lightning'},
    {e:'🎉',k:'庆祝 party'},{e:'🎊',k:'彩带 confetti'},{e:'🎁',k:'礼物 gift'},{e:'🏆',k:'奖杯 trophy'},
    {e:'🌸',k:'樱花 cherry blossom'},{e:'🌺',k:'花 flower'},{e:'🌷',k:'郁金香 tulip'},{e:'🌻',k:'向日葵 sunflower'},
    {e:'🌹',k:'玫瑰 rose'},{e:'🍀',k:'四叶草 clover'},{e:'🌈',k:'彩虹 rainbow'},{e:'☀️',k:'太阳 sun'},
    {e:'🌙',k:'月亮 moon'},{e:'⛅',k:'云 cloud'},{e:'❄️',k:'雪 snow'},{e:'🎵',k:'音符 music'},
    {e:'🎮',k:'游戏 game'},{e:'🕹️',k:'摇杆 joystick'},{e:'🎲',k:'骰子 dice'},{e:'🎯',k:'目标 target'},
    {e:'🍕',k:'披萨 pizza'},{e:'🍔',k:'汉堡 burger'},{e:'🍣',k:'寿司 sushi'},{e:'🍰',k:'蛋糕 cake'},
    {e:'☕',k:'咖啡 coffee'},{e:'🍺',k:'啤酒 beer'},{e:'🐱',k:'猫 cat'},{e:'🐶',k:'狗 dog'},
    {e:'🐼',k:'熊猫 panda'},{e:'🦊',k:'狐狸 fox'},{e:'🐰',k:'兔子 bunny'},{e:'🦄',k:'独角兽 unicorn'},
    {e:'✅',k:'对 check yes'},{e:'❌',k:'错 cross no'},{e:'⚠️',k:'警告 warning'},{e:'❓',k:'问号 question'},
    {e:'❗',k:'感叹号 exclamation'},{e:'💯',k:'满分 100'},{e:'🚀',k:'火箭 rocket'},{e:'💎',k:'钻石 diamond'},
];

async function openEmojiPicker(triggerBtn) {
    _epTarget = triggerBtn;
    if (_epCustom === null) {
        try { _epCustom = await api('/emojis'); } catch(e) { _epCustom = []; }
    }
    const picker = document.getElementById('emoji-picker');
    const rect = triggerBtn.getBoundingClientRect();
    picker.style.display = 'flex';
    // Position below trigger, scroll-aware
    picker.style.top = (window.scrollY + rect.bottom + 6) + 'px';
    picker.style.left = (window.scrollX + rect.left) + 'px';
    document.getElementById('ep-search').value = '';
    renderEmojiGrid('');
    // Close on outside click
    setTimeout(() => document.addEventListener('click', closeEmojiPickerOnOutside), 0);
}

function closeEmojiPickerOnOutside(e) {
    const picker = document.getElementById('emoji-picker');
    if (picker.contains(e.target) || (_epTarget && _epTarget.contains(e.target))) return;
    picker.style.display = 'none';
    document.removeEventListener('click', closeEmojiPickerOnOutside);
}

function switchEmojiTab(tab) {
    _epTab = tab;
    document.querySelectorAll('.ep-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    renderEmojiGrid(document.getElementById('ep-search').value);
}

function filterEmojis() {
    renderEmojiGrid(document.getElementById('ep-search').value);
}

function renderEmojiGrid(q) {
    const grid = document.getElementById('ep-grid');
    q = (q || '').toLowerCase().trim();
    let html = '';
    if (_epTab === 'default') {
        const list = q
            ? EP_DEFAULT_EMOJIS.filter(x => x.k.includes(q) || x.e === q)
            : EP_DEFAULT_EMOJIS;
        if (list.length === 0) html = '<div class="ep-empty">没有匹配的 emoji</div>';
        else html = list.map(x =>
            `<button class="ep-item" type="button" onclick="pickEmoji(${JSON.stringify(x.e).replace(/"/g,'&quot;')})">${x.e}</button>`
        ).join('');
    } else {
        const list = q ? (_epCustom||[]).filter(x => x.name.toLowerCase().includes(q)) : (_epCustom||[]);
        if (list.length === 0) html = '<div class="ep-empty">服务器没有自定义 emoji</div>';
        else html = list.map(x => {
            const code = `<${x.animated?'a':''}:${x.name}:${x.id}>`;
            const safe = JSON.stringify(code).replace(/"/g,'&quot;');
            return `<button class="ep-item" type="button" title=":${escapeHtml(x.name)}:" onclick="pickEmoji(${safe},'${x.url}')"><img src="${x.url}" alt=""></button>`;
        }).join('');
    }
    grid.innerHTML = html;
}

function pickEmoji(code, imgUrl) {
    if (!_epTarget) return;
    const row = _epTarget.parentElement;
    row.querySelector('.rr-emoji').value = code;
    if (imgUrl) {
        _epTarget.innerHTML = `<img src="${imgUrl}" alt="">`;
    } else {
        _epTarget.innerHTML = code;
    }
    document.getElementById('emoji-picker').style.display = 'none';
    document.removeEventListener('click', closeEmojiPickerOnOutside);
}
async function sendRRPanel() {
    const ch = document.getElementById('rr-ch').value;
    const title = document.getElementById('rr-title').value || '🏷 身份组选择';
    const content = document.getElementById('rr-content').value || '点击下方的按钮来领取身分组';
    const exclusive = document.getElementById('rr-exclusive').checked;
    if (ch === '0') { showToast('请选择发送频道'); return; }
    const rows = document.querySelectorAll('.rr-row');
    if (rows.length === 0) { showToast('请至少添加一个身份组'); return; }
    const mappings = [];
    for (const row of rows) {
        const emoji = row.querySelector('.rr-emoji').value.trim();
        const roleSel = row.querySelector('.rr-role');
        const roleId = roleSel.value;
        const roleName = roleSel.options[roleSel.selectedIndex].text;
        if (!emoji) { showToast('每个身份组都需要选择 emoji'); return; }
        mappings.push({ emoji, role_id: roleId, role_name: roleName });
    }
    const btn = document.getElementById('rr-send'); btn.disabled = true; btn.textContent = '发送中…';
    try {
        const r = await api('/reactionroles/send', 'POST', { channel_id: ch, title, content, mappings, exclusive });
        if (r.ok) {
            showToast('✅ 身份组面板已发送到频道!');
            _rrLoaded = false; loadRolesPage();
        } else { showToast('❌ ' + (r.error || '发送失败')); }
    } catch(e) { showToast('❌ 网络错误'); }
    btn.disabled = false; btn.textContent = '送出';
}

/* ── Giveaway creation ── */
let _gwPageLoaded = false;
async function loadGiveawayPage() {
    if (_gwPageLoaded) return; _gwPageLoaded = true;
    const [ch, roles] = await Promise.all([getCh(), getRoles()]);
    chOpts('gw-ch', ch, 0);
    const rsel = document.getElementById('gw-role');
    rsel.innerHTML = '<option value="0">@ 不限制</option>' + roles.map(r => `<option value="${r.id}">@ ${escapeHtml(r.name)}</option>`).join('');
    // Set default end time to 24h from now
    const d = new Date(Date.now() + 86400000);
    document.getElementById('gw-end').value = d.toISOString().slice(0, 16);
    loadGiveaways(); // Load existing list
}
async function createGiveaway() {
    const prize = document.getElementById('gw-prize').value.trim();
    const winners = +document.getElementById('gw-winners').value;
    const ch = document.getElementById('gw-ch').value;
    const endStr = document.getElementById('gw-end').value;
    const role = document.getElementById('gw-role').value;
    if (!prize) { showToast('请输入奖项名称'); return; }
    if (ch === '0') { showToast('请选择发起频道'); return; }
    if (!endStr) { showToast('请选择结束时间'); return; }
    const endTime = Math.floor(new Date(endStr).getTime() / 1000);
    if (endTime <= Math.floor(Date.now() / 1000)) { showToast('结束时间必须在未来'); return; }
    const btn = document.getElementById('gw-create-btn'); btn.disabled = true; btn.textContent = '建立中…';
    try {
        const r = await api('/giveaway/create', 'POST', {
            prize, winners_count: winners, channel_id: ch,
            end_time: endTime, restrict_role: role !== '0' ? role : null
        });
        if (r.ok) {
            showToast('✅ 抽奖活动已建立！');
            document.getElementById('gw-prize').value = '';
            _gwPageLoaded = false; loadGiveawayPage();
        } else { showToast('❌ ' + (r.error || '建立失败')); }
    } catch(e) { showToast('❌ 网络错误'); }
    btn.disabled = false; btn.textContent = '建立';
}

/* ── Bot Personalizer ── */
let _bpLoaded = false, _avData = null;
async function loadPersonalizer() {
    if (_bpLoaded) return; _bpLoaded = true;
    try {
        const cfg = await apiGlobal('/api/bot/personalizer');
        document.getElementById('bp-status').value = cfg.bot_status || 'online';
        document.getElementById('bp-atype').value = cfg.activity_type || 'watching';
        document.getElementById('bp-atext').value = cfg.activity_text || '';
        updatePreview();
    } catch(e) { showToast('❌ 加载 Bot 配置失败: ' + e.message); }
}
function updatePreview() {
    const atype = document.getElementById('bp-atype').value;
    const atext = document.getElementById('bp-atext').value;
    const status = document.getElementById('bp-status').value;
    const labels = {watching:'观看中',playing:'游玩中',listening:'收听',competing:'竞争中',custom:'',none:''};
    const emojis = {watching:'👀',playing:'🎮',listening:'🎧',competing:'🏆',custom:'💬',none:''};
    const act = atype === 'none' ? '' : `${emojis[atype]||''} ${labels[atype]||''} ${atext}`.trim();
    document.getElementById('prev-act').textContent = act || '无活动';
    document.getElementById('prev-act2').textContent = act || '无活动';
    const dot = document.getElementById('prev-dot');
    const dColors = {online:'#23A559',idle:'#F0B232',dnd:'#F23F43',invisible:'#80848E'};
    dot.style.background = dColors[status] || '#23A559';
}
function previewAvatar(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    const reader = new FileReader();
    reader.onload = function(e) {
        _avData = e.target.result; // data:image/...;base64,...
        ['bp-av-img','prev-av-1','prev-av-2'].forEach(id => {
            const img = document.getElementById(id); img.src = _avData; img.style.display = 'block';
        });
        ['bp-av-placeholder','prev-av-1-ph','prev-av-2-ph'].forEach(id => {
            const el = document.getElementById(id); if(el) el.style.display = 'none';
        });
    };
    reader.readAsDataURL(file);
}
async function uploadAvatar() {
    if (!_avData) { showToast('⚠ 请先选择一张图片'); return; }
    const btn = document.getElementById('bp-av-btn'); btn.textContent = '上传中…'; btn.disabled = true;
    try {
        const d = await apiGlobal('/api/bot/avatar', 'POST', { avatar: _avData });
        if (d.ok) showToast('✅ 头像已更新!');
        else showToast('❌ ' + (d.error || '上传失败'));
    } catch(e) { showToast('❌ 上传失败: ' + e.message); }
    btn.textContent = '上传头像'; btn.disabled = false;
}
async function changeName() {
    const name = document.getElementById('bp-name').value.trim();
    if (!name) { showToast('⚠ 请输入用户名'); return; }
    try {
        const d = await apiGlobal('/api/bot/username', 'POST', { username: name });
        if (d.ok) {
            showToast('✅ 用户名已更新!');
            document.getElementById('prev-name').textContent = name;
            document.getElementById('prev-name2').textContent = name;
        } else { showToast('❌ ' + (d.error || '修改失败')); }
    } catch(e) { showToast('❌ 修改失败: ' + e.message); }
}
async function savePersonalizer() {
    const btn = document.getElementById('bp-save'); btn.disabled = true; btn.textContent = '保存中…';
    try {
        await apiGlobal('/api/bot/personalizer', 'POST', {
            bot_status: document.getElementById('bp-status').value,
            activity_type: document.getElementById('bp-atype').value,
            activity_text: document.getElementById('bp-atext').value,
        });
        btn.textContent = '✅ 已保存!'; showToast('✅ 状态配置已保存,30 秒内生效!');
    } catch(e) { showToast('❌ 保存失败: ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '储存设定'; }, 1500);
}

/* ── Toast ── */
let _tt;
function showToast(msg, type) {
    const el = document.getElementById('toast');
    if (!type) {
        if (msg.startsWith('✅')) type = 'success';
        else if (msg.startsWith('❌')) type = 'error';
        else if (msg.startsWith('⚠')) type = 'warning';
        else type = 'info';
    }
    const icons = { info:'i', success:'✓', error:'✕', warning:'!' };
    const text = msg.replace(/^[❌✅⚠️ℹ️]+\s*/u, '').trim();
    el.className = 'toast toast--' + type;
    el.innerHTML = `<span class="toast-icon">${icons[type]}</span><span>${escapeHtml(text)}</span>`;
    requestAnimationFrame(() => el.classList.add('show'));
    clearTimeout(_tt);
    _tt = setTimeout(() => el.classList.remove('show'), 2800);
}

// Initialize Lucide icons
document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) lucide.createIcons();
    loadOverviewStats();
    loadModules();
    loadGuildInfo();
});

async function loadGuildInfo() {
    try {
        const info = await api('/info');
        const m = document.getElementById('ov-members');
        const o = document.getElementById('ov-online');
        const t = document.getElementById('ov-text-ch');
        const v = document.getElementById('ov-voice-ch');
        const j = document.getElementById('ov-joined');
        if (m) m.textContent = (info.member_count || 0).toLocaleString();
        if (o) o.textContent = (info.online_count || 0).toLocaleString();
        if (t) t.textContent = info.text_channels || 0;
        if (v) v.textContent = info.voice_channels || 0;
        if (j) j.textContent = info.bot_joined_at ? formatJoinDuration(info.bot_joined_at) : '—';
    } catch(e) {
        console.error('loadGuildInfo', e);
    }
}

function formatJoinDuration(iso) {
    const joined = new Date(iso);
    const now = new Date();
    const days = Math.floor((now - joined) / 86400000);
    if (days < 1) return '今天';
    if (days < 30) return `${days} 天`;
    if (days < 365) return `${Math.floor(days / 30)} 个月`;
    const years = Math.floor(days / 365);
    const remMonths = Math.floor((days % 365) / 30);
    return remMonths > 0 ? `${years} 年 ${remMonths} 个月` : `${years} 年`;
}

/* ── Bot Log ── */
let _blLoaded = false;
async function loadBotLog() {
    if (_blLoaded) return; _blLoaded = true;
    try {
        const [ch, cfg] = await Promise.all([getCh(), api('/botlog')]);
        chOpts('bl-ch', ch, cfg.channel_id);
        document.getElementById('bl-enabled').checked = !!cfg.enabled;
        const wanted = new Set(cfg.levels || []);
        document.querySelectorAll('#pg-botlog .bl-chip input').forEach(inp => {
            inp.checked = wanted.has(inp.value);
        });
        document.querySelectorAll('#bl-ch,#bl-enabled,#pg-botlog .bl-chip input').forEach(el =>
            el.addEventListener('change', () => markDirty('bl-savebar'))
        );
    } catch(e) { showToast('❌ 加载日志配置失败: ' + e.message); }
}

async function saveBotLog() {
    const btn = document.getElementById('bl-save'); btn.disabled = true; btn.textContent = '保存中…';
    try {
        const levels = [...document.querySelectorAll('#pg-botlog .bl-chip input:checked')].map(i => i.value);
        await api('/botlog', 'POST', {
            channel_id: document.getElementById('bl-ch').value,
            enabled: document.getElementById('bl-enabled').checked,
            levels,
        });
        btn.textContent = '✅ 已保存!'; showToast('✅ 日志配置已保存!'); markClean('bl-savebar');
    } catch(e) { showToast('❌ 保存失败: ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '储存设定'; }, 1500);
}

async function testBotLog() {
    const btn = document.getElementById('bl-test'); btn.disabled = true; btn.textContent = '发送中…';
    try {
        await api('/botlog/test', 'POST', {});
        showToast('✅ 测试消息已发送!');
    } catch(e) { showToast('❌ ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '📤 发送测试日志'; }, 1500);
}

/* ── Server Log (审计日志) ── */
let _slLoaded = false;
async function loadServerLog() {
    if (_slLoaded) return; _slLoaded = true;
    try {
        const [ch, cfg] = await Promise.all([getCh(), api('/serverlog')]);
        chOpts('sl-ch', ch, cfg.channel_id);
        document.getElementById('sl-enabled').checked = !!cfg.enabled;
        const wanted = new Set(cfg.categories || []);
        document.querySelectorAll('#pg-serverlog .bl-chip input').forEach(inp => {
            inp.checked = wanted.has(inp.value);
        });
        document.querySelectorAll('#sl-ch,#sl-enabled,#pg-serverlog .bl-chip input').forEach(el =>
            el.addEventListener('change', () => markDirty('sl-savebar'))
        );
    } catch(e) { showToast('❌ 加载审计日志配置失败: ' + e.message); }
}

async function saveServerLog() {
    const btn = document.getElementById('sl-save'); btn.disabled = true; btn.textContent = '保存中…';
    try {
        const categories = [...document.querySelectorAll('#pg-serverlog .bl-chip input:checked')].map(i => i.value);
        await api('/serverlog', 'POST', {
            channel_id: document.getElementById('sl-ch').value,
            enabled: document.getElementById('sl-enabled').checked,
            categories,
        });
        btn.textContent = '✅ 已保存!'; showToast('✅ 审计日志配置已保存!'); markClean('sl-savebar');
    } catch(e) { showToast('❌ 保存失败: ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '储存设定'; }, 1500);
}

async function testServerLog() {
    const btn = document.getElementById('sl-test'); btn.disabled = true; btn.textContent = '发送中…';
    try {
        await api('/serverlog/test', 'POST', {});
        showToast('✅ 测试消息已发送!');
    } catch(e) { showToast('❌ ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '📤 发送测试'; }, 1500);
}

async function loadModules() {
    try {
        const r = await fetch('/api/modules');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const mods = await r.json();
        renderSidebar(mods);
        renderOverviewCards(mods);
        if (window.lucide) lucide.createIcons();
    } catch(e) {
        console.error('loadModules', e);
        document.getElementById('ov-modules').innerHTML = '<div class="error-state">模块列表加载失败</div>';
        showToast('❌ 模块列表加载失败: ' + e.message);
    }
}

function renderSidebar(mods) {
    const sb = document.getElementById('side-modules');
    const overviewLi = sb.querySelector('li');
    sb.innerHTML = '';
    sb.appendChild(overviewLi);
    for (const m of mods) {
        const li = document.createElement('li');
        li.innerHTML = `<a class="nav-link" data-mod="${m.slug}" role="button" tabindex="0" onclick="go('${m.slug}')">
            <i data-lucide="${m.icon}" style="width:16px;height:16px;"></i> ${escapeHtml(m.name)}
            <span class="nav-status ${m.loaded ? 'on' : 'off'}"></span>
        </a>`;
        sb.appendChild(li);
    }
}

function renderOverviewCards(mods) {
    const grid = document.getElementById('ov-modules');
    grid.innerHTML = mods.map(m => `
        <div class="mod-card ${m.loaded ? '' : 'mod-card--off'}" ${m.loaded ? `onclick="go('${m.slug}')"` : ''}>
            <div class="mod-card-head">
                <div class="mod-card-icon"><i data-lucide="${m.icon}" style="width:22px;height:22px;"></i></div>
                <div class="mod-card-name">${m.name}</div>
                <span class="mod-status-badge ${m.loaded ? '' : 'mod-status-badge--off'}">${m.loaded ? '已启用' : '未启用'}</span>
            </div>
            <div class="mod-card-desc">${m.desc}</div>
            <div class="mod-card-btn">${m.loaded ? '开始设定 →' : '暂不可用'}</div>
        </div>
    `).join('');
}