const GID = window.GID || "";
let _ch = null, _roles = null, _chPromise = null, _rolesPromise = null;
/* ── Navigation ── */
/* Legacy module pages, driven by Console's router until each page is rebuilt. */
const legacyLoaders = {
    automod: () => loadAutoMod(), moderation: () => loadModeration(),
    giveaway: () => { loadGiveaways(); loadGiveawayPage(); }, leveling: () => loadLeaderboard(), utility: () => loadUtility(),
    botlog: () => loadBotLog(), serverlog: () => loadServerLog(),
};
document.addEventListener('console:page', e => {
    legacyLoaders[e.detail.slug]?.();
    window.DashboardPreview?.refresh();
});
window.legacyInvalidate = slug => {
    if (DashboardUI.dirty('pg-' + slug)) return;
    if (slug === 'automod') _amLoaded = false;
    if (slug === 'botlog') _blLoaded = false;
    if (slug === 'serverlog') _slLoaded = false;
};

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
async function getCh() {
    if (_ch !== null) return _ch;
    if (!_chPromise) {
        _chPromise = api('/channels')
            .then(data => { _ch = data; return data; })
            .finally(() => { _chPromise = null; });
    }
    return _chPromise;
}
async function getRoles() {
    if (_roles !== null) return _roles;
    if (!_rolesPromise) {
        _rolesPromise = api('/roles')
            .then(data => { _roles = data; return data; })
            .finally(() => { _rolesPromise = null; });
    }
    return _rolesPromise;
}

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
    if (bar) DashboardUI.changed(bar.closest('.mod-page'));
}
function markClean(barId) {
    const bar = document.getElementById(barId);
    if (bar) DashboardUI.clean(bar.closest('.mod-page'));
    Console.refreshModules();
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
    } catch(e) { _amLoaded=false; throw e; }
}
async function saveAutoMod() {
    const btn = document.getElementById('am-save'); btn.disabled = true; btn.textContent = '保存中…';
    try {
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
    } catch(e) { showToast('❌ 保存失败，输入已保留，可重试：' + e.message); }
    finally { btn.disabled = false; btn.textContent = '保存设置'; }
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
    if (!cases || cases.length === 0) { el.innerHTML = '<div class="empty-state-sm">暂无管理记录</div>'; }
    const colors = {kick:'#E8899A',ban:'#E24B4A',tempban:'#E24B4A',mute:'#EF9F27',warn:'#FFD166',unban:'#5A9E6F',unmute:'#5A9E6F',purge:'#85B7EB'};
    if(cases?.length) el.innerHTML = cases.map(c => {
        const d = new Date(c.created_at * 1000);
        const ts = d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
        return `<div class="case-item"><div class="case-head"><span class="case-action" style="color:${colors[c.action]||'var(--text)'}">#${c.case_no ?? c.id} ${c.action}</span><span class="case-time">${ts}</span></div><div class="case-body">${escapeHtml(c.user_name || c.user_id)} · 管理员: ${escapeHtml(c.mod_name || c.mod_id)} · 原因: ${escapeHtml(c.reason)}${c.duration?' · 时长: '+c.duration:''}</div></div>`;
    }).join('');
    // Dirty listeners
    document.querySelectorAll('#mod-log,#mod-mt,#mod-md,#mod-kt,#mod-bt').forEach(el => el.addEventListener('change', () => markDirty('mod-savebar')));
    } catch(e) { _modLoaded=false; throw e; }
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
    setTimeout(() => { btn.disabled = false; btn.textContent = '保存设置'; }, 1500);
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
        `<span class="tag-chip">${escapeHtml(w)}<button type="button" class="tag-rm" aria-label="移除此项" onclick="removeTag(this)">×</button></span>`
    ).join('');
}
function addTag(prefix) {
    const inp = document.getElementById(prefix + '-new');
    const w = inp.value.trim(); if (!w) return; inp.value = '';
    document.getElementById(prefix + '-tags').insertAdjacentHTML('beforeend',
        `<span class="tag-chip">${escapeHtml(w)}<button type="button" class="tag-rm" aria-label="移除此项" onclick="removeTag(this)">×</button></span>`);
    DashboardUI.changed('pg-automod');
}
function removeTag(button){button.parentElement.remove();DashboardUI.changed('pg-automod');}
function collectTags(id) {
    return [...document.querySelectorAll('#' + id + ' .tag-chip')].map(t => t.firstChild.textContent.trim());
}

/* ── Utility (Command Toggle) ── */
let _cmdData = null, _cmdPromise = null;
async function getCommands(){
    if(_cmdData!==null)return _cmdData;
    if(!_cmdPromise)_cmdPromise=api('/commands').then(data=>{_cmdData=data;return data;}).finally(()=>{_cmdPromise=null;});
    return _cmdPromise;
}

