"""官网首页（website/templates/index.html）与其贴纸资源的静态检查。"""
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RIN_DIR = ROOT / "website" / "static" / "images" / "rin"

STICKERS = ["welcome", "music", "manage", "confused", "manage-blink", "confused-blink"]


@pytest.mark.parametrize("name", STICKERS)
@pytest.mark.parametrize("width", [480, 960])
def test_rin_assets_exist_and_sized(name, width):
    path = RIN_DIR / f"{name}-{width}.webp"
    assert path.is_file(), path
    with Image.open(path) as im:
        assert im.width == width
        assert im.mode == "RGBA"
    assert path.stat().st_size < 150 * 1024


def test_bot_avatar_small():
    path = RIN_DIR / "bot-avatar-96.webp"
    assert path.is_file()
    with Image.open(path) as im:
        assert im.width == 96
