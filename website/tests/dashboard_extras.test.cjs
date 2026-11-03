const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const read=name=>fs.readFileSync(path.join(__dirname,'../static/js/',name),'utf8');

function extras(hash=''){
    const events={},writes=[];
    const ctx=vm.createContext({document:{addEventListener(){}},location:{hash},URL,Event:class{constructor(type,options){this.type=type;Object.assign(this,options);}}});
    ctx.window=ctx;ctx.addEventListener=(name,fn)=>{events[name]=fn;};
    ctx.history=Object.fromEntries(['pushState','replaceState'].map(method=>[method,(_a,_b,url)=>{writes.push([method,url]);ctx.location.hash=url;}]));
    vm.runInContext(read('dashboard-extras.js'),ctx);
    vm.runInContext(read('message-preview.js'),ctx);
    return {ctx,ui:ctx.DashboardExtras,preview:ctx.DashboardPreview,events,writes};
}
test('direct module link survives initialization; unknown hash falls back safely',()=>{
    for(const [hash,expected] of [['#welcome','welcome'],['#unknown','overview'],['#%zz','overview'],['','overview']]){
        const {ui,ctx}=extras(hash),shown=[];
        const router=ui.createHashRouter({ids:['overview','welcome'],fallback:'overview',show:id=>shown.push(id),canLeave:()=>true});
        assert.equal(router.current(),expected);assert.equal(ctx.location.hash,'#'+expected);assert.deepEqual(shown,[expected]);
    }
});
test('internal navigation uses history; cancelled navigation changes neither view nor URL',()=>{
    const {ui,ctx,writes}=extras();let allow=false;
    const router=ui.createHashRouter({ids:['overview','welcome'],fallback:'overview',show(){},canLeave:()=>allow});
    assert.equal(router.navigate('welcome'),false);assert.equal(ctx.location.hash,'#overview');
    allow=true;assert.equal(router.navigate('welcome'),true);
    assert.deepEqual(writes.at(-1),['pushState','#welcome']);
    assert.equal(router.navigate('bad'),false);assert.equal(router.current(),'welcome');
});
test('back/forward/direct hash navigation obeys draft guard and restores URL on cancel',()=>{
    const {ui,ctx,events}=extras('#welcome');let allow=false;
    const router=ui.createHashRouter({ids:['overview','welcome'],fallback:'overview',show(){},canLeave:()=>allow});
    ctx.location.hash='#overview';events.hashchange();
    assert.equal(router.current(),'welcome');assert.equal(ctx.location.hash,'#welcome');
    allow=true;ctx.location.hash='#overview';events.hashchange();assert.equal(router.current(),'overview');
    ctx.location.hash='#welcome';events.hashchange();assert.equal(router.current(),'welcome');
});
const tabsOf=(id,tab)=>['message','card','farewell'].includes(tab)?tab:'message';
test('#welcome/farewell opens the page on that tab',()=>{
    const {ui,ctx}=extras('#welcome/farewell'),shown=[],tabs=[];
    const router=ui.createHashRouter({ids:['overview','welcome'],fallback:'overview',show:id=>shown.push(id),canLeave:()=>true,showTab:(id,tab)=>{tabs.push([id,tab]);return tabsOf(id,tab);}});
    assert.deepEqual(shown,['welcome']);assert.deepEqual(tabs.at(-1),['welcome','farewell']);
    assert.equal(router.currentTab(),'farewell');assert.equal(ctx.location.hash,'#welcome/farewell');
});
test('switching tabs never asks canLeave; leaving the page still does',()=>{
    const {ui,ctx,writes,events}=extras('#welcome');let asked=0;
    const router=ui.createHashRouter({ids:['overview','welcome'],fallback:'overview',show(){},canLeave:()=>{asked++;return false;},showTab:tabsOf});
    assert.equal(ctx.location.hash,'#welcome');
    assert.equal(router.navigate('welcome',{tab:'card'}),true);
    assert.equal(asked,0);assert.deepEqual(writes.at(-1),['pushState','#welcome/card']);
    ctx.location.hash='#welcome/farewell';events.hashchange();
    assert.equal(asked,0);assert.equal(router.currentTab(),'farewell');
    assert.equal(router.navigate('overview'),false);assert.equal(asked,1);
    assert.equal(router.current(),'welcome');assert.equal(ctx.location.hash,'#welcome/farewell');
});
test('unknown tab and unknown page fall back without errors',()=>{
    const bad=extras('#welcome/nope');
    const router=bad.ui.createHashRouter({ids:['overview','welcome'],fallback:'overview',show(){},canLeave:()=>true,showTab:tabsOf});
    assert.equal(router.currentTab(),'message');assert.equal(bad.ctx.location.hash,'#welcome/message');
    const lost=extras('#nope/x');
    const other=lost.ui.createHashRouter({ids:['overview','welcome'],fallback:'overview',show(){},canLeave:()=>true,showTab:()=>null});
    assert.equal(other.current(),'overview');assert.equal(lost.ctx.location.hash,'#overview');
});
test('search is case-insensitive and treats HTML/regex symbols as ordinary text',()=>{
    const {ui}=extras();
    assert.equal(ui.matches('周末一起听歌 123',' 听歌 '),true);
    assert.equal(ui.matches('DJ Music',' dj '),true);
    assert.equal(ui.matches('safe','.*'),false);
    assert.equal(ui.matches('<img>','<img>'),true);
});
test('filtering preserves selected/default options without changing value',()=>{
    const {ui}=extras();
    const select={value:'1',options:[{textContent:'未设置',value:'0'},{textContent:'Welcome',value:'1',selected:true},{textContent:'Logs',value:'2'}]};
    assert.equal(ui.filterOptions(select,'zz'),0);
    assert.equal(select.value,'1');assert.equal(select.options[0].hidden,false);assert.equal(select.options[1].hidden,false);assert.equal(select.options[2].hidden,true);
    assert.equal(ui.filterOptions(select,'LOG'),1);assert.equal(select.options[2].hidden,false);
    ui.filterOptions(select,'');assert.ok(select.options.every(o=>!o.hidden));
});