let _cmdSaving=false;
window.addEventListener('beforeunload',e=>{if(_cmdSaving){e.preventDefault();e.returnValue='';}});
function matchingCommands(){
    const query=document.getElementById('command-search').value;
    const state=document.getElementById('command-filter').value;
    return (_cmdData||[]).filter(c=>DashboardExtras.matches(c.name+' '+c.desc+' '+c.cog,query) &&
        (state==='all'||(state==='enabled'?c.enabled:!c.enabled)));
}
async function loadUtility() {
    if(_cmdSaving)return;
    const el=document.getElementById('util-commands');
    try{
        if(!_cmdData){showSkeleton('util-commands',4);await getCommands();}
        renderUtility();
    }catch(e){
        el.replaceChildren();
        const message=document.createElement('p');message.textContent='指令读取失败，请重试。';
        const retry=document.createElement('button');retry.className='tag-add-btn';retry.textContent='重试';retry.onclick=()=>{_cmdData=null;loadUtility();};
        el.append(message,retry);
    }
}
function renderUtility(){
    if(!_cmdData)return;
    const el=document.getElementById('util-commands');
    const opened=new Set([...el.querySelectorAll('details[open]')].map(d=>d.dataset.cog));
    const filtering=!!document.getElementById('command-search').value.trim()||document.getElementById('command-filter').value!=='all';
    const visible=matchingCommands();
    const groups=new Map();
    visible.forEach(c=>{if(!groups.has(c.cog))groups.set(c.cog,[]);groups.get(c.cog).push(c);});
    el.replaceChildren();
    for(const [cog,commands] of groups){
        const group=document.createElement('details');group.className='command-group';group.dataset.cog=cog;group.open=filtering||opened.has(cog);
        const summary=document.createElement('summary');summary.textContent=cog+' · '+commands.length+' 条';group.append(summary);
        const bulk=document.createElement('button');bulk.type='button';bulk.className='tag-add-btn command-bulk';
        const editable=commands.filter(c=>!c.protected),allOn=editable.length>0&&editable.every(c=>c.enabled);
        bulk.textContent=(allOn?'关闭':'开启')+'本组'+(filtering?'筛选结果':'全部')+'（'+editable.length+' 条）';
        bulk.disabled=_cmdSaving||!editable.length;bulk.onclick=()=>toggleCategory(cog,!allOn);group.append(bulk);
        for(const c of commands){
            const row=document.createElement('div');row.className='cmd-row';row.id='cr-'+c.name;
            const info=document.createElement('div');info.className='cmd-info';
            const name=document.createElement('div');name.className='cmd-name';name.textContent=c.name;
            const desc=document.createElement('div');desc.className='cmd-desc';desc.textContent=c.desc+(c.protected?' · 必需指令，不可关闭':'');
            info.append(name,desc);
            const label=document.createElement('label');label.className='cfg-tog';
            const input=document.createElement('input');input.type='checkbox';input.checked=c.enabled;input.disabled=c.protected||_cmdSaving;
            input.setAttribute('aria-label','启用 /'+c.name);input.onchange=()=>toggleCommand(c.name,input.checked,cog);
            const track=document.createElement('span');track.className='track';const thumb=document.createElement('span');thumb.className='thumb';
            label.append(input,track,thumb);row.append(info,label);group.append(row);
        }
        el.append(group);
    }
    if(!visible.length){const empty=document.createElement('p');empty.className='empty-state-sm';empty.textContent='没有匹配的指令，换个关键词或筛选条件试试吧。';el.append(empty);}
    el.inert=_cmdSaving;
    document.getElementById('util-search-status').textContent='显示 '+visible.length+' / '+_cmdData.length+' 条指令';
    updateSummary();
}
async function changeCommands(commands,enabled){
    if(_cmdSaving||!commands.length)return;
    _cmdSaving=true;
    document.getElementById('util-commands').inert=true;
    try{
        const body=commands.length===1?{name:commands[0].name,enabled}:{names:commands.map(c=>c.name),enabled};
        const result=await api(commands.length===1?'/commands/toggle':'/commands/bulk-toggle','POST',body);
        if(!result.ok)throw new Error(result.error||'操作失败');
        commands.forEach(c=>{c.enabled=enabled;});
        showToast('✅ 已'+(enabled?'开启':'关闭')+' '+commands.length+' 条指令');
    }catch(e){showToast('❌ 修改失败，开关已恢复：'+e.message);}
    finally{_cmdSaving=false;renderUtility();}
}
async function toggleCommand(name,enabled){
    return changeCommands((_cmdData||[]).filter(c=>c.name===name&&!c.protected),enabled);
}
async function toggleCategory(cog,enabled){
    return changeCommands(matchingCommands().filter(c=>c.cog===cog&&!c.protected),enabled);
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

/* ── Giveaway creation ── */
let _gwPageLoaded = false;
async function loadGiveawayPage() {
    if (_gwPageLoaded) return; _gwPageLoaded = true;
    try {
        const [ch, roles] = await Promise.all([getCh(), getRoles()]);
        chOpts('gw-ch', ch, 0);
        const rsel = document.getElementById('gw-role');
        rsel.innerHTML = '<option value="0">@ 不限制</option>' + roles.map(r => `<option value="${r.id}">@ ${escapeHtml(r.name)}</option>`).join('');
        // Set default end time to 24h from now
        const d = new Date(Date.now() + 86400000);
        document.getElementById('gw-end').value = d.toISOString().slice(0, 16);
        loadGiveaways(); // Load existing list
    } catch(e) {
        _gwPageLoaded = false;
        showError('gw-list', '加载频道或身份组失败，请重新打开此页面重试: ' + e.message);
        showToast('❌ 加载抽奖配置失败: ' + e.message);
    }
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
    if (endTime > Math.floor(Date.now() / 1000) + 365 * 86400) { showToast('抽奖最长可以设置 365 天'); return; }
    const btn = document.getElementById('gw-create-btn'); btn.disabled = true; btn.textContent = '建立中…';
    try {
        const r = await api('/giveaway/create', 'POST', {
            prize, winners_count: winners, channel_id: ch,
            end_time: endTime, restrict_role: role !== '0' ? role : null
        });
        if (r.ok) {
            showToast('✅ 抽奖活动已建立！');
            document.getElementById('gw-prize').value = '';
            DashboardUI.clean('pg-giveaway');
            _gwPageLoaded = false; await loadGiveawayPage();
        } else { showToast('❌ ' + (r.error || '建立失败')); }
    } catch(e) { showToast('❌ ' + e.message); }
    btn.disabled = false; btn.textContent = '建立';
}

/* ── Toast ── */
function showToast(msg) {
    const kind = msg.startsWith('✅') ? 'ok' : msg.startsWith('❌') ? 'bad' : 'info';
    Console.toast(msg.replace(/^[❌✅⚠️ℹ️]+\s*/u, '').trim(), kind);
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('command-search').addEventListener('input',renderUtility);
    document.getElementById('command-filter').addEventListener('change',renderUtility);
});

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
    } catch(e) { _blLoaded=false; throw e; }
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
    setTimeout(() => { btn.disabled = false; btn.textContent = '保存设置'; }, 1500);
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
    } catch(e) { _slLoaded=false; throw e; }
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
    setTimeout(() => { btn.disabled = false; btn.textContent = '保存设置'; }, 1500);
}

