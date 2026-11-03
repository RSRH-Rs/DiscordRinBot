/* Local illustrative previews: textContent only, no sending or remote image fetch. */
window.DashboardPreview = (() => {
    const el=id=>document.getElementById(id);
    const value=id=>el(id)?.value || '';
    const avatar='/static/images/rin/bot-avatar.png';
    function formatWelcome(text,guild,member='@新朋友'){
        return (text||'欢迎 %member% 加入 %server%！🎉').replaceAll('%member%',member).replaceAll('{member}',member).replaceAll('%server%',guild).replaceAll('{server}',guild);
    }
    function imageKind(text,defaultAvatar=false){
        const input=text.trim()||(defaultAvatar?'%avatar%':'');
        if(!input)return 'none';
        if(input==='%avatar%')return 'member';
        if(['%server_avatar%','%server%'].includes(input))return 'guild';
        try{return ['http:','https:'].includes(new URL(input).protocol)?'external':'invalid';}catch{return 'invalid';}
    }
    function textNode(tag,cls,text){const node=document.createElement(tag);node.className=cls;node.textContent=text;return node;}
    function bubble(content){
        const card=document.createElement('div');card.className='discord-preview';
        const header=document.createElement('div');header.className='preview-author';
        const img=document.createElement('img');img.src=avatar;img.alt='';img.width=28;img.height=28;
        header.append(img,textNode('strong','','小凛 Rin'),textNode('span','preview-bot','APP'));
        card.append(header,content);return card;
    }
    function imagePlaceholder(kind,large=false){
        const box=document.createElement('div');box.className=large?'preview-image-large':'preview-image-thumb';
        if(kind==='member')box.append(textNode('span','','新朋友头像'));
        if(kind==='guild')box.append(textNode('span','','服务器头像'));
        if(kind==='external')box.append(textNode('span','','外链图片（不自动加载）'));
        if(kind==='invalid')box.append(textNode('span','','图片地址格式不对哦'));
        return box;
    }
    function refreshWelcome(){
        const target=el('welcome-preview-content');if(!target)return;
        const guild=document.body?.dataset.guildName||'';
        const embed=document.createElement('div');embed.className='preview-embed';
        embed.append(textNode('strong','preview-title',value('w-title').trim()||'欢迎来到 '+guild));
        embed.append(textNode('p','preview-body',formatWelcome(value('w-msg'),guild)));
        const uploadedWelcome=window.WelcomeImageUploads?.has('welcome');
        const uploadedFarewell=window.WelcomeImageUploads?.has('farewell');
        const thumb=imageKind(value('w-thumb'),true),big=uploadedWelcome?'none':imageKind(value('w-image'));
        if(thumb!=='none')embed.append(imagePlaceholder(thumb));
        if(uploadedWelcome)embed.append(textNode('div','preview-image-large','已上传的迎新图片'));
        if(big!=='none')embed.append(imagePlaceholder(big,true));
        target.replaceChildren();
        if(!el('w-enabled').checked)target.append(textNode('p','preview-notice','欢迎消息未开启。下面先看看文案，不会发送哦。'));
        target.append(bubble(embed));
        if(el('w-card').checked&&!uploadedWelcome)target.append(textNode('p','preview-notice','还会附带自动生成的欢迎横幅，实际图片在成员加入时生成。'));
        const farewell=textNode('p','preview-body','道别：'+formatWelcome(value('w-fmsg'),guild));
        if(value('w-fch')!=='0'){
            target.append(farewell);
            if(uploadedFarewell)target.append(textNode('div','preview-image-large','已上传的道别图片'));
        }
    }
    function refreshRoles(){
        const target=el('roles-preview-content');if(!target)return;
        const embed=document.createElement('div');embed.className='preview-embed preview-embed--roles';
        embed.append(textNode('strong','preview-title',value('rr-title').trim()||'🏷 身份组选择'));
        embed.append(textNode('p','preview-body',value('rr-content').trim()||'点击下方的按钮来领取身份组'));
        if(el('rr-exclusive').checked)embed.append(textNode('p','preview-notice','只能选一个身份组，选择其他会自动替换。'));
        const card=bubble(embed),buttons=document.createElement('div');buttons.className='preview-role-buttons';
        document.querySelectorAll('#rr-roles-list .rr-row').forEach(row=>{
            const select=row.querySelector('.rr-role');if(!select.value||select.value==='0')return;
            const emoji=row.querySelector('.rr-emoji').value;
            const shownEmoji=/^<a?:\w+:\d+>$/.test(emoji)?'自定义表情':emoji;
            buttons.append(textNode('span','preview-role-button',(shownEmoji?shownEmoji+' ':'')+select.selectedOptions[0].textContent.replace(/^@\s*/,'')));
        });
        if(!buttons.children.length)buttons.append(textNode('p','preview-notice','添加身份组后，这里会出现对应的按钮。'));
        card.append(buttons);target.replaceChildren(card);
    }
    function insertToken(input,token){
        const start=input.selectionStart??input.value.length,end=input.selectionEnd??start;
        const next=input.value.slice(0,start)+token+input.value.slice(end);
        if(input.maxLength>0&&next.length>input.maxLength)return;
        input.value=next;input.focus();input.setSelectionRange(start+token.length,start+token.length);
        input.dispatchEvent(new Event('input',{bubbles:true}));
    }
    function tools(input,tokens){
        const bar=document.createElement('div');bar.className='variable-tools';
        tokens.forEach(token=>{
            const button=document.createElement('button');button.type='button';
            button.textContent=({'%member%':'@新成员','%server%':'服务器名','%avatar%':'成员头像','%server_avatar%':'服务器头像'})[token]||token;
            button.title='插入 '+token;
            button.setAttribute('aria-label','插入 '+token);button.onclick=()=>insertToken(input,token);bar.append(button);
        });input.after(bar);
    }
    function sample(kind){
        if(!window.confirm('这会替换当前的标题和正文，其他设置不会改变。要套用示例吗？'))return;
        if(kind==='welcome'){
            el('w-title').value='欢迎来到 '+(document.body?.dataset.guildName||'');
            el('w-msg').value='欢迎 %member% 来到 %server%！\n先坐下来聊聊天吧，大家都在等你哦～';
        }else{
            el('rr-title').value='找到你的同好';el('rr-content').value='喜欢听歌，还是一起打游戏？\n点下面的按钮，选一个属于你的小角落吧。';
        }
        DashboardUI.changed('pg-'+kind);refresh();
    }
    function refresh(){
        refreshWelcome();refreshRoles();
    }
    document.addEventListener('DOMContentLoaded',()=>{
        for(const kind of ['welcome','roles']){
            const root=el('pg-'+kind);if(!root)continue;
            const button=document.createElement('button');button.type='button';button.className='btn btn--text';button.textContent='用小凛的示例';button.onclick=()=>sample(kind);
            root.querySelector('[data-sample-slot]').append(button);
            root.addEventListener('input',refresh);root.addEventListener('change',refresh);
        }
        ['w-msg','w-fmsg'].forEach(id=>tools(el(id),['%member%','%server%']));
        ['w-thumb','w-image'].forEach(id=>tools(el(id),['%avatar%','%server_avatar%']));
        new MutationObserver(refreshRoles).observe(el('rr-roles-list'),{childList:true,subtree:true});
        refresh();
    });
    return {refresh,formatWelcome,imageKind,insertToken};
})();
