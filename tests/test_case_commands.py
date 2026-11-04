import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import aiosqlite
import discord
from discord.ext import commands

from command_tree import top_level_app_commands
from cogs import moderation
from cogs.errors import notice_for
from cogs.moderation import Moderation
from rincore import cases

SCHEMA = [
    """CREATE TABLE mod_cases (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, action TEXT NOT NULL,
       user_id INTEGER NOT NULL, mod_id INTEGER NOT NULL, reason TEXT DEFAULT '未提供原因', duration TEXT DEFAULT '',
       created_at REAL NOT NULL)""",
    "CREATE TABLE tempbans (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, unban_at REAL NOT NULL, PRIMARY KEY (guild_id, user_id))",
    """CREATE TABLE mod_config (guild_id INTEGER PRIMARY KEY, log_channel INTEGER DEFAULT 0, warn_kick_threshold INTEGER DEFAULT 0,
       warn_ban_threshold INTEGER DEFAULT 0, warn_mute_threshold INTEGER DEFAULT 3, warn_mute_duration INTEGER DEFAULT 600)""",
]


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class _Author:
    id = 9
    mention = "<@9>"

    def __init__(self, perms):
        self.guild_permissions = perms

    def __str__(self):
        return "管理员"


async def _db(tmp_path, monkeypatch, rows):
    path = str(tmp_path / "mod.db")
    monkeypatch.setattr(moderation, "DB_PATH", path)
    async with aiosqlite.connect(path) as db:
        for statement in SCHEMA:
            await db.execute(statement)
        await cases.migrate(db)
        for action, user_id in rows:
            duration = "1小时" if action in ("mute", "tempban") else ""
            await cases.next_case(db, 1, action, user_id, 9, "原因", duration, time.time())
        await db.commit()
    return path


def _member(user_id=5, timed_out_until=None):
    return SimpleNamespace(
        id=user_id, display_name=f"成员{user_id}", mention=f"<@{user_id}>", timed_out_until=timed_out_until,
        timeout=_Recorder(),
    )


def _guild(members=(), channel=None):
    by_id = {m.id: m for m in members}
    me = SimpleNamespace(guild_permissions=discord.Permissions.all())
    return SimpleNamespace(id=1, me=me, get_member=by_id.get, get_channel=lambda cid: channel)


def _ctx(guild, perms=None):
    return SimpleNamespace(
        guild=guild, author=_Author(perms or discord.Permissions.all()), interaction=None, me=guild.me,
        send=_Recorder(), channel=SimpleNamespace(permissions_for=lambda m: SimpleNamespace(embed_links=True)),
    )


def _titles(ctx):
    return [kwargs["embed"].title for _, kwargs in ctx.send.calls]


def test_case_group_shape():
    tops = {cmd.name: cmd for cmd in top_level_app_commands(Moderation)}
    assert "modlog" not in tops
    assert {c.name for c in tops["case"].commands} == {"list", "view", "reason", "duration"}


def test_invoke_errors_from_command_bodies_are_explained():
    wrapped = commands.CommandInvokeError(commands.MissingPermissions(["moderate_members"]))
    assert notice_for(wrapped).title == "你没有权限使用这条指令"


async def test_duration_on_expired_mute_is_refused(tmp_path, monkeypatch):
    await _db(tmp_path, monkeypatch, [("mute", 5), ("tempban", 6)])
    cog = Moderation(SimpleNamespace())
    for guild in (_guild([_member(5, timed_out_until=None)]), _guild([])):
        ctx = _ctx(guild)
        await Moderation.case_duration.callback(cog, ctx, 1, "2h")
        assert _titles(ctx) == ["这个案件没有可以修改的时长"]
    ctx = _ctx(_guild([]))
    await Moderation.case_duration.callback(cog, ctx, 2, "2h")
    assert _titles(ctx) == ["这个案件没有可以修改的时长"]