async function testServerLog() {
    const btn = document.getElementById('sl-test'); btn.disabled = true; btn.textContent = '发送中…';
    try {
        await api('/serverlog/test', 'POST', {});
        showToast('✅ 测试消息已发送!');
    } catch(e) { showToast('❌ ' + e.message); }
    setTimeout(() => { btn.disabled = false; btn.textContent = '📤 发送测试'; }, 1500);
}

// Loaded defaults must not overwrite drafts; failed loads are explicitly retryable.
function guardedLoader(mod, original, loaded){
    let pending=null;
    const wrapped=()=>{
        if(pending)return pending;
        if(loaded())return Promise.resolve();
        pending=DashboardUI.loading('pg-'+mod, async()=>{
            await original();
            if(!loaded())throw new Error('load failed');
            window.DashboardExtras?.refreshSelects();
            window.DashboardPreview?.refresh();
        },wrapped).finally(()=>{pending=null;});
        return pending;
    };
    return wrapped;
}
loadAutoMod=guardedLoader('automod',loadAutoMod,()=>_amLoaded);
loadModeration=guardedLoader('moderation',loadModeration,()=>_modLoaded);
loadBotLog=guardedLoader('botlog',loadBotLog,()=>_blLoaded);
loadServerLog=guardedLoader('serverlog',loadServerLog,()=>_slLoaded);
loadGiveawayPage=guardedLoader('giveaway',loadGiveawayPage,()=>_gwPageLoaded);
for(const [name,mod] of Object.entries({saveAutoMod:'automod',saveModeration:'moderation',saveBotLog:'botlog',saveServerLog:'serverlog',createGiveaway:'giveaway'})){
    const original=window[name];
    window[name]=(...args)=>DashboardUI.saving('pg-'+mod,()=>original(...args));
}
