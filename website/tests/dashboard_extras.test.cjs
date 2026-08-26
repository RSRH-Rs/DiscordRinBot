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

function commandsFixture(){
    const elements={'util-commands':{inert:false},'command-search':{value:'play'},'command-filter':{value:'all'}};
    const ctx=vm.createContext({document:{getElementById:id=>elements[id]},DashboardExtras:{matches:(s,q)=>s.toLowerCase().includes(q.toLowerCase())},addEventListener(){},showToast(){}});ctx.window=ctx;
    const source=read('server.js');
    vm.runInContext('let _cmdData=[{name:"play",desc:"music",cog:"Music",enabled:true},{name:"skip",desc:"music",cog:"Music",enabled:true},{name:"help",desc:"help",cog:"System",enabled:true,protected:true}];'+source.slice(source.indexOf('let _cmdSaving=false;'),source.indexOf('function updateSummary() {')),ctx);
    ctx.renderUtility=()=>{elements['util-commands'].inert=false;};
    const state=()=>JSON.parse(vm.runInContext('JSON.stringify(_cmdData)',ctx));
    return {ctx,state,elements};
}
test('failed immediate toggle preserves prior state; retry succeeds',async()=>{
    const {ctx,state}=commandsFixture();ctx.api=async()=>{throw Error('503');};
    await ctx.toggleCommand('play',false);assert.equal(state()[0].enabled,true);
    ctx.api=async()=>({ok:true});await ctx.toggleCommand('play',false);assert.equal(state()[0].enabled,false);
});
test('filtered bulk toggle affects only visible unprotected commands',async()=>{
    const {ctx,state}=commandsFixture(),requests=[];
    ctx.api=async(...args)=>{requests.push(args);return {ok:true};};
    await ctx.toggleCategory('Music',false);
    assert.equal(state()[0].enabled,false);assert.equal(state()[1].enabled,true);assert.equal(state()[2].enabled,true);
    assert.equal(requests.length,1);assert.equal(requests[0][2].name,'play');
    await ctx.toggleCommand('help',false);assert.equal(requests.length,1);
});
test('pending toggle blocks duplicates; application errors do not update local state',async()=>{
    const {ctx,state}=commandsFixture();let finish,calls=0;
    ctx.api=()=>new Promise(resolve=>{calls++;finish=resolve;});
    const first=ctx.toggleCommand('play',false);await ctx.toggleCommand('skip',false);assert.equal(calls,1);
    finish({ok:false,error:'denied'});await first;assert.ok(state().every(c=>c.enabled));
});

test('overview and direct command links share one request and do not replace edited state',async()=>{
    const source=read('server.js');let finish,calls=0;
    const ctx=vm.createContext({api:()=>new Promise(resolve=>{calls++;finish=resolve;})});
    vm.runInContext(source.slice(source.indexOf('let _cmdData = null'),source.indexOf('async function loadOverviewStats()')),ctx);
    const first=ctx.getCommands(),second=ctx.getCommands();assert.equal(calls,1);
    finish([{name:'play',enabled:true}]);const [a,b]=await Promise.all([first,second]);assert.equal(a,b);
    a[0].enabled=false;assert.equal((await ctx.getCommands())[0].enabled,false);assert.equal(calls,1);
});

test('emoji popup is clamped inside a 320px screen',()=>{
    const source=read('server.js'),picker={style:{display:'flex'},offsetWidth:296,offsetHeight:340};
    const ctx=vm.createContext({document:{getElementById:()=>picker},innerWidth:320,innerHeight:740});ctx.window=ctx;
    ctx._epTarget={getBoundingClientRect:()=>({left:46,bottom:700})};
    vm.runInContext(source.slice(source.indexOf('function positionEmojiPicker()'),source.indexOf('function closeEmojiPicker(')),ctx);
    ctx.positionEmojiPicker();assert.equal(picker.style.left,'12px');assert.equal(picker.style.top,'388px');
});