async def test_duration_updates_mute(tmp_path, monkeypatch):
    path = await _db(tmp_path, monkeypatch, [("mute", 5)])
    member = _member(5, timed_out_until=datetime.now(timezone.utc) + timedelta(minutes=30))
    cog = Moderation(SimpleNamespace())
    ctx = _ctx(_guild([member]))
    await Moderation.case_duration.callback(cog, ctx, 1, "2h")
    (args, kwargs), = member.timeout.calls
    assert abs((args[0] - datetime.now(timezone.utc)).total_seconds() - 7200) < 60
    async with aiosqlite.connect(path) as db:
        assert (await cases.get_case(db, 1, 1))["duration"] == "2小时"
    assert _titles(ctx)[0].startswith("案件 #1 将在 <t:")


async def test_duration_updates_tempban(tmp_path, monkeypatch):
    path = await _db(tmp_path, monkeypatch, [("tempban", 6)])
    async with aiosqlite.connect(path) as db:
        await db.execute("INSERT INTO tempbans VALUES (1, 6, ?)", (time.time() + 3600,))
        await db.commit()
    cog = Moderation(SimpleNamespace())
    ctx = _ctx(_guild([]))
    await Moderation.case_duration.callback(cog, ctx, 1, "3d")
    async with aiosqlite.connect(path) as db:
        unban_at = (await (await db.execute("SELECT unban_at FROM tempbans")).fetchone())[0]
    assert abs(unban_at - (time.time() + 3 * 86400)) < 60


async def test_duration_needs_matching_permission(tmp_path, monkeypatch):
    await _db(tmp_path, monkeypatch, [("mute", 5)])
    member = _member(5, timed_out_until=datetime.now(timezone.utc) + timedelta(minutes=30))
    cog = Moderation(SimpleNamespace())
    ctx = _ctx(_guild([member]), perms=discord.Permissions(manage_messages=True))
    try:
        await Moderation.case_duration.callback(cog, ctx, 1, "2h")
    except commands.MissingPermissions as error:
        assert error.missing_permissions == ["moderate_members"]
    else:
        raise AssertionError("expected MissingPermissions")
    assert member.timeout.calls == []


async def test_reason_updates_and_logs(tmp_path, monkeypatch):
    path = await _db(tmp_path, monkeypatch, [("warn", 5)])
    async with aiosqlite.connect(path) as db:
        await db.execute("INSERT INTO mod_config (guild_id, log_channel) VALUES (1, 77)")
        await db.commit()
    log = SimpleNamespace(send=_Recorder())
    cog = Moderation(SimpleNamespace())
    ctx = _ctx(_guild([], channel=log))
    await Moderation.case_reason.callback(cog, ctx, 1, reason="说脏话")
    async with aiosqlite.connect(path) as db:
        assert (await cases.get_case(db, 1, 1))["reason"] == "说脏话"
    assert _titles(ctx) == ["案件 #1 的原因已更新"]
    logged = log.send.calls[0][1]["embed"]
    assert logged.title == "案件 #1：原因已更新"
    assert [(f.name, f.value) for f in logged.fields][:2] == [("之前", "原因"), ("之后", "说脏话")]


async def test_unknown_case(tmp_path, monkeypatch):
    await _db(tmp_path, monkeypatch, [])
    cog = Moderation(SimpleNamespace())
    calls = (
        lambda c: Moderation.case_view.callback(cog, c, 99),
        lambda c: Moderation.case_reason.callback(cog, c, 99, reason="x"),
        lambda c: Moderation.case_duration.callback(cog, c, 99, "1h"),
    )
    for call in calls:
        ctx = _ctx(_guild([]))
        await call(ctx)
        assert _titles(ctx) == ["找不到案件 #99"]


async def test_case_autocomplete_active_only(tmp_path, monkeypatch):
    await _db(tmp_path, monkeypatch, [("mute", 5), ("mute", 6), ("warn", 5), ("tempban", 7)])
    active = _member(5, timed_out_until=datetime.now(timezone.utc) + timedelta(hours=1))
    expired = _member(6, timed_out_until=None)
    cog = Moderation(SimpleNamespace())
    interaction = SimpleNamespace(guild=_guild([active, expired]), locale=discord.Locale.chinese)
    got = await cog._case_duration_autocomplete(interaction, "")
    assert [c.value for c in got] == [1]
    assert "剩" in got[0].name
    every = await cog._case_autocomplete(interaction, "")
    assert [c.value for c in every] == [4, 3, 2, 1]
