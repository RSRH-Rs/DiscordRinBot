/* 指令大全：搜索、高亮、选中一条后在详情栏（窄屏是行内）画出 Discord 输入框。列表本身由服务器渲染。 */
window.RinCommands = (() => {
    const CJK = /[　-鿿＀-￯]/;
    const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[ch]);

    /* 搜索词：不分大小写，去掉开头的一个 / */
    function normalize(q) {
        const s = String(q ?? '').trim().toLowerCase();
        return s.startsWith('/') ? s.slice(1).trim() : s;
    }

    function matches(cmd, q) {
        const needle = normalize(q);
        if (!needle) return true;
        const fields = [cmd.name, cmd.zh, cmd.en, ...(cmd.params || []).flatMap(p => [p.name, p.zh, p.zh_desc, p.en])];
        return fields.some(s => String(s ?? '').toLowerCase().includes(needle));
    }

    /* 转义后的 HTML，第一处匹配包在 <mark> 里 */
    function highlight(text, q) {
        const s = String(text ?? '');
        const needle = normalize(q);
        const i = needle ? s.toLowerCase().indexOf(needle) : -1;
        if (i < 0) return esc(s);
        return esc(s.slice(0, i)) + '<mark>' + esc(s.slice(i, i + needle.length)) + '</mark>' + esc(s.slice(i + needle.length));
    }

    /* 英文模式下，带中日韩文字的例子不显示 */
    function examplesFor(cmd, lang) {
        const list = cmd.examples || [];
        return lang === 'zh' ? list : list.filter(e => !CJK.test(e));
    }

    /* 输入框里的槽位：必填参数，加上当前看的那个可不填参数 */
    function slotsFor(cmd, focus) {
        const params = cmd.params || [];
        const cur = params[focus];
        const shown = params.filter(p => p.required || p === cur);
        const optional = params.filter(p => !p.required).length;
        return {shown, rest: optional - (cur && !cur.required ? 1 : 0)};
    }

    /* 一条指令默认需要的全部权限，按当前语言连成一句；不需要权限时为 null */
    function permText(perms, labels, lang) {
        if (!perms || !perms.length) return null;
        const i = lang === 'zh' ? 0 : 1;
        return perms.map(p => labels[p][i]).join(lang === 'zh' ? '、' : ', ');
    }

    function step(ids, current, delta) {
        if (!ids.length) return null;
        const i = ids.indexOf(current);
        if (i < 0) return ids[0];
        return ids[Math.max(0, Math.min(ids.length - 1, i + delta))];
    }

    function idFromHash(hash, ids) {
        let id;
        try { id = decodeURIComponent(String(hash || '').replace(/^#/, '')); } catch (e) { return null; }
        return id && ids.includes(id) ? id : null;
    }

    const api = {normalize, matches, highlight, examplesFor, slotsFor, permText, step, idFromHash};
    const dataEl = document.getElementById('commands-data');
    if (!dataEl) return api;

    /* ── 页面 ── */
    const data = JSON.parse(dataEl.textContent);
    const byId = new Map(data.commands.map(c => [c.id, c]));
    const groupOf = new Map(data.groups.map(g => [g.key, g]));
    const ids = data.commands.map(c => c.id);
    const root = document.documentElement;
    const $ = id => document.getElementById(id);
    const q = $('q'), panel = $('panel'), list = $('list'), found = $('found'), toast = $('toast');
    const defaultFound = found.innerHTML;
    const narrow = matchMedia('(max-width: 1079px)');
    const lang = () => root.getAttribute('data-lang') === 'en' ? 'en' : 'zh';
    const L = (zh, en) => lang() === 'zh' ? zh : en;
    const both = (zh, en) => `<span data-l="zh">${zh}</span><span data-l="en" lang="en">${en}</span>`;
    let sel = null, focusOpt = 0, visible = ids.slice(), toastTimer = 0;

    const pname = p => L(p.zh || p.name, p.name);
    const pdesc = p => L(p.zh_desc || p.en, p.en);
    const desc = c => L(c.zh || c.en, c.en);
    const permOf = c => permText(c.perms, data.perm_labels, lang());

    function filter() {
        const term = q.value;
        visible = [];
        for (const row of list.querySelectorAll('.row')) {
            const cmd = byId.get(row.dataset.id);
            const show = matches(cmd, term);
            row.hidden = !show;
            if (show) visible.push(cmd.id);
            row.querySelectorAll('[data-hl]').forEach(el => {
                if (normalize(term)) el.innerHTML = highlight(el.dataset.text, term); else el.textContent = el.dataset.text;
            });
        }
        for (const sec of list.querySelectorAll('.sec')) {
            const n = sec.querySelectorAll('.row:not([hidden])').length;
            const total = +sec.dataset.total;
            sec.hidden = n === 0;
            sec.querySelector('[data-count]').innerHTML = normalize(term) ? both(`${n} / ${total} 条`, `${n} of ${total}`) : both(`${total} 条`, `${total}`);
            const chan = document.querySelector(`[data-chan="${sec.dataset.group}"]`);
            if (chan) { chan.hidden = n === 0; chan.querySelector('.n').textContent = n; }
        }
        const empty = $('empty');
        empty.hidden = visible.length > 0;
        empty.querySelectorAll('[data-q-echo]').forEach(b => { b.textContent = term; });
        found.innerHTML = !normalize(term) ? defaultFound : visible.length ? both(`找到 ${visible.length} 条`, `${visible.length} found`) : '';
        $('clear').hidden = !term;
        if (sel && !visible.includes(sel) && visible.length) select(visible[0]);
        else render();
    }

    function dcm(c) {
        const {shown, rest} = slotsFor(c, focusOpt);
        const cur = c.params[focusOpt];
        const slots = shown.map(p => `<span class="slot${p === cur ? ' on' : ''}">${esc(pname(p))}</span>`).join('');
        const pop = cur
            ? `<div class="dcm-opt"><b>${esc(pname(cur))}</b><span class="need">${cur.required ? L('必填', 'required') : L('可不填', 'optional')}</span><span class="d">${esc(pdesc(cur))}</span></div>`
            : `<div class="dcm-opt"><b>/${esc(c.name)}</b><span class="d">${esc(desc(c))}</span></div>`;
        return `<div class="dcm" aria-label="${L('在 Discord 输入框里的样子', 'How it looks in the Discord message box')}">
            <div class="dcm-pop"><div class="dcm-app"><img src="${esc(panel.dataset.avatar)}" alt="">${L('小凛', 'Rin')}</div>${pop}</div>
            <div class="dcm-in"><span class="c">/${esc(c.name)}</span>${slots}${rest > 0 ? `<span class="more">${L(`+${rest} 个可不填`, `+${rest} optional`)}</span>` : ''}</div></div>`;
    }

    function detail(c) {
        const g = groupOf.get(c.group);
        const perm = permOf(c);
        const lock = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
        const who = perm
            ? `<p class="who">${lock}${L(`需要 <b>${esc(perm)}</b> 权限`, `Needs <b>${esc(perm)}</b>`)}</p>`
            : `<p class="who">${L('所有人都能用', 'Everyone can use it')}</p>`;
        const params = c.params.length ? `<div class="block"><h4>${L('参数', 'Options')}</h4><ul class="params">${c.params.map((p, i) =>
            `<li><button type="button" data-opt="${i}" class="${i === focusOpt ? 'on' : ''}" title="${L('在上面的输入框里看它的位置', 'Show it in the box above')}"><span class="pn">${esc(pname(p))}<span class="tag">${p.required ? L('必填', 'required') : L('可不填', 'optional')}</span></span><span class="pd">${esc(pdesc(p))}</span></button></li>`).join('')}</ul></div>` : '';
        const ex = examplesFor(c, lang());
        const exHtml = ex.length ? `<div class="block"><h4>${L('例子', 'Examples')}</h4><ul class="ex">${ex.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div>` : '';
        const copyIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
        const dash = g && g.dashboard ? `<a href="/dashboard">${esc(L(`在控制台的「${g.dashboard_zh}」里也能设置`, `Also set up in the dashboard under ${g.dashboard_en}`))}</a>` : '';
        const note = perm ? `<p class="note">${L('想让更多人或更少人能用，在 Discord 的「服务器设置 › 整合 › 小凛」里改。', 'To let more or fewer people use it, go to Server Settings › Integrations › Rin in Discord.')}</p>` : '';
        return `${who}${dcm(c)}${params}${exHtml}<div class="acts"><button type="button" class="copy" data-copy="/${esc(c.name)}">${copyIcon}${L('复制', 'Copy')} /${esc(c.name)}</button>${dash}</div>${note}`;
    }

    function render() {
        list.querySelectorAll('.inline-panel').forEach(el => el.remove());
        list.querySelectorAll('.row').forEach(row => row.setAttribute('aria-selected', String(row.dataset.id === sel)));
        const c = byId.get(sel);
        if (!c || !visible.includes(sel)) { panel.hidden = true; return; }
        if (narrow.matches) {
            panel.hidden = true;
            const box = document.createElement('div');
            box.className = 'inline-panel';
            box.innerHTML = detail(c);
            $('r-' + c.id).insertAdjacentElement('afterend', box);
        } else {
            panel.hidden = false;
            panel.innerHTML = `<div><h3>/${esc(c.name)}</h3><p class="lead">${esc(desc(c))}</p></div>${detail(c)}`;
        }
    }

    function select(id, {scroll = false, focus = false, writeHash = true} = {}) {
        sel = id; focusOpt = 0;
        if (writeHash) history.replaceState(null, '', '#' + id);
        render();
        const row = $('r-' + id);
        if (row && scroll) row.scrollIntoView({block: 'nearest'});
        if (row && focus) row.focus({preventScroll: !scroll});
    }

    function focusParam(i) {
        if (i === focusOpt) return;
        focusOpt = i;
        const c = byId.get(sel);
        const box = narrow.matches ? list.querySelector('.inline-panel') : panel;
        if (!c || !box) return;
        box.querySelector('.dcm').outerHTML = dcm(c);
        box.querySelectorAll('[data-opt]').forEach(b => b.classList.toggle('on', +b.dataset.opt === focusOpt));
    }

    function syncLanguage() {
        const text = L('搜索指令、功能或参数', 'Search commands, features or options');
        q.placeholder = text;
        q.setAttribute('aria-label', text);
        list.querySelectorAll('.row').forEach(row => { row.querySelector('.desc').title = desc(byId.get(row.dataset.id)); });
        render();
    }

    list.addEventListener('click', e => {
        const row = e.target.closest('.row');
        if (row) { select(row.dataset.id); return; }
        const sugg = e.target.closest('[data-q-zh]');
        if (sugg) { q.value = L(sugg.dataset.qZh, sugg.dataset.qEn); filter(); q.focus(); }
    });
    document.addEventListener('click', e => {
        const opt = e.target.closest('[data-opt]');
        if (opt) { focusParam(+opt.dataset.opt); return; }
        const copy = e.target.closest('[data-copy]');
        if (copy) {
            const text = copy.dataset.copy;
            if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
            toast.textContent = L(`已复制 ${text}，在 Discord 里粘贴后选中它`, `Copied ${text}. Paste it in Discord and pick it from the list`);
            toast.classList.add('show');
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => toast.classList.remove('show'), 2200);
        }
    });
    document.addEventListener('mouseover', e => {
        const opt = e.target.closest('[data-opt]');
        if (opt) focusParam(+opt.dataset.opt);
    });
    $('clear').addEventListener('click', () => { q.value = ''; filter(); q.focus(); });
    q.addEventListener('input', filter);
    document.addEventListener('keydown', e => {
        const a = document.activeElement;
        const typing = a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable);
        if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); q.focus(); q.select(); return; }
        if (a === q && e.key === 'Escape') { q.value = ''; filter(); return; }
        if (a === q && e.key === 'Enter' && visible.length) { e.preventDefault(); select(visible[0], {scroll: true}); return; }
        const inList = a === q || (a && a.classList && a.classList.contains('row'));
        if (inList && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && visible.length) {
            e.preventDefault();
            select(step(visible, sel, e.key === 'ArrowDown' ? 1 : -1), {scroll: true, focus: a !== q});
        }
    });
    document.addEventListener('rin:lang', () => { syncLanguage(); filter(); });
    /* 同一页里换了 #指令（站内链接、浏览器后退），选中跟着变；#g-分组 这种侧栏链接不算 */
    addEventListener('hashchange', () => {
        const id = idFromHash(location.hash, ids);
        if (id && id !== sel) {
            if (!visible.includes(id)) { q.value = ''; filter(); }
            select(id, {scroll: true, writeHash: false});
        }
    });
    narrow.addEventListener('change', render);

    const fromHash = idFromHash(location.hash, ids);
    sel = fromHash || ids[0];
    syncLanguage();
    if (fromHash) $('r-' + fromHash).scrollIntoView({block: 'center'});
    return api;
})();
