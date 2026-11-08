// No browser or network access: exercise the settings script with a minimal DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const html = fs.readFileSync(path.join(__dirname, '../templates/settings.html'), 'utf8');
let script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
script = script.slice(0, script.lastIndexOf('\n    loadProfile();'));

function fixture() {
    const nodes = {};
    const fallback = '/static/images/rin/bot-avatar.png';
    nodes['bp-avatar-preview'] = {src:fallback, dataset:{fallback}, getAttribute(key){return this[key];}};
    nodes['bp-avatar-file'] = {files:[], disabled:false, set value(v){if(v==='')this.files=[];}};
    nodes['bp-avatar-state'] = {textContent:''};
    nodes['bp-avatar-reset'] = {hidden:true, disabled:false};
    const readers = [];
    const ctx = vm.createContext({
        document:{getElementById:id=>nodes[id]},
        DashboardUI:{clean(){},changed(){},saving:(_id,action)=>action()},
        Console:{busy:(button,task)=>task(),toast(){}},FileReader:class {readAsDataURL(file){readers.push(()=>{this.result=file.data;this.onload();});}},
        fetch:async()=>({ok:true,json:async()=>({avatar_url:'https://cdn.discordapp.com/current.png'})}),
    });
    ctx.window=ctx;
    vm.runInContext(script, ctx);
    ctx.showToast = () => {};
    return {ctx,nodes,readers,fallback};
}
const validFile = {type:'image/png',size:100,data:'data:image/png;base64,new'};

test('loads current avatar, with a local fallback on read/image failure', async()=>{
    const {ctx,nodes,fallback} = fixture();
    await ctx.loadAvatar();
    assert.equal(nodes['bp-avatar-preview'].src,'https://cdn.discordapp.com/current.png');
    ctx.avatarImageError();
    assert.equal(nodes['bp-avatar-preview'].src,fallback);
    ctx.fetch=async()=>({ok:false});
    await ctx.loadAvatar();
    assert.equal(nodes['bp-avatar-preview'].src,fallback);
    assert.match(nodes['bp-avatar-state'].textContent,/暂时没能读取/);
});
test('late GET cannot overwrite selected file preview; cancel restores current avatar',async()=>{
    const {ctx,nodes,readers}=fixture();
    let resolve;
    ctx.fetch=()=>new Promise(r=>{resolve=r;});
    const loading=ctx.loadAvatar();
    nodes['bp-avatar-file'].files=[validFile];
    ctx.previewAvatar(nodes['bp-avatar-file']); readers.shift()();
    resolve({ok:true,json:async()=>({avatar_url:'https://cdn.discordapp.com/current.png'})});
    await loading;
    assert.equal(nodes['bp-avatar-preview'].src,validFile.data);
    assert.equal(nodes['bp-avatar-reset'].hidden,false);
    ctx.resetAvatarSelection();
    assert.equal(nodes['bp-avatar-file'].files.length,0);
    assert.equal(nodes['bp-avatar-preview'].src,'https://cdn.discordapp.com/current.png');
});
test('cancel invalidates an unfinished file read',()=>{
    const {ctx,nodes,readers,fallback}=fixture();
    nodes['bp-avatar-file'].files=[validFile];
    ctx.previewAvatar(nodes['bp-avatar-file']);
    ctx.resetAvatarSelection(); readers.shift()();
    assert.equal(nodes['bp-avatar-preview'].src,fallback);
});
test('invalid files reset selection without a stale preview',()=>{
    const {ctx,nodes,readers,fallback}=fixture();
    for(const f of [{type:'text/plain',size:1},{type:'image/png',size:6*1024*1024}]){
        nodes['bp-avatar-file'].files=[f]; ctx.previewAvatar(nodes['bp-avatar-file']);
        assert.equal(nodes['bp-avatar-file'].files.length,0);
        assert.equal(nodes['bp-avatar-preview'].src,fallback);
    }
    assert.equal(readers.length,0);
});
test('upload success clears pending selection and defeats a stale GET',async()=>{
    const {ctx,nodes,readers}=fixture();
    let resolve;
    ctx.fetch=()=>new Promise(r=>{resolve=r;});
    const loading=ctx.loadAvatar();
    nodes['bp-avatar-file'].files=[validFile];
    ctx.jpost=async()=>({ok:true,avatar_url:'https://cdn.discordapp.com/new.png'});
    const button={};
    const saving=ctx.saveAvatar(button); readers.shift()(); await saving;
    resolve({ok:true,json:async()=>({avatar_url:'https://cdn.discordapp.com/old.png'})});
    await loading;
    assert.equal(nodes['bp-avatar-preview'].src,'https://cdn.discordapp.com/new.png');
    assert.equal(nodes['bp-avatar-file'].files.length,0);
    assert.equal(button.disabled,false);
});
test('upload failure preserves selection and re-enables controls',async()=>{
    const {ctx,nodes,readers}=fixture();
    nodes['bp-avatar-file'].files=[validFile];
    ctx.jpost=async()=>{throw new Error('rate limited');};
    const button={};
    const saving=ctx.saveAvatar(button); readers.shift()(); await saving;
    assert.equal(nodes['bp-avatar-file'].files.length,1);
    assert.equal(nodes['bp-avatar-file'].disabled,false);
    assert.equal(nodes['bp-avatar-reset'].disabled,false);
    assert.equal(button.disabled,false);
});
