"""Read-only status checks using temporary DBs and heartbeat fixtures."""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from quart import Quart
from test_bot_avatar import routes


class DashboardStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.botdir=patch.object(routes,'BOT_DIR',str(self.root))
        self.botdir.start(); self.addCleanup(self.botdir.stop)
        self.app=Quart(__name__)
        routes.setup_routes(self.app,object())
        self.app.before_serving_funcs.clear();self.app.after_serving_funcs.clear()
        self.client=self.app.test_client()

    def heartbeat(self, **changes):
        data=dict(updated_at=time.time(), gateway_connected=True,cogs=['Welcome','Music'],guild_ids=['123'])
        data.update(changes)
        (self.root/'health.json').write_text(json.dumps(data),encoding='utf-8')

    def test_missing_stale_disconnected_and_legacy(self):
        self.assertEqual(routes._runtime_health()['state'],'unknown')
        for data,expected in [({},'online'),({'gateway_connected':False},'offline'),
                              ({'updated_at':time.time()-100},'stale'),({'gateway_connected':None},'unknown'),
                              ({'updated_at':'bad'},'unknown'),({'updated_at':float('nan')},'unknown')]:
            self.heartbeat(**data)
            self.assertEqual(routes._runtime_health()['state'],expected)
        (self.root/'health.json').write_text('[]')
        self.assertEqual(routes._runtime_health()['state'],'unknown')

    async def test_db_existence_is_not_module_load(self):
        (self.root/'automod.db').touch()
        self.heartbeat(cogs=['Music'])
        response=await self.client.get('/api/modules')
        result={m['slug']:m['loaded'] for m in await response.get_json()}
        self.assertFalse(result['automod'])
        self.assertTrue(result['music'])
        self.heartbeat(updated_at=time.time()-100)
        result=await (await self.client.get('/api/modules')).get_json()
        self.assertTrue(all(m['loaded'] is None for m in result))

    async def test_config_states_are_per_guild_and_read_only(self):
        path=self.root/'welcome.db'
        with patch.object(routes,'DB_WELCOME',str(path)):
            self.assertEqual(await routes._guild_module_config('welcome',123),'unconfigured')
            self.assertFalse(path.exists())
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE welcome_config (guild_id INTEGER, enabled INTEGER, welcome_channel INTEGER)')
                db.executemany('INSERT INTO welcome_config VALUES (?,?,?)',[(123,0,777),(456,1,777),(789,1,0)])
            db.close()
            before=path.read_bytes()
            for gid,state in [(123,'disabled'),(456,'enabled'),(789,'unconfigured'),(999,'unconfigured')]:
                self.assertEqual(await routes._guild_module_config('welcome',gid),state)
            self.assertEqual(path.read_bytes(),before)

    async def test_unreadable_schema_is_unknown_not_enabled(self):
        path=self.root/'broken.db';path.write_bytes(b'not a database')
        with patch.object(routes,'DB_AUTOMOD',str(path)):
            self.assertEqual(await routes._guild_module_config('automod',123),'unknown')

    async def test_status_requires_guild_access(self):
        with patch.object(routes,'check_guild_access',AsyncMock(return_value=False)):
            self.assertEqual((await self.client.get('/api/guild/123/modules')).status_code,401)

    def make_db(self, name, ddl, rows):
        path=self.root/name
        with sqlite3.connect(path) as db:
            db.execute(ddl)
            if rows:
                marks=','.join('?'*len(rows[0]))
                db.executemany(f'INSERT INTO {ddl.split()[2]} VALUES ({marks})',rows)
        db.close()
        return str(path)

    async def test_summary_welcome(self):
        path=self.make_db('welcome.db','CREATE TABLE welcome_config (guild_id INTEGER, welcome_channel INTEGER, farewell_channel INTEGER, auto_roles TEXT)',[(123,777,0,'1,2,')])
        with patch.object(routes,'DB_WELCOME',path):
            self.assertEqual(await routes._guild_module_summary('welcome',123),{'welcome_channel':777,'farewell_channel':0,'auto_roles_count':2,'enabled':1})
            self.assertEqual(await routes._guild_module_summary('welcome',999),{'enabled':1})

    async def test_summary_automod_counts_rules(self):
        path=self.make_db('automod.db','CREATE TABLE automod_config (guild_id INTEGER, log_channel INTEGER, anti_spam INTEGER, anti_badword INTEGER, anti_link INTEGER, anti_caps INTEGER, anti_repeat INTEGER)',[(123,5,1,0,1,0,1)])
        with patch.object(routes,'DB_AUTOMOD',path):
            self.assertEqual(await routes._guild_module_summary('automod',123),{'log_channel':5,'rules_on':3,'enabled':1})

    async def test_summary_reports_real_enabled_flag(self):
        path=self.make_db('botlog.db','CREATE TABLE botlog_config (guild_id INTEGER, channel_id INTEGER, enabled INTEGER)',[(123,0,0)])
        with patch.object(routes,'DB_BOTLOG',path):
            self.assertEqual(await routes._guild_module_summary('botlog',123),{'channel_id':0,'enabled':0})

    async def test_summary_counts_panels_and_active_giveaways(self):
        rr=self.make_db('rr.db','CREATE TABLE rr_panels (message_id INTEGER, guild_id INTEGER)',[(1,123),(2,123),(3,456)])
        gw=self.make_db('gw.db','CREATE TABLE giveaways (id INTEGER, guild_id INTEGER, ended INTEGER)',[(1,123,0),(2,123,1)])
        with patch.object(routes,'DB_RR',rr),patch.object(routes,'DB_GIVEAWAY',gw):
            self.assertEqual(await routes._guild_module_summary('roles',123),{'panels':2})
            self.assertEqual(await routes._guild_module_summary('giveaway',123),{'active':1})
            self.assertEqual(await routes._guild_module_summary('roles',999),{'panels':0})

    async def test_summary_missing_db_and_broken_db_are_none(self):
        missing=self.root/'missing.db'
        broken=self.root/'broken.db';broken.write_bytes(b'not a database')
        with patch.object(routes,'DB_MUSIC',str(missing)),patch.object(routes,'DB_BOTLOG',str(broken)):
            self.assertIsNone(await routes._guild_module_summary('music',123))
            self.assertIsNone(await routes._guild_module_summary('botlog',123))
            self.assertIsNone(await routes._guild_module_summary('leveling',123))
        self.assertFalse(missing.exists())

    async def test_modules_endpoint_includes_summary(self):
        with patch.object(routes,'check_guild_access',AsyncMock(return_value=True)),patch.object(routes,'_guild_module_config',AsyncMock(return_value='configured')),patch.object(routes,'_guild_module_summary',AsyncMock(return_value={'x':1})):
            data=await (await self.client.get('/api/guild/123/modules')).get_json()
        self.assertTrue(all(m['summary']=={'x':1} for m in data['modules']))

    def toggle_patches(self, path, access=True):
        notify=AsyncMock()
        stack=[patch.object(routes,'DB_WELCOME',path),patch.object(routes,'check_guild_access',AsyncMock(return_value=access)),
               patch.object(routes,'_notify_bot',notify),patch.object(routes,'audit',lambda *a,**k:None),
               patch.object(routes,'_resolve_actor',AsyncMock(return_value='测试'))]
        for p in stack:p.start();self.addCleanup(p.stop)
        return notify

    async def test_toggle_only_changes_enabled(self):
        path=self.make_db('welcome.db',"CREATE TABLE welcome_config (guild_id INTEGER PRIMARY KEY, welcome_channel INTEGER DEFAULT 0, farewell_channel INTEGER DEFAULT 0, auto_roles TEXT DEFAULT '', welcome_msg TEXT DEFAULT '默认', enabled INTEGER DEFAULT 1)",[(123,777,0,'',  '自定义',1)])
        notify=self.toggle_patches(path)
        response=await self.client.post('/api/guild/123/modules/welcome/enabled',json={'enabled':False})
        self.assertEqual(response.status_code,200)
        self.assertEqual((await response.get_json())['config_state'],'disabled')
        with sqlite3.connect(path) as db:
            row=db.execute('SELECT welcome_msg,welcome_channel,enabled FROM welcome_config WHERE guild_id=123').fetchone()
        db.close()
        self.assertEqual(row,('自定义',777,0))
        notify.assert_awaited_once_with('welcome',123)

    async def test_toggle_creates_row_when_missing(self):
        path=self.make_db('welcome.db',"CREATE TABLE welcome_config (guild_id INTEGER PRIMARY KEY, welcome_channel INTEGER DEFAULT 0, welcome_msg TEXT DEFAULT '默认', enabled INTEGER DEFAULT 0)",[])
        self.toggle_patches(path)
        response=await self.client.post('/api/guild/123/modules/welcome/enabled',json={'enabled':True})
        self.assertEqual(response.status_code,200)
        with sqlite3.connect(path) as db:
            row=db.execute('SELECT welcome_msg,enabled FROM welcome_config WHERE guild_id=123').fetchone()
        db.close()
        self.assertEqual(row,('默认',1))

    async def test_toggle_rejects(self):
        path=self.make_db('welcome.db','CREATE TABLE welcome_config (guild_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 1)',[])
        self.toggle_patches(path,access=False)
        self.assertEqual((await self.client.post('/api/guild/123/modules/welcome/enabled',json={'enabled':True})).status_code,401)
        routes.check_guild_access.return_value=True
        self.assertEqual((await self.client.post('/api/guild/123/modules/music/enabled',json={'enabled':True})).status_code,404)
        for body in ({'enabled':'yes'},[]):
            self.assertEqual((await self.client.post('/api/guild/123/modules/welcome/enabled',json=body)).status_code,400)

    async def test_summary_without_row_reports_bot_default_enabled(self):
        welcome=self.make_db('welcome.db','CREATE TABLE welcome_config (guild_id INTEGER, welcome_channel INTEGER, farewell_channel INTEGER, auto_roles TEXT, enabled INTEGER)',[])
        automod=self.make_db('automod.db','CREATE TABLE automod_config (guild_id INTEGER, enabled INTEGER)',[])
        with patch.object(routes,'DB_WELCOME',welcome),patch.object(routes,'DB_AUTOMOD',automod):
            self.assertEqual(await routes._guild_module_summary('automod',123),{'enabled':0})
            self.assertEqual(await routes._guild_module_summary('welcome',123),{'enabled':1})

    async def test_channels_fetch_failure_is_an_error_not_an_empty_list(self):
        with patch.object(routes,'check_guild_access',AsyncMock(return_value=True)),patch.object(routes,'discord_api_get',AsyncMock(return_value=None)):
            self.assertEqual((await self.client.get('/api/guild/123/channels')).status_code,502)
        data=[{'id':1,'name':'news','type':5},{'id':2,'name':'chat','type':0},{'id':3,'name':'voice','type':2}]
        with patch.object(routes,'check_guild_access',AsyncMock(return_value=True)),patch.object(routes,'discord_api_get',AsyncMock(return_value=data)):
            names=[c['name'] for c in await (await self.client.get('/api/guild/123/channels')).get_json()]
        self.assertEqual(names,['chat','news'])

    async def test_settings_page_survives_guild_list_failure(self):
        class FakeDiscord:
            @property
            async def authorized(self): return True
            async def fetch_user(self): return SimpleNamespace(id=1,name='主人',avatar_url='')
            async def fetch_guilds(self): raise RuntimeError('429')
        app=Quart(__name__);routes.setup_routes(app,FakeDiscord())
        app.before_serving_funcs.clear();app.after_serving_funcs.clear()
        render=AsyncMock(return_value='ok')
        with patch.object(routes,'is_owner',AsyncMock(return_value=True)),patch.object(routes,'render_template',render):
            response=await app.test_client().get('/dashboard/settings')
        self.assertEqual(response.status_code,200)
        self.assertEqual(render.await_args.kwargs['guilds'],[])

    def test_manageable_guilds_filters_and_orders(self):
        guilds=[SimpleNamespace(id='1',permissions=0x20),SimpleNamespace(id='2',owner=True,permissions=0),
                SimpleNamespace(id='3',permissions=0x8),SimpleNamespace(id='4',permissions=0)]
        result=routes.manageable_guilds(guilds,{2})
        self.assertEqual([g.id for g in result],['2','1','3'])
        self.assertEqual([g.bot_joined for g in result],[True,False,False])

    async def test_not_joined_and_no_private_guild_list_leak(self):
        self.heartbeat(guild_ids=['456'])
        with patch.object(routes,'check_guild_access',AsyncMock(return_value=True)),patch.object(routes,'_guild_module_config',AsyncMock(return_value='unconfigured')):
            response=await self.client.get('/api/guild/123/modules')
            data=await response.get_json()
        self.assertEqual(response.status_code,200)
        self.assertEqual(data['bot_state'],'not_joined')
        self.assertNotIn('guild_ids',data)
        self.assertEqual(data['modules'][0]['config_state'],'unconfigured')


if __name__=='__main__':unittest.main()
