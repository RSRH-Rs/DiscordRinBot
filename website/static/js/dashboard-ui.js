/* Shared navigation and unsaved-change handling. No settings are auto-saved. */
window.DashboardUI = (() => {
    const drafts = new Map();
    let menuOpener = null;
    const rootOf = id => typeof id === 'string' ? document.getElementById(id) : id;
    function snapshot(root) {
        return JSON.stringify([
            [...root.querySelectorAll('input,select,textarea')].filter(el => !el.matches('[data-draft-ignore]')).map(el => [
                el.id || el.name || el.className,
                el.type === 'file' ? [...el.files].map(f => [f.name,f.size,f.lastModified]) :
                /^(checkbox|radio)$/.test(el.type) ? el.checked : el.value
            ]),
            [...root.querySelectorAll('.tag-chip')].map(el => el.firstChild.textContent)
        ]);
    }
    function refresh(root) {
        const state = drafts.get(root);
        if (!state) return;
        const dirty = snapshot(root) !== state.saved;
        root.classList.toggle('has-unsaved', dirty);
        const bar = root.querySelector('.save-bar');
        if (bar) bar.classList.toggle('dirty', dirty);
        const hint = root.querySelector('.save-hint, .draft-hint');
        if (hint) hint.textContent = state.saving ? '正在保存，请稍等…' : dirty ? '有未保存的更改' : (root.dataset.draftHint || '改好后记得保存哦。');
        const notice = document.getElementById('draft-notice');
        if (notice) notice.hidden = ![...drafts].some(([r,s]) => s.saving || snapshot(r) !== s.saved);
    }
    function register(root) {
        if (drafts.has(root)) return;
        drafts.set(root, {saved:snapshot(root), saving:false});
        if (!root.querySelector('.save-hint, .draft-hint')) {
            const hint = document.createElement('p');
            hint.className = 'draft-hint'; hint.setAttribute('aria-live','polite');
            root.append(hint);
        }
        refresh(root);
    }
    function clean(id) {
        const root = rootOf(id); if (!root) return;
        register(root);
        const state = drafts.get(root);
        state.saved = snapshot(root);
        refresh(root);
    }
    function changed(id) { const root=rootOf(id); if(root)refresh(root); }
    function dirty(id) { const root=rootOf(id), state=drafts.get(root); return !!state && (state.saving || snapshot(root)!==state.saved); }
    function confirmSwitch(id) {
        const root=rootOf(id);
        if (!root || !dirty(root)) return true;
        if (drafts.get(root).saving) return false;
        return window.confirm('这一页还有未保存的更改。切换后会暂时保留，但刷新或离开控制台会丢失。仍要切换吗？');
    }
    async function saving(id, action) {
        const root=rootOf(id); if(!root)return action();
        register(root);
        const state=drafts.get(root);
        if(state.saving)return;
        state.saving=true;
        const wasInert=root.inert;
        root.inert=true; root.setAttribute('aria-busy','true'); refresh(root);
        try { return await action(); }
        finally { state.saving=false; root.inert=wasInert || !!state.unread; root.removeAttribute('aria-busy'); refresh(root); }
    }
    async function loading(id, action, retry) {
        const root=rootOf(id);
        register(root);
        const state=drafts.get(root);
        state.unread=true;
        const feedbackId=id+'-load-feedback';
        document.getElementById(feedbackId)?.remove();
        root.inert=true;
        root.setAttribute('aria-busy','true');
        try { await action(); state.unread=false; clean(root); root.inert=state.saving; }
        catch(e) {
            const feedback=document.createElement('div');
            feedback.id=feedbackId;feedback.className='load-feedback';feedback.setAttribute('role','alert');
            if(root.classList.contains('mod-page')){feedback.dataset.forModule=root.id;feedback.hidden=!root.classList.contains('active');}
            feedback.append(document.createTextNode('配置读取失败，暂时不能保存。'));
            const button=document.createElement('button');button.type='button';button.textContent='重试';button.onclick=retry;
            feedback.append(button);root.before(feedback);
            // Keep the unread/default form inert until a successful retry.
        } finally {root.removeAttribute('aria-busy');}
    }
    function closeSidebar(restoreFocus=true) {
        document.querySelector('.sidebar')?.classList.remove('open');
        document.getElementById('sidebarBackdrop')?.classList.remove('show');
        document.getElementById('menuBtn')?.setAttribute('aria-expanded','false');
        if(restoreFocus)menuOpener?.focus();
    }
    function toggleSidebar() {
        const side=document.querySelector('.sidebar');
        if(side.classList.contains('open'))return closeSidebar();
        menuOpener=document.getElementById('menuBtn');
        side.classList.add('open');
        document.getElementById('sidebarBackdrop')?.classList.add('show');
        menuOpener?.setAttribute('aria-expanded','true');
        side.querySelector('a[href],button,[tabindex="0"]')?.focus();
    }
    document.addEventListener('keydown', e => {
        const side=document.querySelector('.sidebar.open');
        if(!side)return;
        if(e.key==='Escape'){e.preventDefault();closeSidebar();}
        if(e.key==='Tab'){
            const focusable=[...side.querySelectorAll('a[href],button,[tabindex="0"]')].filter(el=>!el.disabled&&el.getClientRects().length);
            const first=focusable[0],last=focusable.at(-1);
            if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
            else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
        }
    });
    window.addEventListener('beforeunload', e => {
        if([...drafts.keys()].some(dirty)){e.preventDefault();e.returnValue='';}
    });
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.mod-page').forEach(root=>{
            if(!['pg-overview','pg-utility','pg-leveling','pg-general'].includes(root.id))root.setAttribute('data-draft','');
        });
        document.querySelectorAll('[data-draft]').forEach(register);
        for(const event of ['input','change'])document.addEventListener(event,e=>{
            const root=e.target.closest('[data-draft]'); if(root)refresh(root);
        });
        window.matchMedia('(min-width:861px)').addEventListener('change', e=>{if(e.matches)closeSidebar(false);});
    });
    return {snapshot,clean,changed,dirty,confirmSwitch,saving,loading,toggleSidebar,closeSidebar};
})();
