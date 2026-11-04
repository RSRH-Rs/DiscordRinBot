import ast
import asyncio
import os
from types import SimpleNamespace

import aiosqlite
from discord.ext import commands

from rincore import legacy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_REMOVED = {
    "welcome_message", "welcome_toggle", "welcome_image", "welcome_title", "welcome_icon",
    "welcome_thumbnail", "welcome_card", "welcome_disable",
    "rr_create", "rr_add", "rr_remove", "rr_list", "rr_exclusive", "rr_delete",
    "automod enable", "automod disable", "automod toggle", "automod log", "automod mute_duration", "automod spam_config",
    "serverlog", "modlog_channel", "warn_config",
}


def test_rewrite_renamed_names():
    assert legacy.rewrite("r!warns @小明") == "r!warnings list @小明"
    assert legacy.rewrite("r!tempban @x 1d 刷屏") == "r!ban @x 1d 刷屏"
    assert legacy.rewrite("r!automod_words add 坏词") == "r!automod words add 坏词"
    assert legacy.rewrite("r!toggle play") == "r!commands toggle play"
    assert legacy.rewrite("r!delq 存档") == "r!playlist delete 存档"
    assert legacy.rewrite("r!togglelist") == "r!commands list"


def test_rewrite_edges():
    for text in ("r!warnsx", "hello r!warns", "r!", "r!play song", "", "R!WARNS", "r!WARNS", "r!warnings list"):
        assert legacy.rewrite(text) == text


def test_rewrite_keeps_line_breaks_in_arguments():
    assert legacy.rewrite("r!warns @a\nmore") == "r!warnings list @a\nmore"


def test_every_removed_name_has_a_page():
    assert SPEC_REMOVED <= set(legacy.REMOVED)
    assert set(legacy.REMOVED) - SPEC_REMOVED == {"slog", "welcome_thumb"}
    pages = {"welcome": "欢迎新成员", "roles": "领取身份组", "automod": "自动审核", "serverlog": "服务器事件日志", "moderation": "管理模块"}
    for slug, name in legacy.REMOVED.values():
        assert pages[slug] == name


def test_dashboard_url():
    assert legacy.dashboard_url(5, "welcome") == "https://rin-bot.com/dashboard/server/5#welcome"


def test_migrate_disabled():
    assert legacy.migrate_disabled({"warns", "clearwarns", "play"}) == {"warnings", "play"}
    assert legacy.migrate_disabled({"tempban", "welcome_image", "rr_add", "serverlog"}) == set()
    assert legacy.migrate_disabled({"togglelist"}) == {"commands"}
    once = legacy.migrate_disabled({"saveq", "modlog", "kick"})
    assert once == {"playlist", "case", "kick"}
    assert legacy.migrate_disabled(once) == once


def test_get_context_rewrites_a_copy():
    with open(os.path.join(ROOT, "rinbot", "main.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    bot = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HybridBot")
    method = next(n for n in bot.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_context")
    calls = {ast.unparse(n.func) for n in ast.walk(method) if isinstance(n, ast.Call)}
    assert {"copy.copy", "legacy.rewrite_named"} <= calls


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def _ctx(invoked_with, guild=True):
    perms = SimpleNamespace(embed_links=True)
    return SimpleNamespace(
        command=None, cog=None, invoked_with=invoked_with, interaction=None, me=object(),
        guild=SimpleNamespace(id=5) if guild else None,
        channel=SimpleNamespace(permissions_for=lambda m: perms), send=_Recorder(),
    )


async def test_removed_command_points_to_the_dashboard():
    from cogs.errors import ErrorHandler

    cog = ErrorHandler(SimpleNamespace())
    ctx = _ctx("welcome_image")
    await cog.on_command_error(ctx, commands.CommandNotFound("x"))
    (args, kwargs), = ctx.send.calls
    assert kwargs["embed"].title == "这项设置已移到控制台"
    assert kwargs["embed"].description == "在控制台的「欢迎新成员」里修改。"
    assert kwargs["view"].children[0].url == "https://rin-bot.com/dashboard/server/5#welcome"
    assert kwargs["delete_after"] == 15
    for other in (_ctx("nope"), _ctx("welcome_image", guild=False)):
        await cog.on_command_error(other, commands.CommandNotFound("x"))
        assert other.send.calls == []


async def test_toggle_migration_rewrites_rows(tmp_path):
    from cogs.commandtoggle import migrate_rows

    async with aiosqlite.connect(tmp_path / "t.db") as db:
        await db.execute("CREATE TABLE disabled_commands (guild_id INTEGER, command_name TEXT, PRIMARY KEY (guild_id, command_name))")
        await db.executemany(
            "INSERT INTO disabled_commands VALUES (?, ?)",
            [(1, "warns"), (1, "delwarn"), (1, "play"), (2, "rr_add"), (3, "kick")],
        )
        await db.commit()
        await migrate_rows(db)
        cur = await db.execute("SELECT guild_id, command_name FROM disabled_commands ORDER BY guild_id, command_name")
        assert await cur.fetchall() == [(1, "play"), (1, "warnings"), (3, "kick")]


async def test_global_migration_rewrites_rows(tmp_path):
    from cogs.globalsettings import migrate_global_rows

    async with aiosqlite.connect(tmp_path / "g.db") as db:
        await db.execute("CREATE TABLE global_disabled_cmds (name TEXT PRIMARY KEY)")
        await db.executemany("INSERT INTO global_disabled_cmds VALUES (?)", [("saveq",), ("tempban",), ("roll",)])
        await db.commit()
        await migrate_global_rows(db)
        cur = await db.execute("SELECT name FROM global_disabled_cmds ORDER BY name")
        assert await cur.fetchall() == [("playlist",), ("roll",)]
