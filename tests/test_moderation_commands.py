import asyncio
import typing
from types import SimpleNamespace
from typing import Optional

import aiosqlite
import discord
from discord.ext import commands
from discord.ext.commands.view import StringView

from _inputs import BadDuration, Duration, SlashRange
from command_tree import top_level_app_commands
from cogs import moderation
from cogs.moderation import Moderation


def test_moderation_command_names():
    tops = {cmd.name: cmd for cmd in top_level_app_commands(Moderation)}
    assert set(tops) == {"ban", "unban", "kick", "mute", "unmute", "warn", "purge", "slowmode", "lock", "unlock", "warnings", "modlog"}
    assert {c.name for c in tops["warnings"].commands} == {"list", "remove", "clear"}


def test_ban_takes_an_optional_duration():
    params = Moderation.ban.app_command.parameters
    assert [p.name for p in params] == ["member", "duration", "delete_days", "reason"]
    assert not params[1].required
    assert (params[2].type, params[2].min_value, params[2].max_value) == (discord.AppCommandOptionType.integer, 0, 7)
    for name in ("duration", "delete_days"):
        annotation = Moderation.ban.clean_params[name].annotation
        assert type(None) in typing.get_args(annotation)


def test_reason_is_not_eaten_as_duration():
    # 和 /ban 一样的参数形状：前缀里看不懂的时长、天数都跳过，整句留给原因
    @commands.hybrid_command(name="shape")
    async def shape(ctx, duration: Optional[Duration("ban")] = None, delete_days: Optional[SlashRange(0, 7)] = None, *, reason: str = "x"):
        pass

    async def parse(text):
        bot = commands.Bot(command_prefix="r!", intents=discord.Intents.none())
        message = SimpleNamespace(attachments=[], content=text, _state=None, guild=None, author=None, channel=None)
        ctx = commands.Context(prefix="r!", view=StringView(text), bot=bot, message=message, command=shape)
        await shape._parse_arguments(ctx)
        return ctx.args[1:], ctx.kwargs

    assert asyncio.run(parse("刷屏不听劝 下次再犯")) == ([None, None], {"reason": "刷屏不听劝 下次再犯"})
    assert asyncio.run(parse("7d 3 广告")) == ([604800, 3], {"reason": "广告"})
    try:
        asyncio.run(Duration("ban")().convert(None, "刷屏不听劝"))
    except BadDuration:
        pass
    else:
        raise AssertionError("duration should not accept a reason")


def test_mute_and_slowmode_take_durations():
    assert [p.name for p in Moderation.mute.app_command.parameters] == ["member", "duration", "reason"]
    assert not Moderation.mute.app_command.parameters[1].required
    assert Moderation.mute.app_command.parameters[1].autocomplete
    assert Moderation.slowmode.app_command.parameters[0].autocomplete


def test_purge_range():
    amount = Moderation.purge.app_command.parameters[0]
    assert (amount.min_value, amount.max_value) == (1, 500)


class _Guild:
    id = 1

    def __init__(self, users=(), error=None):
        self._users, self._error = users, error

    def bans(self, limit=None):
        async def gen():
            if self._error:
                raise self._error
            for user in self._users:
                yield SimpleNamespace(user=user)

        return gen()

    def get_member(self, user_id):
        return None


class _User:
    def __init__(self, name, user_id):
        self.name, self.id = name, user_id

    def __str__(self):
        return self.name


async def test_unban_autocomplete_without_permission_is_empty():
    cog = Moderation(SimpleNamespace())
    guild = _Guild(error=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "missing"))
    assert await cog._unban_autocomplete(SimpleNamespace(guild=guild), "") == []


async def test_unban_autocomplete_lists_and_filters():
    cog = Moderation(SimpleNamespace())
    guild = _Guild(users=[_User("小明", 11), _User("小红", 12), _User("bob", 13)])
    got = await cog._unban_autocomplete(SimpleNamespace(guild=guild), "小")
    assert [(c.name, c.value) for c in got] == [("小明（11）", "11"), ("小红（12）", "12")]


async def test_warning_autocomplete_newest_first(tmp_path, monkeypatch):
    path = str(tmp_path / "mod.db")
    monkeypatch.setattr(moderation, "DB_PATH", path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, mod_id INTEGER, reason TEXT, created_at REAL)"
        )
        await db.executemany(
            "INSERT INTO warnings (guild_id, user_id, mod_id, reason, created_at) VALUES (1, 7, 9, ?, ?)",
            [(f"原因{i}", float(i)) for i in range(30)],
        )
        await db.commit()
    cog = Moderation(SimpleNamespace())
    got = await cog._warning_autocomplete(SimpleNamespace(guild=_Guild()), "")
    assert len(got) == 25
    assert got[0].value == 30 and got[0].name.startswith("#30 7 原因29")
