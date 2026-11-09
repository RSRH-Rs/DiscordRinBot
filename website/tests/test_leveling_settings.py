"""Leveling settings API with a fake Discord and a temporary database."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from quart import Quart
from test_bot_avatar import routes

import i18n

GID = "123"
BOT_ID = "999"
BOT_ROLE = "500"
MANAGE_ROLES = 1 << 28
GOOD = {"enabled": True, "notify_mode": "here", "notify_channel": "0", "rewards": []}
CREATE = ("CREATE TABLE level_config (guild_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 1, "
          "notify_mode TEXT DEFAULT 'here', notify_channel INTEGER DEFAULT 0, rewards TEXT DEFAULT '[]')")


class FakeDiscord:
    def __init__(self):
        self.down = False
        self.roles = [
            {"id": GID, "name": "@everyone", "permissions": "0", "position": 0},
            {"id": BOT_ROLE, "name": "Rin", "permissions": str(MANAGE_ROLES), "position": 5, "managed": True},
            {"id": "1", "name": "low", "permissions": "0", "position": 2},
            {"id": "2", "name": "high", "permissions": "0", "position": 9},
        ]

    async def get(self, path):
        if self.down:
            return None
        if path == "/users/@me":
            return {"id": BOT_ID}
        if path == f"/guilds/{GID}/roles":
            return self.roles
        if path == f"/guilds/{GID}/members/{BOT_ID}":
            return {"user": {"id": BOT_ID}, "roles": [BOT_ROLE]}
        return None


def rewards(*pairs):
    return [{"level": level, "role_id": role} for level, role in pairs]


class LevelingSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(folder.cleanup)
        self.path = str(Path(folder.name) / "leveling.db")
        self.sql(CREATE)
        self.fake = FakeDiscord()
        self.notify = AsyncMock()
        self.validate = AsyncMock(return_value=True)
        self.access = AsyncMock(return_value=True)
        for target, value in (
            ("DB_LEVELING", self.path),
            ("discord_api_get", AsyncMock(side_effect=self.fake.get)),
            ("check_guild_access", self.access),
            ("_notify_bot", self.notify),
            ("_validate_guild_resources", self.validate),
            ("audit", lambda *a, **k: None),
            ("_resolve_actor", AsyncMock(return_value="测试")),
        ):
            stub = patch.object(routes, target, value)
            stub.start()
            self.addCleanup(stub.stop)
        self.app = Quart(__name__)
        self.app.jinja_env.globals.update(tr=i18n.tr, console_strings=i18n.console_strings)
        routes.setup_routes(self.app, SimpleNamespace())
        self.app.before_serving_funcs.clear()
        self.app.after_serving_funcs.clear()
        self.client = self.app.test_client()

    def sql(self, query, *params):
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                return connection.execute(query, params).fetchall()
        finally:
            connection.close()

    def saved(self):
        rows = self.sql("SELECT enabled, notify_mode, notify_channel, rewards FROM level_config WHERE guild_id=123")
        return rows[0] if rows else None

    async def get(self):
        response = await self.client.get(f"/api/guild/{GID}/leveling")
        return response.status_code, await response.get_json()

    async def post(self, body):
        response = await self.client.post(f"/api/guild/{GID}/leveling", json=body)
        return response.status_code, await response.get_json()

    async def test_get_defaults_without_row(self):
        status, body = await self.get()
        self.assertEqual(status, 200)
        self.assertEqual(
            {key: body[key] for key in GOOD},
            {"enabled": True, "notify_mode": "here", "notify_channel": "0", "rewards": []},
        )
        self.assertIsNone(self.saved())

    async def test_get_returns_saved_values_with_string_ids(self):
        stored = json.dumps(rewards((5, "1352551616427069492")))
        self.sql("INSERT INTO level_config VALUES (123, 0, 'channel', 1352551616427069493, ?)", stored)
        _, body = await self.get()
        self.assertFalse(body["enabled"])
        self.assertEqual(body["notify_channel"], "1352551616427069493")
        self.assertEqual(body["rewards"], rewards((5, "1352551616427069492")))

    async def test_get_tolerates_broken_rewards(self):
        self.sql("INSERT INTO level_config VALUES (123, 1, 'here', 0, 'not json')")
        status, body = await self.get()
        self.assertEqual(status, 200)
        self.assertEqual(body["rewards"], [])

    async def test_get_marks_blocked_roles(self):
        _, body = await self.get()
        self.assertEqual(body["blocked_roles"], {BOT_ROLE: "managed", "2": "above"})
        self.assertIs(body["can_manage_roles"], True)

    async def test_get_when_discord_is_down(self):
        self.fake.down = True
        status, body = await self.get()
        self.assertEqual(status, 200)
        self.assertEqual(body["blocked_roles"], {})
        self.assertIsNone(body["can_manage_roles"])

    async def test_requires_access(self):
        self.access.return_value = False
        self.assertEqual((await self.get())[0], 401)
        self.assertEqual((await self.post(GOOD))[0], 401)
        self.assertIsNone(self.saved())

    async def test_post_saves_sorted_and_notifies(self):
        status, body = await self.post({**GOOD, "rewards": rewards((20, "2"), (5, "1"))})
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual(json.loads(self.saved()[3]), rewards((5, "1"), (20, "2")))
        self.notify.assert_awaited_once_with("leveling", 123)

    async def test_post_rejects_bad_body(self):
        cases = {
            "not an object": ["x"],
            "enabled not bool": {**GOOD, "enabled": 1},
            "bad mode": {**GOOD, "notify_mode": "x"},
            "channel missing": {**GOOD, "notify_mode": "channel", "notify_channel": "0"},
            "channel not text": {**GOOD, "notify_mode": "channel", "notify_channel": "abc"},
            "too many": {**GOOD, "rewards": rewards(*[(i, str(i)) for i in range(1, 22)])},
            "level zero": {**GOOD, "rewards": rewards((0, "1"))},
            "level too high": {**GOOD, "rewards": rewards((1000, "1"))},
            "level bool": {**GOOD, "rewards": rewards((True, "1"))},
            "level float": {**GOOD, "rewards": rewards((1.5, "1"))},
            "level string": {**GOOD, "rewards": rewards(("5", "1"))},
            "role zero": {**GOOD, "rewards": rewards((5, "0"))},
            "role letters": {**GOOD, "rewards": rewards((5, "abc"))},
            "role int": {**GOOD, "rewards": rewards((5, 5))},
            "reward not object": {**GOOD, "rewards": [1]},
            "rewards not list": {**GOOD, "rewards": "x"},
            "same level": {**GOOD, "rewards": rewards((5, "1"), (5, "2"))},
            "same role": {**GOOD, "rewards": rewards((5, "1"), (6, "1"))},
        }
        for name, body in cases.items():
            with self.subTest(name):
                status, result = await self.post(body)
                self.assertEqual(status, 400)
                self.assertTrue(result["error"])
                self.assertIsNone(self.saved())
        self.notify.assert_not_awaited()

    async def test_post_accepts_the_limits(self):
        body = {**GOOD, "rewards": rewards(*[(i, str(i)) for i in range(1, 20)], (999, "999"))}
        self.assertEqual((await self.post(body))[0], 200)

    async def test_post_rejects_foreign_role(self):
        self.validate.return_value = False
        status, _ = await self.post({**GOOD, "rewards": rewards((5, "1"))})
        self.assertEqual(status, 400)
        self.assertIsNone(self.saved())

    async def test_post_when_discord_is_down(self):
        self.validate.return_value = None
        status, _ = await self.post({**GOOD, "rewards": rewards((5, "1"))})
        self.assertEqual(status, 502)
        self.assertIsNone(self.saved())
        self.notify.assert_not_awaited()

    async def test_post_allows_role_above_bot(self):
        await self.post({**GOOD, "rewards": rewards((5, "2"))})
        self.assertFalse(self.validate.await_args.kwargs.get("assignable_roles", False))
        self.assertEqual(list(self.validate.await_args.kwargs["role_ids"]), ["2"])

    async def test_post_clears_channel_when_not_channel_mode(self):
        status, _ = await self.post({**GOOD, "notify_mode": "off", "notify_channel": "77"})
        self.assertEqual(status, 200)
        self.assertEqual(self.saved()[2], 0)
        self.assertNotIn("77", [str(value) for value in self.validate.await_args.kwargs["channel_ids"]])

    async def test_post_checks_the_chosen_channel(self):
        await self.post({**GOOD, "notify_mode": "channel", "notify_channel": "77"})
        self.assertEqual(self.saved()[2], 77)
        self.assertEqual([str(value) for value in self.validate.await_args.kwargs["channel_ids"]], ["77"])

    async def test_post_disabled_skips_discord_checks(self):
        status, _ = await self.post({
            "enabled": False, "notify_mode": "channel", "notify_channel": "77",
            "rewards": rewards((5, "404")),
        })
        self.assertEqual(status, 200)
        self.validate.assert_not_awaited()
        self.assertEqual(self.saved()[:3], (0, "channel", 77))
        self.assertEqual(json.loads(self.saved()[3]), rewards((5, "404")))
