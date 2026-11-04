"""Template wiring checks with fake context; no app startup or server writes."""
from html.parser import HTMLParser
from pathlib import Path
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from jinja2 import Environment, FileSystemLoader
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import i18n  # noqa: E402

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.links=[]; self.panels={}; self.current=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href',''))
        if 'data-settings-panel' in a:self.current=a['data-settings-panel'];self.panels[self.current]=[]
        if 'data-draft' in a and self.current:self.panels[self.current].append(a['id'])
    def handle_endtag(self, tag):
        if tag=='section':self.current=None

class DashboardTemplateTests(unittest.TestCase):
    def render(self, name):
        env=Environment(loader=FileSystemLoader(ROOT/'templates'),autoescape=True)
        env.globals.update(url_for=lambda endpoint,filename:'/static/'+filename,tr=i18n.tr,console_strings=i18n.console_strings)
        guild=dict(id='123',name='小凛 <img src=x>',icon_url=None,bot_joined=True)
        html=env.get_template(name).render(guild=guild,guilds=[dict(guild,id='456',bot_joined=False),guild],user=dict(name='测试',avatar_url='/avatar.png'),is_owner=True)
        parser=Parser();parser.feed(html)
        return html,parser
    def test_settings_groups_preserve_all_independent_drafts(self):
        _,p=self.render('settings.html')
        self.assertEqual(p.panels,{'runtime':[],'profile':['draft-profile','draft-username','draft-avatar'],'admin':['draft-announce','draft-maint','draft-blacklist']})
    def test_no_duplicate_ids_and_versioned_helpers(self):
        for name in ['dashboard.html','settings.html','server.html']:
            html,p=self.render(name)
            self.assertEqual(len(p.ids),len(set(p.ids)),name)
            self.assertNotIn('储存设定',html)
        for name in ['dashboard.html','settings.html','server.html']:
            html,p=self.render(name)
            self.assertIn('console.css?v=20261103',html)
            self.assertIn('dashboard-ui.js?v=20261103',html)
            self.assertIn('console-core.js?v=20261103',html)
    def test_invites_do_not_request_administrator_and_match_homepage(self):
        html,p=self.render('dashboard.html')
        invites=[link for link in p.links if link.startswith('https://discord.com/oauth2/authorize')]
        self.assertTrue(invites)
        for link in invites:
            permissions=int(parse_qs(urlsplit(link).query)['permissions'][0])
            self.assertEqual(permissions,1374694796438)
            self.assertEqual(permissions & 8,0)
        self.assertNotIn('即将上线',html)
        self.assertIn('小凛 &lt;img src=x&gt;',html)

    def test_dashboard_lists_joined_first_and_escapes_names(self):
        html,p=self.render('dashboard.html')
        self.assertLess(html.index('data-guild-id="123"'),html.index('data-guild-id="456"'))
        self.assertLess(html.index('id="joined"'),html.index('id="not-joined"'))
        self.assertIn('小凛 &lt;img src=x&gt;',html)
        self.assertNotIn('<img src=x>',html)
        self.assertIn('href="/dashboard"',html[html.index('id="switcher-pop"'):])

    def test_role_editor_follows_message_then_roles_then_destination(self):
        html,p=self.render('server.html')
        self.assertLess(p.ids.index('rr-title'),p.ids.index('rr-content'))
        self.assertLess(p.ids.index('rr-content'),p.ids.index('rr-roles-list'))
        self.assertLess(p.ids.index('rr-roles-list'),p.ids.index('rr-ch'))
        self.assertLess(p.ids.index('rr-ch'),p.ids.index('rr-send'))
        self.assertIn('已发送的面板',html)

    def test_optional_welcome_sections_keep_all_fields_in_the_page(self):
        html,p=self.render('server.html')
        for field in ['w-enabled','w-ch','w-msg','w-title','w-thumb','w-image','w-card','w-fch','w-fmsg','w-roles','w-welcome-file','w-farewell-file','w-welcome-image-preview','w-farewell-image-preview']:
            self.assertEqual(p.ids.count(field),1)
        self.assertLess(p.ids.index('w-msg'),p.ids.index('panel-welcome-appearance'))
        self.assertIn('最大 5 MB、4096×4096',html)
        self.assertIn('message-preview.js?v=20261103',html)

    def test_overview_lists_every_module_once_with_toggles_for_four(self):
        html,p=self.render('server.html')
        rows=re.findall(r'data-row="([a-z]+)"',html)
        self.assertEqual(sorted(rows),sorted(['welcome','roles','leveling','giveaway','automod','moderation','botlog','serverlog','music','utility','general']))
        self.assertEqual(re.findall(r'data-toggle="([a-z]+)"',html),['welcome','automod','botlog','serverlog'])
        self.assertLess(html.index('id="ov-headline"'),html.index('data-row='))
        self.assertIn('机器人运行日志',html)
        self.assertIn('服务器事件日志',html)
        self.assertNotIn('pg-personalizer',html)

    def test_homepage_tab_title_stays_short_in_both_languages(self):
        html=(ROOT/'templates/index.html').read_text(encoding='utf-8')
        self.assertIn('<title>小凛Rinbot</title>',html)
        self.assertEqual(html.count("title: '小凛Rinbot'"),2)
        self.assertIn('document.title = t.title;',html)

    def render_all(self):
        for name in ['dashboard.html','server.html','settings.html','login_gate.html','error.html']:
            yield name,self.render(name)[0]

    def test_only_server_rows_carry_data_guild_name(self):
        # serverSearch() filters every [data-guild-name] element; anything else carrying it gets hidden.
        for name in ['dashboard.html','server.html','settings.html']:
            html,_=self.render(name)
            tags=re.findall(r'<([a-z]+)\b[^>]*\sdata-guild-name=',html)
            self.assertEqual(set(tags)-{'a','div'},set(),name)
            for tag in re.findall(r'<[a-z]+\b[^>]*\sdata-guild-name=[^>]*>',html):self.assertIn('class="server-row',tag,name)
            self.assertNotIn('<body data-guild-name',html,name)

    def test_server_list_and_settings_have_visible_page_heads(self):
        html,_=self.render('dashboard.html')
        self.assertRegex(html,r'<div class="page-head">\s*<div class="page-head-text">\s*<h1>')
        self.assertEqual(len(re.findall(r'class="server-row[ "]',html)),2)
        self.assertNotIn('server-card',html); self.assertNotIn('server-grid',html)
        head=re.search(r'<div class="page-head">(.*?)</div>\s*</div>',html,re.S).group(1)
        self.assertIn('邀请小凛',head)
        html,_=self.render('settings.html')
        self.assertIn('<h1 class="sr-only">全局设置</h1>',html)
        heads=re.findall(r'<div class="page-head"><div class="page-head-text"><h2 id="settings-[a-z]+-title" tabindex="-1">[^<]+</h2><p>[^<]+</p></div></div>',html)
        self.assertEqual(len(heads),3)
        for name in ['dashboard.html','settings.html']:
            html,_=self.render(name)
            self.assertIn('<div class="content content--column">',html,name)
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertIn('max-width: 680px',re.search(r'\.content--column > \*\s*\{([^}]*)\}',css).group(1))

    def test_server_rows_truncate_long_names(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        body=re.search(r'(?:^|\n)\.server-name\s*\{([^}]*)\}',css).group(1)
        for part in ['text-overflow: ellipsis','white-space: nowrap','min-width: 0']:self.assertIn(part,body)
        self.assertNotIn('.server-card',css); self.assertNotIn('.server-grid',css)

    def test_page_heads_wrap_title_and_intro(self):
        for name in ['server.html','settings.html']:
            html,_=self.render(name)
            for head in re.findall(r'<div class="page-head">\s*<[^>]+>',html):
                self.assertIn('class="page-head-text"',head,name)

    def test_topbar_has_a_plain_background_before_color_mix(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        body=re.search(r'\.topbar\s*\{([^}]*)\}',css).group(1)
        self.assertIn('background: var(--bg);',body)
        self.assertLess(body.index('background: var(--bg);'),body.index('color-mix('))

    def test_overview_module_rows(self):
        html,_=self.render('server.html')
        start=html.index('id="pg-overview"');ov=html[start:html.index('</section>',start)]
        self.assertEqual(ov.count('class="mod-row"'),11)
        self.assertEqual(len(re.findall(r'<div class="list">\s*<div class="mod-row"',ov)),3)
        self.assertNotIn('mod-card',ov); self.assertNotIn('mod-grid',ov)
        self.assertEqual(ov.count('class="mod-go"'),11)
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertNotIn('.mod-card',css); self.assertNotIn('.mod-grid',css)
        hero=re.search(r'(?:^|\n)\.hero\s*\{([^}]*)\}',css).group(1)
        for gone in ['border:','background','box-shadow']:self.assertNotIn(gone,hero)
        self.assertEqual(len(re.findall(r'<input type="checkbox" role="switch" data-toggle="[a-z]+" data-draft-ignore disabled',ov)),4)
        for id_ in ['ov-attention','ov-modules','ov-error','ov-retry']:self.assertIn(f'id="{id_}"',ov)
        self.assertIn('aria-busy="true"',ov)

    def test_palette_only_on_server_page(self):
        _,p=self.render('server.html')
        for id_ in ['palette','palette-btn','palette-input','palette-list']:self.assertIn(id_,p.ids)
        for name in ['dashboard.html','settings.html']:
            _,q=self.render(name)
            self.assertNotIn('palette',q.ids,name);self.assertNotIn('palette-btn',q.ids,name)

    def test_tabs_carry_their_label(self):
        html,_=self.render('server.html')
        self.assertIn('data-tab="words" aria-controls="panel-automod-words" data-label="违禁词"',html)

    def test_dashboard_and_settings_menus(self):
        html,_=self.render('dashboard.html')
        menu=html[html.index('id="side-modules"'):html.index('</nav>',html.index('id="side-modules"'))]
        self.assertIn('<a class="nav-item" href="/dashboard" aria-current="page">',menu)
        self.assertIn('所有服务器',menu)
        html,_=self.render('settings.html')
        menu=html[html.index('id="side-modules"'):html.index('</nav>',html.index('id="side-modules"'))]
        self.assertIn('href="/dashboard"',menu)
        for tab in ['profile','runtime','admin']:self.assertIn(f'data-settings-tab="{tab}"',menu)

    def test_module_scripts_find_every_id_they_read(self):
        _,p=self.render('server.html')
        DYNAMIC=set()  # ids the scripts create themselves at runtime
        used=set()
        for path in list((ROOT/'static/js/modules').glob('*.js'))+[ROOT/'static/js/message-preview.js']:
            used|=set(re.findall(r"(?:el|getElementById)\('([a-z][a-z0-9-]*)'\)",path.read_text(encoding='utf-8')))
        self.assertEqual(sorted(used-set(p.ids)-DYNAMIC),[])

    def test_master_switches_live_in_page_heads(self):
        html,_=self.render('server.html')
        for master in ['w-enabled','am-enabled','bl-enabled','sl-enabled']:
            head=re.search(r'<div class="page-head">(?:(?!</section>).)*?id="%s"(?:(?!</section>).)*?</div>\s*<p class="master-hint" data-master-hint="%s" hidden>'%(master,master),html,re.S)
            self.assertIsNotNone(head,master)

    def test_welcome_and_automod_use_tabs(self):
        _,p=self.render('server.html')
        for slug,tabs in [('welcome',['message','appearance','farewell','autoroles']),('automod',['rules','words','links'])]:
            for tab in tabs:
                self.assertIn(f'panel-{slug}-{tab}',p.ids)
                self.assertIn(f'tab-{slug}-{tab}',p.ids)
        html,_=self.render('server.html')
        self.assertEqual(re.findall(r'<details class="fold[^"]*"',html),['<details class="fold sent-panels"'])

    def test_shell_has_switcher_and_no_rail(self):
        for name in ['dashboard.html','server.html','settings.html']:
            html,p=self.render(name)
            for id_ in ['switcher-btn','switcher-pop','switcher-search','switcher-empty']:self.assertIn(id_,p.ids,f'{name} {id_}')
            for gone in ['rail-item','nav-head']:self.assertNotIn(gone,html,f'{name} {gone}')

    def test_switcher_lists_joined_before_invites(self):
        html,p=self.render('server.html')
        pop=html[html.index('id="switcher-pop"'):]
        self.assertLess(pop.index('data-name="小凛 &lt;img src=x&gt;"'),pop.index('guild_id=456'))
        invite=[l for l in p.links if 'guild_id=456' in l]
        self.assertEqual(len(invite),1)
        query=parse_qs(urlsplit(invite[0]).query)
        self.assertEqual(query['permissions'],['1374694796438'])
        self.assertEqual(query['disable_guild_select'],['true'])

    def test_switcher_popover_scrolls_inside_viewport(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        pop=re.search(r'\.switcher-pop\s*\{([^}]*)\}',css).group(1)
        self.assertIn('max-height',pop);self.assertIn('overflow-y: auto',pop)
        self.assertIn('text-overflow: ellipsis',re.search(r'\.switcher-name\s*\{([^}]*)\}',css).group(1))

    def test_pages_carry_group_and_guild_name(self):
        html,_=self.render('server.html')
        sections=re.findall(r'<section class="page[^>]*>',html)
        self.assertEqual(len(sections),12)
        for tag in sections:self.assertIn('data-group=',tag)
        self.assertIn('<body data-current-guild="小凛 &lt;img src=x&gt;"',html)

    def test_every_page_boots_theme_before_styles(self):
        for name,html in self.render_all():
            boot=html.find("localStorage.getItem('rin-theme')")
            self.assertGreater(boot,-1,name)
            self.assertLess(boot,html.index('css/console.css'),name)

    def test_console_pages_have_three_theme_buttons(self):
        for name in ['dashboard.html','server.html','settings.html']:
            html,_=self.render(name)
            for value in ['light','','dark']:
                self.assertEqual(html.count(f'data-theme-set="{value}"'),1,f'{name} {value!r}')
            self.assertIn('js/theme.js?v=20261103c',html)

    def test_login_gate_sits_on_a_blurred_console_backdrop(self):
        html,_=self.render('login_gate.html')
        backdrop=re.search(r'<div class="gate-backdrop" aria-hidden="true">(.*?)</div>\s*<main class="gate',html,re.S)
        self.assertIsNotNone(backdrop)
        for part in ['fake-side','fake-main','fake-hero','fake-card']:self.assertIn(part,backdrop.group(1))
        self.assertEqual(backdrop.group(1).count('class="fake-card"'),6)
        for gone in ['fake-rail','fake-nav']:self.assertNotIn(gone,backdrop.group(1))
        self.assertNotIn('<a ',backdrop.group(1))
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertRegex(css,r'\.gate-backdrop\s*\{[^}]*filter:\s*blur\(')

    def test_no_inline_styles_or_cdn(self):
        for name,html in self.render_all():
            for banned in ['style="','unpkg.com','@latest','Noto+Sans+SC','Nunito','lucide']:
                self.assertNotIn(banned,html,f'{name} contains {banned}')

    def test_every_tr_key_exists(self):
        keys=set(i18n.console_strings())
        used=set()
        for path in (ROOT/'templates').glob('*.html'):
            used|=set(re.findall(r"\btr\('([a-z_][A-Za-z0-9_.]*)'",path.read_text(encoding='utf-8')))
        for path in (ROOT/'static/js').rglob('*.js'):
            used|=set(re.findall(r"\btr\('([a-z_][A-Za-z0-9_.]*)'",path.read_text(encoding='utf-8')))
        used={k for k in used if not k.endswith(('.','_'))}  # prefixes of keys built at runtime
        self.assertEqual(sorted(used-keys),[])

    def test_static_assets_exist_and_versioned(self):
        for name,html in self.render_all():
            for ref in re.findall(r'(?:src|href)="/static/([^"?#]+)(\?[^"]*)?"',html):
                path,query=ref
                self.assertTrue((ROOT/'static'/path).is_file(),f'{name}: missing {path}')
                if path.endswith(('.css','.js')):self.assertIn('v=20261103',query,f'{name}: {path} not versioned')

    def test_legacy_assets_are_gone(self):
        for old in ['css/dashboard.css','css/dashboard-ui.css','css/server.css','css/dashboard-extras.css','js/server.js','js/dashboard.js']:
            self.assertFalse((ROOT/'static'/old).exists(),old)

    def test_icon_sprite_has_every_used_icon(self):
        import re
        sprite=(ROOT/'static/icons.svg').read_text(encoding='utf-8')
        symbols=set(re.findall(r'<symbol id="i-([a-z-]+)"',sprite))
        self.assertGreaterEqual(len(symbols),25)
        used=set()
        for path in list((ROOT/'templates').glob('*.html'))+list((ROOT/'static/js').rglob('*.js')):
            text=path.read_text(encoding='utf-8')
            used|=set(re.findall(r"icon\('([a-z-]+)'",text))|set(re.findall(r'#i-([a-z-]+)',text))
        self.assertEqual(used-symbols,set())

    def test_every_console_page_links_home_from_the_sidebar(self):
        for name in ['dashboard.html','server.html','settings.html']:
            html,_=self.render(name)
            side=html[html.index('id="sideNav"'):html.index('id="switcher"')]
            self.assertRegex(side,r'<a class="brand-row" href="/" aria-label="回到主页"',name)

    def test_no_crumbs_and_titles_live_in_content(self):
        for name in ['dashboard.html','server.html','settings.html']:
            html,_=self.render(name)
            self.assertNotIn('id="crumbs"',html,name)
            topbar=html[html.index('<header class="topbar">'):html.index('</header>')]
            self.assertIn('id="topbar-title"',topbar,name)
            self.assertNotIn('<h1',topbar,name)
        html,_=self.render('server.html')
        content=html[html.index('<div class="content'):]
        self.assertIn('<h1 class="sr-only" id="page-title">',content)
        ov=html[html.index('id="pg-overview"'):html.index('</section>',html.index('id="pg-overview"'))]
        self.assertIn('data-bot-status',ov)

    def test_topbar_only_shows_while_the_sidebar_is_a_drawer(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertRegex(re.search(r'(?:^|\n)\.topbar\s*\{([^}]*)\}',css).group(1),r'display:\s*none')
        narrow=css[css.index('@media (max-width: 859px)'):]
        self.assertRegex(narrow,r'\.topbar\s*\{[^}]*display:\s*flex')

    def test_only_warning_dots_show_in_the_sidebar(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertRegex(css,r'\.nav-dot:not\(\.nav-dot--warn\)\s*\{\s*display:\s*none;?\s*\}')

    def test_pages_share_one_left_edge(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        page=re.search(r'\n\.page\s*\{([^}]*)\}',css).group(1)
        self.assertIn('max-width: 680px',page); self.assertNotIn('auto',page)
        self.assertNotIn('.page--wide',css); self.assertNotIn('.content--page',css)
        self.assertIn('max-width: 1032px',re.search(r'\.page--editor\s*\{([^}]*)\}',css).group(1))
        self.assertIn('padding: 40px 48px',re.search(r'\n\.content\s*\{([^}]*)\}',css).group(1))
        for name in ['dashboard.html','settings.html','server.html']:
            html,_=self.render(name)
            self.assertNotIn('content--page',html,name); self.assertNotIn('page--wide',html,name)

    def test_editor_pages(self):
        html,_=self.render('server.html')
        self.assertEqual(sorted(re.findall(r'<section class="page page--editor" id="pg-([a-z]+)"',html)),['roles','welcome'])
        self.assertEqual(len(re.findall(r'<section class="page[" ]',html)),12)
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertIn('minmax(0, 680px) 320px',re.search(r'\n\.editor\s*\{([^}]*)\}',css).group(1))
        self.assertRegex(css[css.index('@media (max-width: 1199px)'):],r'\.editor\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)')

    def test_sticky_preview_scrolls_inside_itself(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        body=re.search(r'\n\.message-preview\s*\{([^}]*)\}',css).group(1)
        for part in ['position: sticky','top: 24px','max-height: calc(100dvh - 48px)','overflow-y: auto']:self.assertIn(part,body)
        for gone in ['background','border:']:self.assertNotIn(gone,body)

    def test_lists_are_flat(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        lst=re.search(r'\n\.list\s*\{([^}]*)\}',css).group(1)
        for gone in ['background','border-radius','box-shadow']:self.assertNotIn(gone,lst)
        self.assertIn('border-block: 1px solid var(--line)',lst)
        self.assertIn('padding: 12px 0',re.search(r'\n\.row\s*\{([^}]*)\}',css).group(1))
        hint=re.search(r'\n\.master-hint\s*\{([^}]*)\}',css).group(1)
        self.assertNotIn('background',hint); self.assertIn('color: var(--warn)',hint)
        for block in ['.case','.lb-list','.cmd-card','.item','.fold > summary']:
            body=re.search(r'\n'+re.escape(block)+r'\s*\{([^}]*)\}',css).group(1)
            self.assertNotIn('background: var(--panel)',body,block)
            self.assertNotIn('border-radius',body,block)

    def test_fields_use_the_field_colour(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        body=re.search(r'\n\.input, \.select, \.textarea, \.num, \.select-trigger\s*\{([^}]*)\}',css).group(1)
        self.assertIn('background: var(--field)',body)

    def test_phone_hero_puts_the_status_under_the_title(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        narrow=css[css.index('@media (max-width: 859px)'):]
        self.assertRegex(narrow,r'\.hero\s*\{[^}]*grid-template-columns:\s*64px minmax\(0, 1fr\)')
        self.assertRegex(narrow,r'\.hero \.bot-status\s*\{[^}]*grid-column:\s*2')


    def test_tabs_line_up_with_the_title(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertIn('gap: 24px',re.search(r'(?:^|\n)\.tabs\s*\{([^}]*)\}',css).group(1))
        self.assertIn('padding: 8px 0;',re.search(r'(?:^|\n)\.tab\s*\{([^}]*)\}',css).group(1))

    def test_whole_module_row_is_clickable(self):
        # The chevron sits outside the link; a stretched link makes the whole row open the module, and the switch stays on top.
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertIn('position: relative',re.search(r'(?:^|\n)\.mod-row\s*\{([^}]*)\}',css).group(1))
        after=re.search(r'(?:^|\n)\.mod-row-link::after\s*\{([^}]*)\}',css).group(1)
        for part in ['content: ""','position: absolute','inset: 0']:self.assertIn(part,after)
        self.assertRegex(css,r'\.mod-row \.tog\s*\{[^}]*position: relative;[^}]*z-index: 1')

    def test_controls_share_one_height(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertRegex(re.search(r'\n:root\s*\{([^}]*)\}',css).group(1),r'--control-h:\s*40px')
        narrow=css[css.index('@media (max-width: 859px)'):]
        self.assertRegex(narrow,r':root\s*\{[^}]*--control-h:\s*44px')
        fixed=re.search(r'\n\.input, \.select, \.num, \.select-trigger\s*\{([^}]*)\}',css).group(1)
        for part in ['height: var(--control-h)','padding-block: 0']:self.assertIn(part,fixed)
        self.assertIn('min-height: var(--control-h)',re.search(r'\n\.btn\s*\{([^}]*)\}',css).group(1))
        self.assertIn('height: var(--control-h)',re.search(r'\n\.seg\s*\{([^}]*)\}',css).group(1))
        self.assertIn('height: var(--control-h)',re.search(r'\n\.emoji-trigger\s*\{([^}]*)\}',css).group(1))
        self.assertNotRegex(css,r'\.server-row\.is-unjoined \.btn\s*\{[^}]*min-height')

    def test_phone_touch_targets(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8');narrow=css[css.index('@media (max-width: 859px)'):]
        self.assertRegex(css,r'\n\.tog input\s*\{[^}]*inset: -9px 0')
        self.assertRegex(narrow,r'\.tog\s*\{[^}]*width: 48px;[^}]*height: 28px')
        self.assertRegex(narrow,r'\.tog input\s*\{[^}]*inset: -8px 0')
        self.assertRegex(narrow,r'\.tog input:checked \+ \.tog-track::after\s*\{[^}]*translateX\(20px\)')
        for sel in [r'\.nav-item',r'\.btn--icon',r'\.menu-btn',r'\.user-logout']:self.assertRegex(narrow,sel+r'\s*\{[^}]*min-height: 44px')
        self.assertRegex(narrow,r'\.theme-switch button\s*\{[^}]*width: 44px;[^}]*height: 36px')
        self.assertRegex(narrow,r'\.theme-switch button::after\s*\{[^}]*inset: -4px 0')

    def test_number_fields_read_left_with_units_inside(self):
        html,_=self.render('server.html')
        for id_,unit in [('am-si','秒'),('am-st','条'),('am-ct','%'),('am-rt','次'),('mod-mt','次警告'),('mod-kt','次警告'),('mod-bt','次警告')]:
            self.assertRegex(html,rf'<span class="num-field"><input class="num" type="number" inputmode="numeric" id="{id_}"[^>]*aria-describedby="{id_}-unit"[^>]*><span class="num-unit" id="{id_}-unit">{re.escape(unit)}</span></span>')
        self.assertNotIn('class="unit">条 /',html)
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        num=re.search(r'\n\.num\s*\{([^}]*)\}',css).group(1)
        for part in ['width: 120px','text-align: left','appearance: textfield']:self.assertIn(part,num)
        self.assertIn('::-webkit-inner-spin-button',css)
        self.assertIn('width: 120px',re.search(r'\n\.num-field\s*\{([^}]*)\}',css).group(1))
        self.assertIn('pointer-events: none',re.search(r'\n\.num-unit\s*\{([^}]*)\}',css).group(1))

    def test_spam_trigger_reads_seconds_then_messages(self):
        html,_=self.render('server.html')
        self.assertLess(html.index('id="am-si"'),html.index('>内发<'));self.assertLess(html.index('>内发<'),html.index('id="am-st"'))
        self.assertIn('<label class="row-title" for="am-si">触发条件</label>',html)
        self.assertRegex(html,r'id="am-st"[^>]*aria-label="消息条数"')
        zh=json.loads((ROOT/'i18n/zh.json').read_text(encoding='utf-8'))
        for key in ['messages_per','seconds_label']:self.assertNotIn(key,zh['automod'])
        self.assertEqual((zh['automod']['within'],zh['automod']['messages']),('内发','条'))

    def test_segments_are_equal_width(self):
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        seg=re.search(r'\n\.seg\s*\{([^}]*)\}',css).group(1)
        for part in ['display: inline-grid','grid-auto-flow: column','grid-auto-columns: minmax(72px, 1fr)']:self.assertIn(part,seg)
        self.assertNotIn('flex-wrap',seg)
        after=re.search(r'\n\.seg-option::after\s*\{([^}]*)\}',css).group(1)
        for part in ['content: attr(data-label)','height: 0','visibility: hidden','font-weight: 600']:self.assertIn(part,after)
        narrow=css[css.index('@media (max-width: 859px)'):]
        self.assertRegex(narrow,r'\.seg\s*\{[^}]*display: grid;[^}]*width: 100%;[^}]*grid-auto-columns: minmax\(0, 1fr\)')
        # five options on a 320px phone leave 57px each; 4px side padding keeps a 3-character label inside its option
        self.assertRegex(narrow,r'\.seg-option\s*\{[^}]*padding: 0 4px')
        html,_=self.render('server.html')
        found=re.findall(r'class="seg-option" data-end-in="[^"]+" data-label="([^"]+)" aria-pressed="[a-z]+">([^<]+)<',html)
        self.assertEqual(len(found),4)
        for label,text in found:self.assertEqual(label,text)

    def test_sub_settings_are_indented(self):
        html,_=self.render('server.html')
        masters=set(re.findall(r'class="tog tog--head"><input type="checkbox" role="switch" id="([^"]+)"',html))
        rows=re.findall(r'<div class="(row[^"]*)" data-depends-on="([^"]+)"',html)
        self.assertEqual(sorted(d for c,d in rows if 'row--sub' in c.split()),['am-bw','am-caps','am-link','am-repeat','am-spam','am-spam'])
        for cls,dep in rows:self.assertEqual('row--sub' in cls.split(),dep not in masters,(cls,dep))
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertIn('margin-left: 16px',re.search(r'\n\.row--sub\s*\{([^}]*)\}',css).group(1))

    def test_editor_head_sits_in_the_form_column(self):
        html,_=self.render('server.html')
        for slug in ['welcome','roles']:
            start=html.index(f'id="pg-{slug}"');page=html[start:html.index('</section>',start)]
            self.assertRegex(page,r'^[^>]*>\s*<div class="editor">\s*<div class="editor-form">\s*<div class="page-head">',slug)
            if slug=='welcome':self.assertLess(page.index('class="page-head"'),page.index('class="tabs"'))

    def test_master_switch_track_ends_on_the_control_line(self):
        # 开启/已关闭 sits left of the track so the track's right edge meets the row switches' right edge
        css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
        self.assertIn('flex-direction: row-reverse',re.search(r'\n\.tog--head\s*\{([^}]*)\}',css).group(1))

if __name__=='__main__':unittest.main()
