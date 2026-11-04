"""Regression tests for the final review of the command usability work."""
import ast
import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import aiosqlite
import discord
import pytest
from discord.ext import commands
from discord.ext.commands.view import StringView

from _inputs import BadDuration, DurationTooLong, check_prefix_duration
from cogs import commandtoggle, moderation
from cogs.moderation import Moderation
from rincore import legacy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _prefix_ctx(**extra):
    base = dict(interaction=None, guild=SimpleNamespace(id=1), author=SimpleNamespace(id=9), send=None)
    base.update(extra)
    return SimpleNamespace(**base)


def test_check_prefix_duration_flags_mistyped_durations():
    with pytest.raises(BadDuration):
        asyncio.run(check_prefix_duration("ban", "7days 刷屏"))
    with pytest.raises(BadDuration):
        asyncio.run(check_prefix_duration("ban", "1y"))
    with pytest.raises(DurationTooLong):
        asyncio.run(check_prefix_duration("ban", "400d 刷屏"))
    with pytest.raises(DurationTooLong):
        asyncio.run(check_prefix_duration("mute", "29d"))
    for reason in ("刷屏不听劝", "3次刷屏", "9 多次", "未提供原因", ""):
        asyncio.run(check_prefix_duration("ban", reason))


async def test_prefix_ban_with_a_bad_duration_does_nothing():
    cog = Moderation(SimpleNamespace())
    for reason, error in (("7days 刷屏", BadDuration), ("400d 刷屏", DurationTooLong)):
        with pytest.raises(error):
            await Moderation.ban.callback(cog, _prefix_ctx(), SimpleNamespace(id=5), None, None, reason=reason)


async def test_old_tempban_name_requires_a_duration():
    cog = Moderation(SimpleNamespace())
    with pytest.raises(commands.MissingRequiredArgument) as missing:
        await Moderation.ban.callback(cog, _prefix_ctx(rinbot_legacy="tempban"), SimpleNamespace(id=5), None, None, reason="刷屏")
    assert missing.value.param.name == "duration"


async def test_prefix_mute_with_a_too_long_duration_does_nothing():
    cog = Moderation(SimpleNamespace())
    with pytest.raises(DurationTooLong):
        await Moderation.mute.callback(cog, _prefix_ctx(), SimpleNamespace(id=5), None, reason="29d 刷屏")


def test_rewrite_reports_the_old_name():
    assert legacy.rewrite_named("r!tempban @x 1d") == ("r!ban @x 1d", "tempban")
    assert legacy.rewrite_named("r!ban @x") == ("r!ban @x", None)


def test_get_context_remembers_the_old_name():
    with open(os.path.join(ROOT, "rinbot", "rincore", "legacy_context.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_context")
    targets = [ast.unparse(t) for n in ast.walk(method) if isinstance(n, ast.Assign) for t in n.targets]
    assert "ctx.rinbot_legacy" in targets


def _parse_slowmode(text):
    bot = commands.Bot(command_prefix="r!", intents=discord.Intents.none(), help_command=None)
    message = SimpleNamespace(attachments=[], content=text, _state=None, guild=None, author=None, channel=None)
    ctx = commands.Context(prefix="r!", view=StringView(text), bot=bot, message=message, command=Moderation.slowmode)
    asyncio.run(Moderation.slowmode._parse_arguments(ctx))
    return [ctx.args[-1]]


def test_prefix_slowmode_refuses_bad_durations():
    with pytest.raises(DurationTooLong):
        _parse_slowmode("7h")
    with pytest.raises(BadDuration):
        _parse_slowmode("10")
    assert _parse_slowmode("") == [0]
    assert _parse_slowmode("关闭") == [0]
    assert _parse_slowmode("30s") == [30]


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


async def test_case_duration_respects_role_order(tmp_path, monkeypatch):
    from rincore import cases

    path = str(tmp_path / "mod.db")
    monkeypatch.setattr(moderation, "DB_PATH", path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE mod_cases (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, action TEXT, user_id INTEGER,"
            " mod_id INTEGER, reason TEXT, duration TEXT, created_at REAL)"
        )
        await cases.migrate(db)
        await cases.next_case(db, 1, "mute", 5, 9, "原因", "1小时", 1.0)
    senior = SimpleNamespace(
        id=5, top_role=8, timed_out_until=datetime.now(timezone.utc) + timedelta(hours=1), timeout=_Recorder(),
    )
    me = SimpleNamespace(top_role=10, guild_permissions=discord.Permissions.all())
    guild = SimpleNamespace(id=1, owner=object(), me=me, get_member={5: senior}.get, get_channel=lambda c: None)
    author = SimpleNamespace(id=9, top_role=3, mention="<@9>", guild_permissions=discord.Permissions.all())
    ctx = SimpleNamespace(guild=guild, author=author, interaction=None, me=me, send=_Recorder())
    await Moderation.case_duration.callback(Moderation(SimpleNamespace()), ctx, 1, "28d")
    assert senior.timeout.calls == []
    assert ctx.send.calls[0][0][0] == "❌ 你不能对身份组等于或高于你的成员执行此操作。"


async def test_toggle_migration_failure_does_not_stop_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(commandtoggle, "DB_PATH", str(tmp_path / "toggle.db"))

    async def broken(db):
        raise aiosqlite.OperationalError("database is locked")

    monkeypatch.setattr(commandtoggle, "migrate_rows", broken)
    cog = commandtoggle.CommandToggle.__new__(commandtoggle.CommandToggle)
    cog.bot = SimpleNamespace()
    cog._disabled = {}
    await cog.cog_load()


async def test_global_migration_failure_does_not_stop_loading(tmp_path, monkeypatch):
    from cogs import globalsettings

    monkeypatch.setattr(globalsettings, "DB_PATH", str(tmp_path / "global.db"))

    async def broken(db):
        raise aiosqlite.OperationalError("database is locked")

    monkeypatch.setattr(globalsettings, "migrate_global_rows", broken)
    cog = globalsettings.GlobalSettings.__new__(globalsettings.GlobalSettings)
    await cog._ensure_tables()


def test_dashboard_command_list_matches_the_bot():
    from rincore import command_list
    from test_command_map import EXPECTED

    assert {c["name"] for c in command_list.registry()} == EXPECTED
    assert all(c["desc"] for c in command_list.registry())
    assert commandtoggle.PROTECTED_COMMANDS is command_list.PROTECTED_COMMANDS
    with open(os.path.join(ROOT, "website", "routes.py"), encoding="utf-8") as f:
        source = f.read()
    assert "command_list.registry()" in source and "command_list.PROTECTED_COMMANDS" in source
    for old in ('"name": "warns"', '"name": "tempban"', '"togglelist"'):
        assert old not in source
