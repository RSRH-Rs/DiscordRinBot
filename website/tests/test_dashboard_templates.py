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
            self.assertIn('dashboard-extras.js?v=20260826b',html)
            self.assertIn('dashboard-ui.js?v=20260826b',html)
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

if __name__=='__main__':unittest.main()
