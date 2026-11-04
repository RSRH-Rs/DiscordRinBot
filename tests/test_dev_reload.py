import os

from cogs.dev import Dev

COGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rinbot", "cogs")


def test_full_reload_covers_the_same_cogs_main_loads():
    # main.py 加载 cogs/ 下所有不以 _ 开头的 .py；热更新和扩展状态要看同一批
    expected = sorted(
        f"cogs.{f[:-3]}" for f in os.listdir(COGS_DIR) if f.endswith(".py") and not f.startswith("_")
    )
    assert Dev(None)._all_cog_exts() == expected
    assert "cogs.music" in expected and "cogs.dev" in expected


def test_full_reload_skips_helpers_and_root_files():
    exts = Dev(None)._all_cog_exts()
    assert not any(ext.startswith("cogs._") for ext in exts)
    assert "cogs.main" not in exts and "cogs.config" not in exts
