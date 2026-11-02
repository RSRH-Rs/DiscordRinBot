"""Avatar endpoint regression tests; never read config or contact Discord."""
import base64
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from quart import Quart

WEBSITE = Path(__file__).resolve().parents[1]
config = types.ModuleType("config")
config.BOT_TOKEN = "test-only-not-a-real-token"
config.OWNER_ID = 1
spec = importlib.util.spec_from_file_location("avatar_test_routes", WEBSITE / "routes.py")
routes = importlib.util.module_from_spec(spec)
previous_config = sys.modules.get("config")
sys.modules["config"] = config
try:
    spec.loader.exec_module(routes)
finally:
    if previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = previous_config


class BotAvatarTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Quart(__name__, static_folder=str(WEBSITE / "static"))
        routes.setup_routes(self.app, object())
        # No test lifecycle hook may create real databases or HTTP sessions.
        self.app.before_serving_funcs.clear()
        self.app.after_serving_funcs.clear()
        self.client = self.app.test_client()
        self.owner = patch.object(routes, "is_owner", AsyncMock(return_value=True))
        self.owner.start()
        self.addCleanup(self.owner.stop)
        self.user = {"id": "1352551616427069492", "avatar": "c" * 32}

    async def test_current_avatar_get(self):
        with patch.object(routes, "discord_api_get", AsyncMock(return_value=self.user)) as get:
            response = await self.client.get("/api/bot/avatar")
        self.assertEqual(response.status_code, 200)
        body = await response.get_json()
        self.assertEqual(body["avatar_url"], "https://cdn.discordapp.com/avatars/1352551616427069492/" + "c"*32 + ".png?size=256")
        self.assertFalse(body["is_fallback"])
        get.assert_awaited_once_with("/users/@me")
        self.assertEqual(set(body), {"avatar_url", "is_fallback"})

    async def test_animated_avatar(self):
        user = dict(self.user, avatar="a_" + "d"*32)
        with patch.object(routes, "discord_api_get", AsyncMock(return_value=user)):
            body = await (await self.client.get("/api/bot/avatar")).get_json()
        self.assertTrue(body["avatar_url"].endswith(".gif?size=256"))

    async def test_missing_or_malformed_avatar_uses_local_rin(self):
        for avatar in [None, "", "../../unexpected", 'x" onerror="alert(1)']:
            with self.subTest(avatar=avatar), patch.object(routes, "discord_api_get", AsyncMock(return_value=dict(self.user, avatar=avatar))):
                body = await (await self.client.get("/api/bot/avatar")).get_json()
                self.assertEqual(body, {"avatar_url": "/static/images/rin/bot-avatar.png", "is_fallback": True})

    async def test_discord_unavailable(self):
        with patch.object(routes, "discord_api_get", AsyncMock(return_value=None)):
            response = await self.client.get("/api/bot/avatar")
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", await response.get_json())

    async def test_owner_required_for_read_and_write(self):
        with patch.object(routes, "is_owner", AsyncMock(return_value=False)), patch.object(routes, "discord_api_get", AsyncMock()) as get, patch.object(routes, "discord_api_patch", AsyncMock()) as update:
            self.assertEqual((await self.client.get("/api/bot/avatar")).status_code, 401)
            self.assertEqual((await self.client.post("/api/bot/avatar", json={})).status_code, 401)
            get.assert_not_awaited()
            update.assert_not_awaited()

    async def test_upload_returns_new_avatar(self):
        raw = (WEBSITE / "static/images/rin/bot-avatar.png").read_bytes()
        data = "data:image/png;base64," + base64.b64encode(raw).decode()
        with patch.object(routes, "discord_api_patch", AsyncMock(return_value=(200, self.user))) as update:
            response = await self.client.post("/api/bot/avatar", json={"avatar": data})
        body = await response.get_json()
        self.assertEqual(response.status_code, 200, body)
        self.assertTrue(body["ok"])
        self.assertIn("cdn.discordapp.com/avatars/", body["avatar_url"])
        update.assert_awaited_once_with("/users/@me", {"avatar": data})

    async def test_invalid_upload_never_reaches_discord(self):
        for value in [[], {}, {"avatar": "data:image/png;base64,bad"}]:
            with self.subTest(value=value), patch.object(routes, "discord_api_patch", AsyncMock()) as update:
                self.assertEqual((await self.client.post("/api/bot/avatar", json=value)).status_code, 400)
                update.assert_not_awaited()

    async def test_upload_failure_is_not_reported_as_success(self):
        raw = (WEBSITE / "static/images/rin/bot-avatar.png").read_bytes()
        data = "data:image/png;base64," + base64.b64encode(raw).decode()
        with patch.object(routes, "discord_api_patch", AsyncMock(return_value=(429, {"message": "Try later"}))):
            response = await self.client.post("/api/bot/avatar", json={"avatar": data})
        self.assertEqual(response.status_code, 429, await response.get_json())
        self.assertEqual(await response.get_json(), {"error": "Try later"})


if __name__ == "__main__":
    unittest.main()
