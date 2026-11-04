import time
from types import SimpleNamespace

import aiosqlite
import discord

from cogs import giveaway
from cogs.giveaway import Giveaway


def _sub(name):
    return Giveaway.giveaway_group.get_command(name)


def test_start_parameters():
    params = _sub("start").app_command.parameters
    # Discord 要求必填参数排在可选参数前面
    assert [p.name for p in params] == ["duration", "prize", "winners"]
    assert (params[2].min_value, params[2].max_value) == (1, 20)
    assert params[0].autocomplete


def test_end_and_reroll_take_a_giveaway():
    assert [p.name for p in _sub("end").app_command.parameters] == ["giveaway"]
    reroll = _sub("reroll").app_command.parameters
    assert [p.name for p in reroll] == ["giveaway", "count"]
    assert (reroll[1].min_value, reroll[1].max_value) == (1, 20)


def test_list_checks_manage_guild():
    assert any("has_permissions" in c.__qualname__ for c in _sub("list").checks)


async def test_giveaway_autocomplete_splits_running_and_ended(tmp_path, monkeypatch):
    path = str(tmp_path / "gw.db")
    monkeypatch.setattr(giveaway, "DB_PATH", path)
    now = time.time()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, channel_id INTEGER, message_id INTEGER,"
            " host_id INTEGER, prize TEXT, winners_count INTEGER, end_time REAL, ended INTEGER DEFAULT 0, restrict_role INTEGER DEFAULT 0)"
        )
        await db.executemany(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time, ended) VALUES (1, 1, 1, 1, ?, 1, ?, ?)",
            [("Nitro", now + 7200, 0), ("皮肤", now - 60, 1), ("别的服务器", now + 60, 0)],
        )
        await db.execute("UPDATE giveaways SET guild_id = 2 WHERE prize = '别的服务器'")
        await db.commit()
    cog = Giveaway.__new__(Giveaway)
    zh = SimpleNamespace(guild=SimpleNamespace(id=1), locale=discord.Locale.chinese)
    running = await cog._running_autocomplete(zh, "")
    assert [c.value for c in running] == [1] and running[0].name.startswith("Nitro 剩 ")
    ended = await cog._ended_autocomplete(zh, "")
    assert [(c.name, c.value) for c in ended] == [("皮肤 已结束", 2)]
    english = SimpleNamespace(guild=SimpleNamespace(id=1), locale=discord.Locale.american_english)
    assert (await cog._ended_autocomplete(english, ""))[0].name == "皮肤 ended"
