from collections import deque
from types import SimpleNamespace

import aiosqlite
import discord

from command_tree import top_level_app_commands
from cogs import music
from cogs.music import Music

FLAT = {
    "play", "search", "skip", "pause", "resume", "stop", "nowplaying", "queue",
    "remove", "clear", "shuffle", "loop", "volume", "move", "join",
}


def _cog(states=None):
    cog = Music.__new__(Music)
    cog._states = states or {}
    return cog


def test_music_command_names():
    tops = {cmd.name: cmd for cmd in top_level_app_commands(Music)}
    assert set(tops) == FLAT | {"playlist"}
    assert {c.name for c in tops["playlist"].commands} == {"save", "load", "list", "delete"}


def test_loop_choices():
    mode = Music.loop.app_command.parameters[0]
    assert [c.value for c in mode.choices] == ["off", "single", "queue"]
    assert not mode.required


def test_volume_and_queue_ranges():
    level = Music.volume.app_command.parameters[0]
    assert (level.min_value, level.max_value, level.required) == (0, 150, False)
    page = Music.queue.app_command.parameters[0]
    assert page.min_value == 1


async def test_queue_position_autocomplete():
    songs = deque(SimpleNamespace(title=t) for t in ("晴天", "七里香", "稻香"))
    cog = _cog({1: SimpleNamespace(queue=songs)})
    interaction = SimpleNamespace(guild=SimpleNamespace(id=1), locale=discord.Locale.chinese)
    got = await cog._position_autocomplete(interaction, "2")
    assert [(c.name, c.value) for c in got] == [("2. 七里香", 2)]
    assert len(await cog._position_autocomplete(interaction, "")) == 3
    empty = SimpleNamespace(guild=SimpleNamespace(id=2), locale=discord.Locale.chinese)
    assert await cog._position_autocomplete(empty, "") == []


async def test_playlist_autocomplete(tmp_path, monkeypatch):
    path = str(tmp_path / "music.db")
    monkeypatch.setattr(music, "DB_PATH", path)
    async with aiosqlite.connect(path) as db:
        await db.execute("CREATE TABLE saved_queues (guild_id INTEGER, name TEXT, songs_json TEXT, created_at REAL, PRIMARY KEY (guild_id, name))")
        await db.commit()
    cog = _cog()
    interaction = SimpleNamespace(guild=SimpleNamespace(id=1), locale=discord.Locale.chinese)
    assert await cog._playlist_autocomplete(interaction, "") == []
    async with aiosqlite.connect(path) as db:
        await db.execute("INSERT INTO saved_queues VALUES (1, '周杰伦', '[1, 2, 3]', 1.0)")
        await db.execute("INSERT INTO saved_queues VALUES (1, 'default', '[1]', 2.0)")
        await db.commit()
    got = await cog._playlist_autocomplete(interaction, "")
    assert [(c.name, c.value) for c in got] == [("default（1 首）", "default"), ("周杰伦（3 首）", "周杰伦")]
    english = SimpleNamespace(guild=SimpleNamespace(id=1), locale=discord.Locale.american_english)
    assert (await cog._playlist_autocomplete(english, "周"))[0].name == "周杰伦 (3 songs)"
