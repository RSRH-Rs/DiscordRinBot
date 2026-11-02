import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest

# 线上 cogs 目录在 sys.path 上；测试里用桩模块代替 _botlog_helper
if "_botlog_helper" not in sys.modules:
    _stub = ModuleType("_botlog_helper")

    async def _audit(*args, **kwargs):
        pass

    _stub.audit = _audit
    sys.modules["_botlog_helper"] = _stub

from cogs import reactionroles  # noqa: E402


class _Ctx:
    def __init__(self, guild_id):
        self.guild = SimpleNamespace(id=guild_id)
        self.author = SimpleNamespace(mention="@u")
        self.sent = []

    async def defer(self, **kwargs):
        pass

    async def send(self, content=None, **kwargs):
        self.sent.append(content)


@pytest.fixture
async def cog(tmp_path, monkeypatch):
    monkeypatch.setattr(reactionroles, "DB_PATH", str(tmp_path / "rr.db"))

    async def fake_audit(*args, **kwargs):
        pass

    monkeypatch.setattr(reactionroles, "audit", fake_audit)
    c = reactionroles.ReactionRoles(SimpleNamespace())
    await c.cog_load()
    return c


def _insert_panel(msg_id, guild_id, mappings='{"a": 1}'):
    con = sqlite3.connect(reactionroles.DB_PATH)
    con.execute(
        "INSERT INTO rr_panels (message_id, channel_id, guild_id, mappings, exclusive) "
        "VALUES (?, 1, ?, ?, 0)",
        (msg_id, guild_id, mappings),
    )
    con.commit()
    con.close()


async def test_exclusive_cache_miss_reloads_and_keeps_mappings(cog):
    _insert_panel(10, 1)  # 网页刚建的面板，bot 缓存里还没有
    ctx = _Ctx(1)
    await cog.rr_exclusive.callback(cog, ctx, "10", True)
    entry = cog._cache[10]
    assert entry["mappings"] == {"a": 1}  # 不能被伪造成空映射
    assert entry["exclusive"] is True
    assert entry["guild_id"] == 1
    assert "找不到" not in str(ctx.sent)


async def test_exclusive_unknown_panel_creates_no_entry(cog):
    ctx = _Ctx(1)
    await cog.rr_exclusive.callback(cog, ctx, "99", True)
    assert 99 not in cog._cache
    assert ctx.sent == ["❌ 找不到该面板。"]


async def test_exclusive_rejects_other_guilds_panel(cog):
    _insert_panel(10, 2)
    ctx = _Ctx(1)
    await cog.rr_exclusive.callback(cog, ctx, "10", True)
    assert ctx.sent == ["❌ 找不到该面板。"]
    assert 10 not in cog._cache
    con = sqlite3.connect(reactionroles.DB_PATH)
    assert con.execute("SELECT exclusive FROM rr_panels WHERE message_id=10").fetchone() == (0,)
    con.close()
