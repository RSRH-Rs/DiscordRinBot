"""Regression tests for the minor issues left after the command usability review."""
import ast
import os
import time
from types import SimpleNamespace

import aiosqlite
import discord
import pytest
from discord import app_commands
from discord.ext import commands

from _inputs import choices
from _messages import Notice
from cogs import moderation
from cogs.commandtoggle import CommandToggle
from cogs.errors import ErrorHandler, notice_for
from cogs.globalsettings import Block
from cogs.moderation import Moderation
from rincore import cases, command_i18n
from rincore.legacy_context import LegacyNamesMixin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def _ctx(**extra):
    base = dict(
        guild=SimpleNamespace(id=5), author=SimpleNamespace(id=1, mention="<@1>"), interaction=None, me=object(),
        send=_Recorder(), channel=SimpleNamespace(permissions_for=lambda m: SimpleNamespace(embed_links=True)),
    )
    base.update(extra)
    return SimpleNamespace(**base)


async def test_case_duration_suggestions_follow_the_case(tmp_path, monkeypatch):
    path = str(tmp_path / "mod.db")
    monkeypatch.setattr(moderation, "DB_PATH", path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE mod_cases (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, action TEXT, user_id INTEGER,"
            " mod_id INTEGER, reason TEXT, duration TEXT, created_at REAL)"
        )
        await cases.migrate(db)
        await cases.next_case(db, 1, "mute", 5, 9, "r", "1小时", time.time())
        await cases.next_case(db, 1, "tempban", 6, 9, "r", "1天", time.time())
    cog = Moderation(SimpleNamespace())

    async def values(case):
        interaction = SimpleNamespace(guild=SimpleNamespace(id=1), locale=discord.Locale.chinese, namespace=SimpleNamespace(case=case))
        return [c.value for c in await cog._case_length_autocomplete(interaction, "")]

    assert await values(2) == ["1d", "7d", "30d"]
    assert await values(1) == ["10m", "1h", "1d", "7d", "28d"]
    assert await values(None) == ["10m", "1h", "1d", "7d", "28d"]


def test_choices_skip_values_discord_would_reject():
    got = choices([("长" * 150, "长" * 150), ("长标题" * 50, "short"), ("ok", "ok")], "")
    assert [c.value for c in got] == ["short", "ok"]
    assert len(got[0].name) == 100


async def test_commands_disable_refuses_subcommand_paths():
    cog = CommandToggle.__new__(CommandToggle)
    cog._disabled = {}
    cog.bot = SimpleNamespace(get_command=lambda name: object())
    ctx = _ctx()
    await CommandToggle.commands_disable.callback(cog, ctx, "/warnings clear")
    card = ctx.send.calls[0][1]["embed"]
    assert (card.title, card.description) == ("只能停用整条指令", "填 warnings 会停用整个 /warnings。")


def test_translation_names_match_the_spec():
    table = command_i18n.load()
    assert table["choices"] == {"off": "关闭", "single": "单曲", "queue": "队列"}
    short = [
        (path, name, entry["name"])
        for path, command in table["commands"].items()
        for name, entry in command.get("params", {}).items()
        if not 2 <= len(entry["name"]) <= 4
    ]
    assert short == []


async def test_blocked_users_get_no_moved_notice():
    for block in (Block("blacklist"), Block("maintenance", "升级中")):
        settings = SimpleNamespace(blocked_reason=lambda user_id, command=None, b=block: b)
        ctx = _ctx(invoked_with="welcome_image", command=None, cog=None, bot=SimpleNamespace(get_cog=lambda name: settings))
        await ErrorHandler(SimpleNamespace()).on_command_error(ctx, commands.CommandNotFound("x"))
        assert ctx.send.calls == []
    open_ctx = _ctx(invoked_with="welcome_image", command=None, cog=None, bot=SimpleNamespace(get_cog=lambda name: SimpleNamespace(blocked_reason=lambda *a: None)))
    await ErrorHandler(SimpleNamespace()).on_command_error(open_ctx, commands.CommandNotFound("x"))
    assert open_ctx.send.calls


class _Bot(LegacyNamesMixin, commands.Bot):
    pass


MEMBER = SimpleNamespace(id=123456789012345678, display_name="小明")


def _message(content, perms):
    channel = SimpleNamespace(type=discord.ChannelType.text, permissions_for=lambda member: perms, id=3)
    guild = SimpleNamespace(id=5, get_member={MEMBER.id: MEMBER}.get, get_member_named=lambda name: None)
    return SimpleNamespace(
        content=content, attachments=[], _state=None, author=SimpleNamespace(id=1, bot=False),
        guild=guild, channel=channel, id=4, mentions=[],
    )


def _bot():
    bot = _Bot(command_prefix="r!", intents=discord.Intents.none(), help_command=None)
    bot._connection.user = SimpleNamespace(id=999)
    bot.add_command(Moderation.warnings_group)
    return bot


async def test_old_prefix_names_obey_permissions():
    bot = _bot()
    ctx = await bot.get_context(_message("r!warns @小明", discord.Permissions.none()))
    assert ctx.command.qualified_name == "warnings" and ctx.rinbot_legacy == "warns"
    with pytest.raises(commands.MissingPermissions):
        await ctx.command.invoke(ctx)


async def test_old_prefix_names_pass_the_disable_hook():
    bot = _bot()
    seen = []

    @bot.before_invoke
    async def hook(ctx):
        seen.append(ctx.command.qualified_name.split()[0])
        raise commands.CheckFailure("disabled here")

    # hybrid 组只在子指令那一层跑检查和 hook（排在参数解析之后），停用检查看的是顶层名
    ctx = await bot.get_context(_message("r!delwarn 12", discord.Permissions.all()))
    assert ctx.rinbot_legacy == "delwarn"
    with pytest.raises(commands.CheckFailure):
        await ctx.command.invoke(ctx)
    assert seen == ["warnings"]


def test_bot_uses_the_legacy_mixin():
    with open(os.path.join(ROOT, "rinbot", "main.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    bot = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HybridBot")
    assert [ast.unparse(b) for b in bot.bases] == ["LegacyNamesMixin", "commands.Bot"]


def test_stale_slash_commands_get_a_short_notice():
    expected = Notice("warning", "这条指令已经更新了", "指令列表正在更新，稍等一会儿再从 / 列表里重新选一次。")
    assert notice_for(app_commands.CommandNotFound("warns", [])) == expected
    assert notice_for(app_commands.CommandSignatureMismatch(Moderation.ban.app_command)) == expected
