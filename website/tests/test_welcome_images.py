"""Welcome/farewell upload regressions; no real config, Discord, or network access."""
import importlib.util
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
from PIL import Image
from quart import Quart
from werkzeug.datastructures import FileStorage

WEBSITE = Path(__file__).resolve().parents[1]
config = types.ModuleType("config")
config.BOT_TOKEN = "test-only-not-a-real-token"
config.OWNER_ID = 1
spec = importlib.util.spec_from_file_location("welcome_image_test_routes", WEBSITE / "routes.py")
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


def image_bytes(color=(240, 140, 170), size=(64, 32), fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format=fmt)
    return output.getvalue()


class WelcomeImageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "welcome.db"
        self.uploads = root / "uploads"
        self.db_patch = patch.object(routes, "DB_WELCOME", str(self.db))
        self.dir_patch = patch.object(routes, "WELCOME_UPLOAD_DIR", str(self.uploads))
        self.access_patch = patch.object(
            routes, "check_guild_access", AsyncMock(return_value=True)
        )
        self.actor_patch = patch.object(
            routes, "_resolve_actor", AsyncMock(return_value="测试用户")
        )
        self.audit_patch = patch.object(routes, "audit")
        for active_patch in (
            self.db_patch,
            self.dir_patch,
            self.access_patch,
            self.actor_patch,
            self.audit_patch,
        ):
            active_patch.start()
            self.addCleanup(active_patch.stop)
        routes._welcome_upload_locks.clear()
        async with aiosqlite.connect(self.db) as db:
            await db.execute(
                """CREATE TABLE welcome_config (
                guild_id INTEGER PRIMARY KEY,
                welcome_image_file TEXT DEFAULT '',
                farewell_image_file TEXT DEFAULT '')"""
            )
            await db.commit()
        self.app = Quart(__name__)
        routes.setup_routes(self.app, object())
        self.app.before_serving_funcs.clear()
        self.app.after_serving_funcs.clear()
        self.client = self.app.test_client()

    @staticmethod
    def upload(raw, filename="image.png", content_type="image/png"):
        return {
            "image": FileStorage(
                stream=io.BytesIO(raw),
                filename=filename,
                content_type=content_type,
            )
        }

    async def test_upload_get_replace_and_delete(self):
        first = image_bytes()
        response = await self.client.post(
            "/api/guild/123/welcome/image/welcome", files=self.upload(first)
        )
        body = await response.get_json()
        self.assertEqual(response.status_code, 200, body)
        self.assertTrue(body["has_image"])
        self.assertEqual(body["mime"], "image/png")
        saved = list(self.uploads.iterdir())
        self.assertEqual(len(saved), 1)
        self.assertRegex(saved[0].name, r"^123-welcome-[0-9a-f]{16}\.png$")

        fetched = await self.client.get("/api/guild/123/welcome/image/welcome")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(await fetched.get_data(), first)
        self.assertEqual(fetched.headers["Cache-Control"], "private, no-store")

        second = image_bytes(color=(80, 120, 200))
        replaced = await self.client.post(
            "/api/guild/123/welcome/image/welcome", files=self.upload(second)
        )
        self.assertEqual(replaced.status_code, 200, await replaced.get_json())
        self.assertEqual(len(list(self.uploads.iterdir())), 1)
        self.assertEqual(
            await (await self.client.get("/api/guild/123/welcome/image/welcome")).get_data(),
            second,
        )

        deleted = await self.client.delete("/api/guild/123/welcome/image/welcome")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse((await deleted.get_json())["has_image"])
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(
            (await self.client.get("/api/guild/123/welcome/image/welcome")).status_code,
            404,
        )

    async def test_rejects_invalid_mismatched_and_oversized_images(self):
        invalid = await self.client.post(
            "/api/guild/123/welcome/image/farewell",
            files=self.upload(b"not an image"),
        )
        self.assertEqual(invalid.status_code, 400)
        mismatch = await self.client.post(
            "/api/guild/123/welcome/image/farewell",
            files=self.upload(image_bytes(), content_type="image/jpeg"),
        )
        self.assertEqual(mismatch.status_code, 400)
        oversized = await self.client.post(
            "/api/guild/123/welcome/image/farewell",
            files=self.upload(b"x" * (5 * 1024 * 1024 + 1)),
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertFalse(self.uploads.exists())

    async def test_rejects_excessive_dimensions_and_unsafe_paths(self):
        too_wide = image_bytes(size=(4097, 1))
        response = await self.client.post(
            "/api/guild/123/welcome/image/welcome", files=self.upload(too_wide)
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("4096", (await response.get_json())["error"])
        self.assertIsNone(routes._welcome_image_path("../secret.png", 123, "welcome"))
        self.assertIsNone(
            routes._welcome_image_path("999-welcome-0123456789abcdef.png", 123, "welcome")
        )

    async def test_access_is_required_before_reading_or_writing(self):
        with patch.object(
            routes, "check_guild_access", AsyncMock(return_value=False)
        ):
            get_response = await self.client.get(
                "/api/guild/123/welcome/image/welcome"
            )
            post_response = await self.client.post(
                "/api/guild/123/welcome/image/welcome",
                files=self.upload(image_bytes()),
            )
        self.assertEqual(get_response.status_code, 401)
        self.assertEqual(post_response.status_code, 401)
        self.assertFalse(self.uploads.exists())


if __name__ == "__main__":
    unittest.main()
