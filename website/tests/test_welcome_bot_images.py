"""Bot-side custom welcome image path and attachment safety checks."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

COGS = Path(__file__).resolve().parents[2] / "rinbot" / "cogs"
spec = importlib.util.spec_from_file_location(
    "welcome_bot_image_test", COGS / "welcome.py"
)
welcome = importlib.util.module_from_spec(spec)
import sys

sys.path.insert(0, str(COGS))
try:
    spec.loader.exec_module(welcome)
finally:
    sys.path.remove(str(COGS))


class WelcomeBotImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(welcome, "WELCOME_UPLOAD_DIR", str(self.root))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_accepts_only_the_configured_guild_and_slot(self):
        name = "123-welcome-0123456789abcdef.png"
        path = self.root / name
        path.write_bytes(b"safe image placeholder")
        config = {"guild_id": 123, "welcome_image_file": name}
        self.assertEqual(welcome.Welcome._custom_image_path(config, "welcome"), str(path))
        self.assertIsNone(
            welcome.Welcome._custom_image_path(
                {"guild_id": 999, "welcome_image_file": name}, "welcome"
            )
        )
        self.assertIsNone(
            welcome.Welcome._custom_image_path(
                {"guild_id": 123, "farewell_image_file": name}, "farewell"
            )
        )

    def test_rejects_traversal_missing_and_oversized_files(self):
        self.assertIsNone(
            welcome.Welcome._custom_image_path(
                {"guild_id": 123, "welcome_image_file": "../secret.png"},
                "welcome",
            )
        )
        name = "123-welcome-fedcba9876543210.webp"
        config = {"guild_id": 123, "welcome_image_file": name}
        self.assertIsNone(welcome.Welcome._custom_image_path(config, "welcome"))
        (self.root / name).write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        self.assertIsNone(welcome.Welcome._custom_image_path(config, "welcome"))


if __name__ == "__main__":
    unittest.main()
