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


@pytest.fixture
async def cog(tmp_path, monkeypatch):
    monkeypatch.setattr(reactionroles, "DB_PATH", str(tmp_path / "rr.db"))

    async def fake_audit(*args, **kwargs):
        pass

    monkeypatch.setattr(reactionroles, "audit", fake_audit)
    c = reactionroles.ReactionRoles(SimpleNamespace())
    await c.cog_load()
    return c


# ─── 单选面板的反应添加 ───


class _Role:
    def __init__(self, rid):
        self.id = rid


class _Member:
    bot = False

    def __init__(self, role_ids):
        self.roles = [_Role(i) for i in role_ids]
        self.added = []
        self.removed = []

    async def add_roles(self, *rs, reason=None):
        self.added += [r.id for r in rs]

    async def remove_roles(self, *rs, reason=None):
        self.removed += [r.id for r in rs]


class _Partial:
    def __init__(self, calls, forbid=False):
        self.calls = calls
        self.forbid = forbid

    async def remove_reaction(self, emoji, member):
        if self.forbid:
            raise reactionroles.discord.Forbidden(SimpleNamespace(status=403, reason="x"), "x")
        self.calls.append(emoji)


def _reaction_setup(cog, member, *, exclusive=True, forbid=False):
    cog._cache[50] = {
        "mappings": {"A": 1, "B": 2, "C": 3, "D": 2},
        "exclusive": exclusive,
        "guild_id": 1,
    }
    calls = []
    channel = SimpleNamespace(get_partial_message=lambda _id: _Partial(calls, forbid))
    guild = SimpleNamespace(
        get_role=lambda rid: _Role(rid),
        get_member=lambda uid: member,
        get_channel_or_thread=lambda cid: channel,
    )
    cog.bot = SimpleNamespace(get_guild=lambda gid: guild)
    payload = SimpleNamespace(
        message_id=50, guild_id=1, channel_id=5, user_id=9, member=member, emoji="B"
    )
    return payload, calls


async def test_exclusive_reaction_swaps_roles_and_reactions(cog):
    member = _Member([1, 99])
    payload, calls = _reaction_setup(cog, member)
    await cog.on_raw_reaction_add(payload)
    assert member.added == [2]
    assert member.removed == [1]
    # 选 B(role 2)：撤掉 A、C 的反应；D 映射到同一身份组 2，不能撤
    assert sorted(calls) == ["A", "C"]


async def test_exclusive_reaction_already_has_role_adds_nothing(cog):
    member = _Member([2, 3])
    payload, calls = _reaction_setup(cog, member)
    await cog.on_raw_reaction_add(payload)
    assert member.added == []
    assert member.removed == [3]


async def test_exclusive_reaction_tolerates_missing_manage_messages(cog):
    member = _Member([1])
    payload, calls = _reaction_setup(cog, member, forbid=True)
    await cog.on_raw_reaction_add(payload)  # 不抛异常
    assert member.added == [2] and member.removed == [1]


async def test_non_exclusive_reaction_only_adds(cog):
    member = _Member([1])
    payload, calls = _reaction_setup(cog, member, exclusive=False)
    await cog.on_raw_reaction_add(payload)
    assert member.added == [2]
    assert member.removed == [] and calls == []