test('searchable picker matches literal names, excludes disabled choices and does not change selection',()=>{
    const {ui}=extras();
    const select={value:'1',options:[{textContent:'未设置',value:'0'},{textContent:'新朋友',value:'1',selected:true},{textContent:'DJ',value:'2'},{textContent:'DJ locked',value:'3',disabled:true},{textContent:'DJ group',value:'4',parentElement:{disabled:true}}]};
    assert.deepEqual(Array.from(ui.selectMatches(select,'dj'),o=>o.value),['0','2']);
    assert.deepEqual(Array.from(ui.selectMatches(select,'<img>'),o=>o.value),['0']);
    assert.equal(select.value,'1');assert.ok(select.options[1].selected);
});

test('navigation preferences are UI-only and tolerate unavailable storage',()=>{
    const {ui,ctx}=extras();
    assert.equal(ui.preference('menu',true),true);
    ctx.localStorage={getItem(){throw new Error('blocked');}};
    assert.equal(ui.preference('menu',false),false);
    const values=new Map();ctx.localStorage={getItem:key=>values.get(key)??null};
    values.set('rin:ui:v1:nav-welcome','closed');assert.equal(ui.preference('nav-welcome',true),false);
    values.set('rin:ui:v1:nav-music','open');assert.equal(ui.preference('nav-music'),true);
});

test('saving welcome retains optional fields even when their sections are collapsed',async()=>{
    const values={'w-ch':'111','w-fch':'222','w-msg':'欢迎','w-fmsg':'再见','w-title':'标题','w-thumb':'%avatar%','w-image':'https://example.com/a.png'};
    const elements=Object.fromEntries(Object.entries(values).map(([id,value])=>[id,{value}]));
    elements['w-card']={checked:true};elements['w-enabled']={checked:true};
    let module;const requests=[];
    const ctx=vm.createContext({document:{getElementById:id=>elements[id],querySelectorAll:()=>[{value:'333'}],addEventListener(){}},
        Console:{tr:k=>k,module:def=>{module=def;},api:async(...args)=>{requests.push(args);}}});
    ctx.window=ctx;
    vm.runInContext(read('modules/welcome.js'),ctx);
    await module.save();const payload=requests[0][2];
    assert.equal(payload.farewell_channel,'222');assert.equal(payload.thumbnail_url,'%avatar%');assert.equal(payload.image_url,values['w-image']);
    assert.equal(payload.auto_roles,'333');assert.equal(payload.show_card,true);assert.equal(payload.welcome_title,'标题');
    assert.equal(Object.keys(payload).length,10);
});
test('welcome preview follows current and legacy text variables without evaluating markup',()=>{
    const {preview}=extras();
    assert.equal(preview.formatWelcome('%member% / {server}','茶话室'),'@新朋友 / 茶话室');
    assert.equal(preview.formatWelcome('<img src=x>','test'),'<img src=x>');
    assert.match(preview.formatWelcome('','茶话室'),/茶话室/);
});
test('preview image values classify tokens and reject active/non-http URL schemes',()=>{
    const {preview}=extras();
    for(const [value,expected] of [['','none'],['%avatar%','member'],['%server_avatar%','guild'],['https://example.com/a.png','external'],['http://127.0.0.1/a','external'],['javascript:alert(1)','invalid'],['data:image/svg+xml,x','invalid'],['file:///tmp/x','invalid']])assert.equal(preview.imageKind(value),expected);
    assert.equal(preview.imageKind('',true),'member');
    assert.equal(read('message-preview.js').includes('fetch('),false);
});
test('variable insertion preserves surrounding text, caret, max length and input event',()=>{
    const {preview}=extras(),events=[];
    const input={value:'hello old!',selectionStart:6,selectionEnd:9,maxLength:30,focus(){},setSelectionRange(a,b){this.selectionStart=a;this.selectionEnd=b;},dispatchEvent(e){events.push(e.type);}};
    preview.insertToken(input,'%member%');assert.equal(input.value,'hello %member%!');assert.equal(input.selectionStart,14);assert.deepEqual(events,['input']);
    input.maxLength=15;preview.insertToken(input,'too long');assert.equal(input.value,'hello %member%!');
});

test('emoji popup is clamped inside a 320px screen',()=>{
    const picker={hidden:false,style:{},offsetWidth:296,offsetHeight:340};
    const ctx=vm.createContext({document:{getElementById:()=>picker,addEventListener(){}},innerWidth:320,innerHeight:740,Console:{tr:k=>k,module(){}}});ctx.window=ctx;
    vm.runInContext(read('modules/roles.js'),ctx);
    ctx.RolePanel.setTarget({getBoundingClientRect:()=>({left:46,bottom:700})});
    ctx.RolePanel.positionPicker();assert.equal(picker.style.left,'12px');assert.equal(picker.style.top,'388px');
});
