"""Read-only status checks using temporary DBs and heartbeat fixtures."""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
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
