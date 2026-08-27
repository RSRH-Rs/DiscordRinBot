"""Template wiring checks with fake context; no app startup or server writes."""
from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit
from jinja2 import Environment, FileSystemLoader

ROOT=Path(__file__).resolve().parents[1]

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.links=[]; self.panels={}; self.current=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href',''))
        if 'data-settings-panel' in a:self.current=a['data-settings-panel'];self.panels[self.current]=[]
        if 'data-draft' in a:self.panels[self.current].append(a['id'])
    def handle_endtag(self, tag):
        if tag=='section':self.current=None

class DashboardTemplateTests(unittest.TestCase):
    def render(self, name):
        env=Environment(loader=FileSystemLoader(ROOT/'templates'),autoescape=True)
        env.globals['url_for']=lambda endpoint,filename:'/static/'+filename
        guild=dict(id='123',name='小凛 <img src=x>',icon_url=None,bot_joined=True)
        html=env.get_template(name).render(guild=guild,guilds=[guild,dict(guild,id='456',bot_joined=False)],user=dict(name='测试',avatar_url='/avatar.png'),is_owner=True)
        parser=Parser();parser.feed(html)
        return html,parser
    def test_settings_groups_preserve_all_independent_drafts(self):
        _,p=self.render('settings.html')
        self.assertEqual(p.panels,{'runtime':[],'profile':['draft-profile','draft-username','draft-avatar'],'admin':['draft-announce','draft-maint','draft-blacklist']})
    def test_no_duplicate_ids_and_versioned_helpers(self):
        for name in ['dashboard.html','settings.html','server.html']:
            html,p=self.render(name)
            self.assertEqual(len(p.ids),len(set(p.ids)),name)
            self.assertIn('dashboard-extras.js?v=20260826c',html)
            self.assertIn('dashboard-ui.js?v=20260826c',html)
            self.assertIn('dashboard-ui.css?v=20260826d',html)
            self.assertNotIn('储存设定',html)
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

    def test_role_editor_follows_message_then_roles_then_destination(self):
        html,p=self.render('server.html')
        self.assertLess(p.ids.index('rr-title'),p.ids.index('rr-content'))
        self.assertLess(p.ids.index('rr-content'),p.ids.index('rr-roles-list'))
        self.assertLess(p.ids.index('rr-roles-list'),p.ids.index('rr-ch'))
        self.assertLess(p.ids.index('rr-ch'),p.ids.index('rr-send'))
        self.assertIn('已发送的面板',html)

    def test_optional_welcome_sections_keep_all_fields_in_the_page(self):
        html,p=self.render('server.html')
        for field in ['w-enabled','w-ch','w-msg','w-title','w-thumb','w-image','w-card','w-fch','w-fmsg','w-roles']:
            self.assertEqual(p.ids.count(field),1)
        self.assertLess(p.ids.index('w-msg'),p.ids.index('welcome-appearance'))
        for name in ['welcome-appearance','welcome-farewell','welcome-autoroles']:
            self.assertIn(f'<details class="cfg-section optional-section" id="{name}">',html)

    def test_overview_shows_server_stats_first_then_common_actions(self):
        html,p=self.render('server.html')
        self.assertLess(p.ids.index('ov-members'),p.ids.index('ov-modules'))
        self.assertLess(p.ids.index('ov-modules'),p.ids.index('ov-more-modules'))
        self.assertLess(p.ids.index('ov-modules'),p.ids.index('setup-checklist'))
        self.assertNotIn('data-remember="server-stats"',html)
        self.assertIn('机器人运行日志',html)
        self.assertIn('服务器事件日志',html)

    def test_homepage_tab_title_stays_short_in_both_languages(self):
        html=(ROOT/'templates/index.html').read_text(encoding='utf-8')
        self.assertIn('<title id="pg-title">小凛Rinbot</title>',html)
        self.assertIn("lang:'English', title:'小凛Rinbot'",html)
        self.assertIn("lang:'中文', title:'小凛Rinbot'",html)
        self.assertIn('document.title=t.title;',html)

if __name__=='__main__':unittest.main()
