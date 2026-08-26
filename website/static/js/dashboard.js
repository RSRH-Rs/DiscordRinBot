document.addEventListener('DOMContentLoaded', () => {
    const search=document.getElementById('server-search');
    if(!search)return;
    const cards=[...document.querySelectorAll('[data-guild-name]')];
    function filter(){
        let count=0;
        cards.forEach(card=>{
            card.hidden=!DashboardExtras.matches(card.dataset.guildName+' '+card.dataset.guildId,search.value);
            if(!card.hidden)count++;
        });
        document.querySelectorAll('[data-server-group]').forEach(group=>{
            const visible=[...group.querySelectorAll('[data-guild-name]')].filter(card=>!card.hidden).length;
            group.hidden=!visible;
            group.querySelector('.section-count').textContent=visible;
        });
        document.getElementById('server-search-result').textContent=`找到 ${count} 个服务器`;
        document.getElementById('server-no-results').hidden=count>0;
    }
    search.addEventListener('input',filter);
    document.getElementById('server-search-clear').addEventListener('click',()=>{search.value='';filter();search.focus();});
    filter();
});
