import asyncio
from types import SimpleNamespace

from cogs.dev import sync_commands

DEV = 9


class FakeTree:
    def __init__(self):
        self.calls = []

    def clear_commands(self, *, guild):
        self.calls.append(("clear", guild.id))

    async def sync(self, *, guild=None):
        gid = guild.id if guild is not None else None
        self.calls.append(("sync", gid))
        return [1, 2, 3] if gid is None else [1, 2]


def _run(scope, guild_id, dev=DEV):
    tree = FakeTree()
    guild = SimpleNamespace(id=guild_id) if guild_id is not None else None
    result = asyncio.run(sync_commands(tree, scope, guild, dev))
    return tree.calls, result


def test_global_syncs_dev_guild_too():
    calls, result = _run("global", 4)
    assert calls == [("sync", None), ("sync", DEV)]
    assert result == "已同步 3 个全局指令，开发服务器 2 个"


def test_guild_in_dev_server_keeps_dev_commands():
    calls, result = _run("guild", DEV)
    assert ("clear", DEV) not in calls
    assert calls == [("sync", None), ("sync", DEV)]
    assert result == "已同步 3 个全局指令，开发服务器 2 个"


def test_guild_elsewhere_clears_that_guild_first():
    calls, result = _run("guild", 4)
    assert calls == [("clear", 4), ("sync", 4), ("sync", None), ("sync", DEV)]
    assert result == "已清理本服务器的旧指令，已同步 3 个全局指令，开发服务器 2 个"


def test_clear_guild_refused_in_dev_server():
    calls, result = _run("clear_guild", DEV)
    assert calls == []
    assert result == "开发服务器的指令不能清掉，改用 global。"


def test_clear_guild_elsewhere():
    calls, result = _run("clear_guild", 4)
    assert calls == [("clear", 4), ("sync", 4)]
    assert result == "已清除本服务器的斜杠指令缓存。"


def test_no_dev_guild():
    calls, result = _run("global", 4, dev=0)
    assert calls == [("sync", None)]
    assert result == "已同步 3 个全局指令"


def test_outside_a_server():
    assert _run("guild", None)[0] == [("sync", None), ("sync", DEV)]
    calls, result = _run("clear_guild", None)
    assert calls == [] and result == "只能在服务器里清除指令缓存。"
