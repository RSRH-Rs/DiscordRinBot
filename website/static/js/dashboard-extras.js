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
    // UI-only preferences. Storage may be blocked; that must never block editing.
    function preference(key, fallback=false) {
        try { const saved=localStorage.getItem('rin:ui:v1:'+key);return saved===null?fallback:saved==='open'; }
        catch { return fallback; }
    }
    function rememberDetails(root=document) {
        root.querySelectorAll('details[data-remember]').forEach(details=>{
            if(details.dataset.rememberReady)return;
            details.open=preference(details.dataset.remember,details.open);
            details.dataset.rememberReady='true';
            details.addEventListener('toggle',()=>{
                try {localStorage.setItem('rin:ui:v1:'+details.dataset.remember,details.open?'open':'closed');} catch {}
            });
        });
    }
    function selectMatches(select,query) {
        return [...select.options].filter(option=>!option.disabled&&!option.parentElement?.disabled&&(option.value==='0'||matches(option.textContent,query)));
    }
    let searchId = 0, activeSelect=null;
    const selectControllers=new WeakMap();
    function closeSelects(){activeSelect?.close();}
    function enhanceSelects(root=document) {
        root.querySelectorAll('select[data-search],select.rr-role').forEach(select => {
            if (select.dataset.searchReady) return;
            select.dataset.searchReady = 'true';
            const name = select.dataset.search || '身份组';
            const wrapper = document.createElement('div'); wrapper.className = 'search-select';
            if (select.style.maxWidth && select.style.maxWidth !== 'none') wrapper.style.maxWidth=select.style.maxWidth;
            select.before(wrapper);
            const input = document.createElement('input');
            input.type='search'; input.className='cfg-input select-search'; input.placeholder='输入名称搜索…';
            input.setAttribute('aria-label','搜索'+name); input.setAttribute('data-draft-ignore','');
            if (!select.id) select.id='searchable-select-'+(++searchId);
            if (!select.getAttribute('aria-label')) select.setAttribute('aria-label',name);
            const trigger=document.createElement('button');trigger.type='button';trigger.className='select-trigger cfg-select';
            trigger.id=select.id+'-trigger';trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
            const popup=document.createElement('div');popup.className='select-popup';popup.hidden=true;
            const list=document.createElement('div');list.className='select-options';list.id=select.id+'-options';list.setAttribute('role','listbox');list.setAttribute('aria-label',name);
            input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');
            input.setAttribute('aria-controls',list.id);trigger.setAttribute('aria-controls',list.id);
            const hint = document.createElement('span'); hint.className='search-feedback';hint.setAttribute('role','status');hint.id=select.id+'-search-status';
            input.setAttribute('aria-describedby',hint.id);
            popup.append(input,list,hint);wrapper.append(select,trigger,popup);
            let available=[],cursor=-1;
            const position=()=>{
                if(popup.hidden)return;
                if(!select.isConnected){close();return;}
                const rect=trigger.getBoundingClientRect(),width=Math.min(Math.max(rect.width,220),window.innerWidth-24);
                popup.style.width=width+'px';popup.style.left=Math.max(12,Math.min(rect.left,window.innerWidth-width-12))+'px';
                const height=popup.offsetHeight,bottom=window.innerHeight-rect.bottom-12,top=rect.top-12;
                popup.style.top=Math.max(12,bottom>=height||bottom>=top?Math.min(rect.bottom+5,window.innerHeight-height-12):rect.top-height-5)+'px';
            };
            const highlight=()=>{
                [...list.children].forEach((item,i)=>item.classList.toggle('is-highlighted',i===cursor));
                if(cursor>=0&&list.children[cursor]){
                    input.setAttribute('aria-activedescendant',list.children[cursor].id);
                    list.children[cursor].scrollIntoView({block:'nearest'});
                }else input.removeAttribute('aria-activedescendant');
            };
            const close=(focus=false)=>{
                popup.hidden=true;trigger.setAttribute('aria-expanded','false');input.setAttribute('aria-expanded','false');
                input.removeAttribute('aria-activedescendant');input.value='';
                if(activeSelect?.select===select)activeSelect=null;
                if(focus)trigger.focus({preventScroll:true});
            };
            const choose=option=>{
                if(select.disabled||select.closest('[inert]')||!option||option.disabled)return;
                select.value=option.value;
                select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));
                close(true);
            };
            const render=()=>{
                available=selectMatches(select,input.value);list.replaceChildren();
                available.forEach((option,i)=>{
                    const item=document.createElement('button');item.type='button';item.tabIndex=-1;item.className='select-option';item.id=list.id+'-'+i;
                    item.setAttribute('role','option');item.setAttribute('aria-selected',String(option.selected));item.textContent=option.textContent;
                    item.addEventListener('mousedown',e=>e.preventDefault());item.onclick=()=>choose(option);list.append(item);
                });
                const count=available.filter(option=>option.value!=='0').length;
                hint.textContent=count?`${count} 个可选项`:'没有匹配项，当前选择不变';
                cursor=available.findIndex(option=>option.selected);
                if(cursor<0&&input.value.trim())cursor=available.findIndex(option=>option.value!=='0');
                position();highlight();
            };
            const refresh=()=>{
                const text=select.selectedOptions[0]?.textContent||'请选择';
                trigger.textContent=text;trigger.setAttribute('aria-label',name+'：'+text);trigger.disabled=select.disabled;
                if(select.disabled)close();else if(!popup.hidden)render();
            };
            const open=()=>{
                if(select.disabled||select.closest('[inert]'))return;
                closeSelects();popup.hidden=false;input.value='';activeSelect={select,close,position};
                trigger.setAttribute('aria-expanded','true');input.setAttribute('aria-expanded','true');render();input.focus({preventScroll:true});
            };
            trigger.onclick=()=>popup.hidden?open():close();
            trigger.addEventListener('keydown',e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();open();}});
            input.addEventListener('input',render);
            input.addEventListener('keydown',e=>{
                if(e.isComposing)return;
                if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close(true);}
                else if(e.key==='ArrowDown'||e.key==='ArrowUp'){
                    e.preventDefault();
                    cursor=available.length?(cursor<0?(e.key==='ArrowDown'?0:available.length-1):(cursor+(e.key==='ArrowDown'?1:-1)+available.length)%available.length):-1;
                    highlight();
                }else if(e.key==='Enter'){e.preventDefault();choose(available[cursor]);}
            });
            wrapper.addEventListener('focusout',e=>{if(!wrapper.contains(e.relatedTarget))close();});
            select.addEventListener('change',refresh);
            new MutationObserver(refresh).observe(select,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['disabled','selected','label']});
            document.querySelectorAll(`label[for="${select.id}"]`).forEach(label=>label.addEventListener('click',e=>{e.preventDefault();trigger.focus();}));
            select.hidden=true;select.tabIndex=-1;select.setAttribute('aria-hidden','true');
            selectControllers.set(select,{refresh});refresh();
        });
    }
    function refreshSelects(root=document){root.querySelectorAll('select').forEach(select=>selectControllers.get(select)?.refresh());}
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
        const names={'mu-dj':'DJ 身份组','mu-ch':'音乐通知频道','w-ch':'欢迎频道','w-fch':'道别频道','am-log':'审核日志频道','mod-log':'管理日志频道','rr-ch':'面板发送频道','gw-ch':'抽奖频道','gw-role':'参与身份组','bl-ch':'机器人日志频道','sl-ch':'服务器事件频道'};
        Object.entries(names).forEach(([id,name])=>{const el=document.getElementById(id);if(el)el.dataset.search=name;});
        enhanceSelects(); setupSettings();rememberDetails();
        document.addEventListener('pointerdown',e=>{if(activeSelect&&!e.target.closest('.search-select'))closeSelects();});
        document.addEventListener('scroll',()=>activeSelect?.position(),true);
        window.addEventListener('resize',()=>activeSelect?.position());
        document.addEventListener('keydown',e=>{if(!e.isComposing&&e.key==='Escape'&&activeSelect){e.stopPropagation();activeSelect.close(true);}});
        const topbar=document.querySelector('.topbar');
        if(topbar&&typeof ResizeObserver!=='undefined')new ResizeObserver(()=>{
            document.documentElement.style.setProperty('--dashboard-header-height',topbar.getBoundingClientRect().height+'px');
        }).observe(topbar);
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
    return {matches,filterOptions,selectMatches,preference,rememberDetails,createHashRouter,enhanceSelects,refreshSelects,closeSelects};
})();
