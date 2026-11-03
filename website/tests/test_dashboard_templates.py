"""Template wiring checks with fake context; no app startup or server writes."""
from html.parser import HTMLParser
from pathlib import Path
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
        self.assertIn('href="/dashboard#not-joined"',html)

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
        self.assertLess(p.ids.index('w-msg'),p.ids.index('welcome-appearance'))
        for name in ['welcome-appearance','welcome-farewell','welcome-autoroles']:
            self.assertIn(f'<details class="fold" id="{name}">',html)
        self.assertIn('最大 5 MB、4096×4096',html)
        self.assertIn('message-preview.js?v=20261103',html)

    def test_overview_lists_every_module_once_with_toggles_for_four(self):
        html,p=self.render('server.html')
        rows=re.findall(r'data-row="([a-z]+)"',html)
        self.assertEqual(sorted(rows),sorted(['welcome','roles','leveling','giveaway','automod','moderation','botlog','serverlog','music','utility','general']))
        self.assertEqual(re.findall(r'data-toggle="([a-z]+)"',html),['welcome','automod','botlog','serverlog'])
        self.assertLess(p.ids.index('ov-headline'),html.count('data-row'))
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
            self.assertIn('js/theme.js?v=20261103a',html)

    def test_login_gate_sits_on_a_blurred_console_backdrop(self):
        html,_=self.render('login_gate.html')
        backdrop=re.search(r'<div class="gate-backdrop" aria-hidden="true">(.*?)</div>\s*<main class="gate',html,re.S)
        self.assertIsNotNone(backdrop)
        for part in ['fake-rail','fake-nav','fake-main']:self.assertIn(part,backdrop.group(1))
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
            used|=set(re.findall(r"tr\('([a-z_][A-Za-z0-9_.]*)'",path.read_text(encoding='utf-8')))
        for path in (ROOT/'static/js').rglob('*.js'):
            used|=set(re.findall(r"tr\('([a-z_][A-Za-z0-9_.]*)'",path.read_text(encoding='utf-8')))
        used={k for k in used if not k.endswith('.')}
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

if __name__=='__main__':unittest.main()
