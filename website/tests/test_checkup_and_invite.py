"""Permission checkup, the invite return and the console's access page; a fake Discord only."""
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from quart import Quart, redirect
from test_bot_avatar import routes

import i18n

GID = "123"
VIEW, SEND, EMBED = 1 << 10, 1 << 11, 1 << 14
BOT_ID = "999"
BOT_ROLE = "500"


class FakeDiscord:
    def __init__(self):
        self.roles = [
            {"id": GID, "name": "@everyone", "permissions": str(VIEW | SEND | EMBED), "position": 0},
            {"id": BOT_ROLE, "name": "Rin", "permissions": "0", "position": 1, "managed": True},
        ]
        self.member = {"user": {"id": BOT_ID}, "roles": [BOT_ROLE]}
        self.gets = []

    async def get(self, path):
        self.gets.append(path)
        if path == "/users/@me":
            return {"id": BOT_ID}
        if path == f"/guilds/{GID}/roles":
            return self.roles
        if path == f"/guilds/{GID}/members/{BOT_ID}":
            return self.member
        return None


class CheckupAndInviteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeDiscord()
        patches = [
            patch.object(routes, "discord_api_get", AsyncMock(side_effect=self.fake.get)),
            patch.object(routes, "check_guild_access", AsyncMock(return_value=True)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        routes._checkup_cache.clear()
        self.addCleanup(routes._checkup_cache.clear)
        test = self

        class Authorized:
            def __await__(self):
                async def state():
                    return test.signed_in
                return state().__await__()

        self.signed_in = True
        self.guilds = [SimpleNamespace(id=123, name="Test", permissions=0x20)]
        discord = SimpleNamespace(
            fetch_user=AsyncMock(return_value=SimpleNamespace(id=42, avatar_url="https://a/u.png")),
            fetch_guilds=AsyncMock(side_effect=lambda: test.guilds),
            authorized=Authorized(),
            create_session=AsyncMock(side_effect=lambda **_: redirect("https://discord.test/oauth")),
            callback=AsyncMock())
        self.app = Quart(__name__, template_folder=str(Path(routes.__file__).parent / "templates"))
        self.app.secret_key = "test"
        self.app.jinja_env.globals.update(tr=i18n.tr, console_strings=i18n.console_strings)
        routes.setup_routes(self.app, discord)
        self.app.before_serving_funcs.clear()
        self.app.after_serving_funcs.clear()
        self.client = self.app.test_client()

    async def checkup(self):
        response = await self.client.get("/api/guild/123/checkup")
        return response.status_code, await response.get_json()

    async def test_checkup_requires_access(self):
        routes.check_guild_access.return_value = False
        self.assertEqual((await self.client.get("/api/guild/123/checkup")).status_code, 401)
        self.assertEqual((await self.client.get("/api/guild/12x/checkup")).status_code, 401)

    async def test_checkup_reports_missing_permissions(self):
        status, body = await self.checkup()
        self.assertEqual(status, 200)
        self.assertTrue(body["available"])
        self.assertEqual(body["blockers"], [])
        self.assertTrue(body["warnings"])
        self.assertEqual({w["code"] for w in body["warnings"]}, {"missing_perm"})

    async def test_checkup_when_discord_is_unavailable(self):
        routes.discord_api_get.side_effect = AsyncMock(return_value=None)
        self.assertEqual(await self.checkup(), (200, {"available": False, "blockers": [], "warnings": []}))

    async def test_checkup_when_rin_has_not_joined(self):
        self.fake.member = None
        _, body = await self.checkup()
        self.assertFalse(body["available"])

    async def test_checkup_cached_for_60_seconds(self):
        await self.checkup()
        await self.checkup()
        self.assertEqual(self.fake.gets.count(f"/guilds/{GID}/roles"), 1)
        routes._checkup_cache.clear()
        await self.checkup()
        self.assertEqual(self.fake.gets.count(f"/guilds/{GID}/roles"), 2)

    async def test_failed_checkup_is_not_cached(self):
        good = routes.discord_api_get.side_effect
        routes.discord_api_get.side_effect = AsyncMock(return_value=None)
        await self.checkup()
        routes.discord_api_get.side_effect = good
        _, body = await self.checkup()
        self.assertTrue(body["available"])

    async def test_server_settings_hides_console_from_non_managers(self):
        self.guilds = [SimpleNamespace(id=123, name="Test", permissions=0)]
        response = await self.client.get("/dashboard/server/123")
        self.assertEqual(response.status_code, 404)
        self.assertIn("找不到该服务器或无权访问", await response.get_data(as_text=True))

    async def test_login_gate_keeps_the_server(self):
        self.signed_in = False
        html = await (await self.client.get("/dashboard/server/123")).get_data(as_text=True)
        self.assertIn('href="/login?guild=123"', html)
        html = await (await self.client.get("/dashboard")).get_data(as_text=True)
        self.assertIn('href="/login"', html)

    async def test_invited_forgets_the_joined_cache(self):
        with patch.object(routes, "_bot_guilds_cache", (time.time(), {1})):
            await self.client.get("/invited?guild_id=5")
            self.assertEqual(routes._bot_guilds_cache[0], 0.0)

    async def test_invited_signed_in_redirects_to_server(self):
        response = await self.client.get("/invited?guild_id=5&code=x")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/dashboard/server/5")

    async def test_invited_signed_out_goes_through_login(self):
        self.signed_in = False
        response = await self.client.get("/invited?guild_id=5&code=x")
        self.assertEqual(response.headers["Location"], "/login?guild=5")

    async def test_invited_rejects_bad_ids(self):
        for bad in ("abc", "//evil.example"):
            response = await self.client.get("/invited", query_string={"guild_id": bad})
            self.assertEqual(response.headers["Location"], "/", bad)

    async def test_invited_cancelled_goes_home(self):
        response = await self.client.get("/invited?guild_id=5&error=access_denied")
        self.assertEqual(response.headers["Location"], "/")

    async def test_login_keeps_guild_after_clearing_session(self):
        async with self.client.session_transaction() as sess:
            sess["stale"] = "old"
        response = await self.client.get("/login?guild=5")
        self.assertEqual(response.status_code, 302)
        async with self.client.session_transaction() as sess:
            self.assertNotIn("stale", sess)
            self.assertEqual(sess["post_login_guild"], "5")

    async def test_callback_uses_and_clears_guild(self):
        async with self.client.session_transaction() as sess:
            sess["post_login_guild"] = "5"
        response = await self.client.get("/callback")
        self.assertEqual(response.headers["Location"], "/dashboard/server/5")
        async with self.client.session_transaction() as sess:
            self.assertNotIn("post_login_guild", sess)

    async def test_callback_ignores_non_numeric_guild(self):
        async with self.client.session_transaction() as sess:
            sess["post_login_guild"] = "../x"
        response = await self.client.get("/callback")
        self.assertEqual(response.headers["Location"], "/dashboard")


if __name__ == "__main__":
    unittest.main()
