/* Navigation and search only. These controls never save configuration. */
window.DashboardExtras = (() => {
    const normal = value => String(value || '').trim().toLocaleLowerCase();
    const matches = (text, query) => normal(text).includes(normal(query));
    function createHashRouter({ids, fallback, show, canLeave}) {
        let current = null;
        const target = () => ids.includes(location.hash.slice(1)) ? location.hash.slice(1) : fallback;
        const write = (id, replace) => history[replace ? 'replaceState' : 'pushState'](null, '', '#'+id);
        function navigate(id, {fromHistory=false, initial=false}={}) {
            if (!ids.includes(id)) return false;
            if (id === current) return true;
            if (!initial && current && !canLeave(current)) {
                if (fromHistory) write(current, true);
                return false;
            }
            current = id;
            if (!fromHistory || location.hash !== '#'+id) write(id, initial || fromHistory);
            show(id, initial);
            return true;
        }
        window.addEventListener('hashchange', () => {
            const id = target();
            if (id === current && location.hash !== '#'+id) write(id, true);
            else navigate(id, {fromHistory:true});
        });
        navigate(target(), {initial:true});
        return {navigate, current:()=>current};
    }
    // Filtering preserves the current selection and "not set" option.
    function filterOptions(select, query) {
        let count = 0;
        for (const option of select.options) {
            const hit = matches(option.textContent, query);
            if (hit && option.value !== '0') count++;
            option.hidden = !(hit || option.selected || option.value === '0');
        }
        return count;
    }
    let searchId = 0;
    function enhanceSelects(root=document) {
        root.querySelectorAll('select[data-search],select.rr-role').forEach(select => {
            if (select.dataset.searchReady) return;
            select.dataset.searchReady = 'true';
            const name = select.dataset.search || '身份组';
            const wrapper = document.createElement('div'); wrapper.className = 'search-select';
            if (select.style.maxWidth && select.style.maxWidth !== 'none') wrapper.style.maxWidth=select.style.maxWidth;
            select.before(wrapper);
            const input = document.createElement('input');
            input.type='search'; input.className='cfg-input select-search'; input.placeholder='搜索'+name+'…';
            input.setAttribute('aria-label','搜索'+name); input.setAttribute('data-draft-ignore','');
            if (!select.id) select.id='searchable-select-'+(++searchId);
            input.setAttribute('aria-controls',select.id);
            if (!select.getAttribute('aria-label')) select.setAttribute('aria-label',name);
            const hint = document.createElement('span'); hint.className='search-feedback';
            hint.setAttribute('role','status'); hint.id=select.id+'-search-status'; hint.hidden=true;
            input.setAttribute('aria-describedby',hint.id);
            wrapper.append(input,select,hint);
            const apply = () => {
                const count=filterOptions(select,input.value);
                hint.hidden=!input.value.trim();
                hint.textContent=count ? `找到 ${count} 项，当前选择会保留` : '没找到匹配项，当前选择不会改变';
            };
            input.addEventListener('input',apply); select.addEventListener('change',apply);
            new MutationObserver(apply).observe(select,{childList:true,subtree:true});
        });
    }
    function setupSettings() {
        const panels=[...document.querySelectorAll('[data-settings-panel]')];
        if (!panels.length) return;
        const profile=panels.find(p=>p.dataset.settingsPanel==='profile');
        profile.append(document.getElementById('draft-avatar'),document.getElementById('draft-username'),document.getElementById('draft-profile'));
        const links=[...document.querySelectorAll('[data-settings-tab]')];
        const router=createHashRouter({
            ids:panels.map(p=>p.dataset.settingsPanel), fallback:'profile',
            canLeave:id=>DashboardUI.confirmLeave([...document.querySelectorAll(`[data-settings-panel="${id}"] [data-draft]`)]),
            show:(id,initial)=>{
                panels.forEach(panel=>{panel.hidden=panel.dataset.settingsPanel!==id;});
                links.forEach(link=>{
                    const selected=link.dataset.settingsTab===id;
                    link.classList.toggle('active',selected);
                    if(selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
                });
                DashboardUI.closeSidebar(false);
                document.querySelector('.main-content').scrollTo(0,0);
                if(!initial)document.querySelector(`[data-settings-panel="${id}"] h2`)?.focus();
            }
        });
        links.forEach(link=>link.addEventListener('click',e=>{
            if(e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey)return;
            e.preventDefault();router.navigate(link.dataset.settingsTab);
        }));
        const update=()=>links.forEach(link=>{
            const panel=panels.find(p=>p.dataset.settingsPanel===link.dataset.settingsTab);
            link.querySelector('.tab-draft').hidden=![...panel.querySelectorAll('[data-draft]')].some(r=>DashboardUI.dirty(r));
        });
        document.addEventListener('dashboard:drafts-changed',update);
        update();
    }
    document.addEventListener('DOMContentLoaded',()=>{
        const names={'mu-dj':'DJ 身份组','mu-ch':'音乐通知频道','w-ch':'欢迎频道','w-fch':'道别频道','am-log':'审核日志频道','mod-log':'管理日志频道','rr-ch':'面板发送频道','gw-ch':'抽奖频道','gw-role':'参与身份组','bl-ch':'系统日志频道','sl-ch':'审计日志频道'};
        Object.entries(names).forEach(([id,name])=>{const el=document.getElementById(id);if(el)el.dataset.search=name;});
        enhanceSelects(); setupSettings();
        const roles=document.getElementById('w-roles');
        if(roles){
            const input=document.createElement('input');input.type='search';input.className='cfg-input';
            input.placeholder='搜索新成员身份组…';input.setAttribute('aria-label','搜索新成员身份组');input.setAttribute('data-draft-ignore','');
            const result=document.createElement('p');result.className='search-feedback';result.setAttribute('role','status');
            roles.before(input,result);
            const filter=()=>{let count=0;roles.querySelectorAll('.role-opt').forEach(label=>{label.hidden=!matches(label.textContent,input.value);if(!label.hidden)count++;});result.textContent=input.value?'找到 '+count+' 项，已勾选的身份组不会改变':'';};
            input.addEventListener('input',filter);new MutationObserver(filter).observe(roles,{childList:true});
        }
        const dynamic=document.getElementById('rr-roles-list');
        if(dynamic)new MutationObserver(()=>enhanceSelects(dynamic)).observe(dynamic,{childList:true});
    });
    return {matches,filterOptions,createHashRouter,enhanceSelects};
})();
