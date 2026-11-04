"""/roles 和 /serverlog：控制台做不到的面板编辑和忽略频道，留成指令组。"""
import json
from types import SimpleNamespace

import aiosqlite
import discord
import pytest

from command_tree import top_level_app_commands
from cogs import reactionroles, serverlog
from cogs.reactionroles import EXCLUSIVE_HINT, ReactionRoles, panel_description
from cogs.serverlog import DEFAULT_CATEGORIES, ServerLog
from rincore import legacy


class _Recorder:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error


class _Role:
    def __init__(self, role_id, name, position=1, managed=False, default=False):
        self.id, self.name, self.position, self.managed, self._default = role_id, name, position, managed, default
        self.mention = f"<@&{role_id}>"

    def is_default(self):
        return self._default

    def __ge__(self, other):
        return self.position >= other.position


BOT = SimpleNamespace(get_cog=lambda name: None)  # 没有系统日志模块时 audit 什么都不做
ME = SimpleNamespace(top_role=_Role(1, "小凛", position=10))
ROLES = {201: _Role(201, "游戏"), 202: _Role(202, "桌游"), 301: _Role(301, "红色"), 401: _Role(401, "新人")}
PANELS = [
    (111, 10, 5, "游戏身份组", {"🎮": 201, "🎲": 202}, 0),
    (112, 11, 5, "颜色", {"<:red:777>": 301}, 1),
    (113, 12, 5, "颜色", {"🔵": 301}, 0),
    (114, 10, 6, "别的服务器", {"🎮": 201}, 0),
]


def _http_error(cls, status):
    return cls(SimpleNamespace(status=status, reason="x"), "x")


def _guild(channels=None):
    channels = channels or {}
    return SimpleNamespace(id=5, me=ME, get_role=ROLES.get, get_channel=channels.get, get_channel_or_thread=channels.get)


def _ctx(guild=None, **extra):
    base = dict(
        guild=guild or _guild(), author=SimpleNamespace(id=1, mention="<@1>"), interaction=None, me=ME,
        send=_Recorder(), defer=_Recorder(), invoked_subcommand=None, subcommand_passed=None,
        channel=SimpleNamespace(permissions_for=lambda m: SimpleNamespace(embed_links=True)),
    )
    base.update(extra)
    return SimpleNamespace(**base)


def _card(ctx):
    return ctx.send.calls[0][1]["embed"]


async def _cog(tmp_path, monkeypatch, panels=PANELS):
    path = str(tmp_path / "rr.db")
    monkeypatch.setattr(reactionroles, "DB_PATH", path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS rr_panels (message_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL,"
            " guild_id INTEGER NOT NULL, title TEXT DEFAULT '身份组选择', mappings TEXT DEFAULT '{}', exclusive INTEGER DEFAULT 0)"
        )
        await db.execute("DELETE FROM rr_panels")
        await db.executemany(
            "INSERT INTO rr_panels VALUES (?, ?, ?, ?, ?, ?)",
            [(m, c, g, t, json.dumps(mp), e) for m, c, g, t, mp, e in panels],
        )
        await db.commit()
    cog = ReactionRoles(BOT)
    await cog.cog_load()
    cog.refreshed, cog.refresh_result = [], "ok"

    async def refresh(guild, panel, mappings, exclusive):
        cog.refreshed.append((panel["message_id"], dict(mappings), exclusive))
        return cog.refresh_result

    cog._refresh_panel = refresh
    return cog, path


async def _stored(path, message_id):
    async with aiosqlite.connect(path) as db:
        row = await (await db.execute("SELECT mappings, exclusive FROM rr_panels WHERE message_id = ?", (message_id,))).fetchone()
    return None if row is None else (json.loads(row[0]), row[1])


# ─── 指令表 ───

def test_roles_and_serverlog_groups():
    roles = {c.name: c for c in top_level_app_commands(ReactionRoles)}
    assert set(roles) == {"roles"}
    assert {c.name for c in roles["roles"].commands} == {"list", "add", "remove", "exclusive", "delete"}
    logs = {c.name: c for c in top_level_app_commands(ServerLog)}
    assert set(logs) == {"serverlog"}
    assert {c.name for c in logs["serverlog"].commands} == {"ignore", "unignore"}
    assert ServerLog.serverlog_group.aliases == ["slog"]


def test_old_names_reach_the_groups():
    assert legacy.rewrite("r!rr_add 111 🎮 @游戏") == "r!roles add 111 🎮 @游戏"
    for old, new in (("rr_remove", "roles remove"), ("rr_list", "roles list"), ("rr_exclusive", "roles exclusive"), ("rr_delete", "roles delete")):
        assert legacy.RENAMED[old] == new
    assert legacy.REMOVED["rr_create"] == ("roles", "领取身份组")
    for sub in ("channel", "toggle", "enable", "disable", "status"):
        assert legacy.REMOVED[f"serverlog {sub}"] == ("serverlog", "服务器事件日志")
    assert "serverlog" not in legacy.REMOVED and "slog" not in legacy.REMOVED
    assert legacy.migrate_disabled({"rr_add", "rr_delete", "serverlog", "rr_create"}) == {"roles", "serverlog"}


def test_add_keeps_the_old_argument_order():
    assert [p.name for p in ReactionRoles.roles_add.app_command.parameters] == ["panel", "emoji", "role"]
    assert [p.name for p in ReactionRoles.roles_remove.app_command.parameters] == ["panel", "role"]
    assert [p.name for p in ReactionRoles.roles_exclusive.app_command.parameters] == ["panel", "enabled"]


# ─── 选面板 ───

async def test_panel_autocomplete_lists_this_servers_panels(tmp_path, monkeypatch):
    cog, _ = await _cog(tmp_path, monkeypatch)
    channels = {10: SimpleNamespace(name="领身份组"), 11: SimpleNamespace(name="颜色区")}
    interaction = SimpleNamespace(guild=_guild(channels), locale=discord.Locale.chinese)
    got = await cog._panel_autocomplete(interaction, "")
    assert [(c.name, c.value) for c in got] == [
        ("游戏身份组（#领身份组，2 个身份组）", "111"),
        ("颜色（#颜色区，1 个身份组）", "112"),
        ("颜色（频道已删除，1 个身份组）", "113"),
    ]
    assert [c.value for c in await cog._panel_autocomplete(interaction, "游戏")] == ["111"]
    english = SimpleNamespace(guild=_guild(channels), locale=discord.Locale.american_english)
    assert (await cog._panel_autocomplete(english, "游戏"))[0].name == "游戏身份组 (#领身份组, 2 roles)"


async def test_find_panel_accepts_ids_links_and_titles(tmp_path, monkeypatch):
    cog, _ = await _cog(tmp_path, monkeypatch)
    for text in ("111", "https://discord.com/channels/5/10/111", "游戏身份组", "  游戏身份组 "):
        panel, notice = await cog._find_panel(5, text)
        assert notice is None and panel["message_id"] == 111, text
    panel, notice = await cog._find_panel(5, "颜色")
    assert panel is None
    assert (notice.title, notice.description) == ("有 2 个面板都叫「颜色」", "从列表里选，或者填面板的消息 ID。")
    for text in ("114", "别的服务器", "999", "", "https://discord.com/channels/6/10/114"):
        panel, notice = await cog._find_panel(5, text)
        assert panel is None and notice.title == "找不到这个面板", text


# ─── /roles add ───

async def test_add_puts_a_role_on_the_panel(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    ctx = _ctx()
    await ReactionRoles.roles_add.callback(cog, ctx, "111", "⭐", ROLES[401])
    assert await _stored(path, 111) == ({"🎮": 201, "🎲": 202, "⭐": 401}, 0)
    assert cog._cache[111]["mappings"] == {"🎮": 201, "🎲": 202, "⭐": 401}
    assert cog.refreshed == [(111, {"🎮": 201, "🎲": 202, "⭐": 401}, False)]
    assert (_card(ctx).title, _card(ctx).description) == ("面板已更新", "⭐ <@&401> 已加到「游戏身份组」，现在有 3 个身份组。")


async def test_add_moves_a_role_that_is_already_on_the_panel(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    await ReactionRoles.roles_add.callback(cog, _ctx(), "111", "⭐", ROLES[201])
    assert await _stored(path, 111) == ({"🎲": 202, "⭐": 201}, 0)


async def test_add_refusals(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    cases = [
        (("999", "⭐", ROLES[401]), "找不到这个面板"),
        (("111", "⭐", _Role(501, "管理员", position=10)), "我分配不了「管理员」"),
        (("111", "⭐", _Role(502, "音乐机器人", managed=True)), "「音乐机器人」不能用来领取"),
        (("111", "⭐", _Role(5, "@everyone", position=0, default=True)), "「@everyone」不能用来领取"),
    ]
    for args, title in cases:
        ctx = _ctx()
        await ReactionRoles.roles_add.callback(cog, ctx, *args)
        assert _card(ctx).title == title
    assert await _stored(path, 111) == ({"🎮": 201, "🎲": 202}, 0)
    assert cog.refreshed == []


async def test_add_refuses_a_full_panel(tmp_path, monkeypatch):
    full = {f"e{i}": 1000 + i for i in range(20)}
    cog, path = await _cog(tmp_path, monkeypatch, [(111, 10, 5, "满了", full, 0)])
    ctx = _ctx()
    await ReactionRoles.roles_add.callback(cog, ctx, "111", "⭐", ROLES[401])
    assert (_card(ctx).title, _card(ctx).description) == ("这个面板已经有 20 个身份组了", "一个面板最多 20 个身份组，先去掉一个再加。")
    await ReactionRoles.roles_add.callback(cog, _ctx(), "111", "e0", ROLES[401])
    assert (await _stored(path, 111))[0]["e0"] == 401


@pytest.mark.parametrize("result, title", [
    ("bad_emoji", "这个 emoji 用不了"),
    ("gone", "面板消息已经不在了"),
    ("failed", "面板没更新成功"),
])
async def test_add_changes_nothing_when_the_panel_cannot_change(tmp_path, monkeypatch, result, title):
    cog, path = await _cog(tmp_path, monkeypatch)
    cog.refresh_result = result
    ctx = _ctx()
    await ReactionRoles.roles_add.callback(cog, ctx, "111", "abc", ROLES[401])
    assert _card(ctx).title == title
    assert await _stored(path, 111) == ({"🎮": 201, "🎲": 202}, 0)
    assert cog._cache[111]["mappings"] == {"🎮": 201, "🎲": 202}


# ─── /roles remove ───

@pytest.mark.parametrize("button", ["🎲", "<@&202>", "202", "桌游"])
async def test_remove_takes_a_role_off(tmp_path, monkeypatch, button):
    cog, path = await _cog(tmp_path, monkeypatch)
    ctx = _ctx()
    await ReactionRoles.roles_remove.callback(cog, ctx, "游戏身份组", role=button)
    assert await _stored(path, 111) == ({"🎮": 201}, 0)
    assert cog.refreshed == [(111, {"🎮": 201}, False)]
    assert (_card(ctx).title, _card(ctx).description) == ("面板已更新", "已从「游戏身份组」去掉 🎲 <@&202>，还剩 1 个身份组。")


async def test_remove_refusals(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    ctx = _ctx()
    await ReactionRoles.roles_remove.callback(cog, ctx, "111", role="⭐")
    assert (_card(ctx).title, _card(ctx).description) == ("面板上没有这个身份组", "从列表里选一个要去掉的身份组。")
    ctx = _ctx()
    await ReactionRoles.roles_remove.callback(cog, ctx, "112", role="<:red:777>")
    assert (_card(ctx).title, _card(ctx).description) == ("面板至少要留一个身份组", "要整个删掉，用 /roles delete。")
    assert await _stored(path, 112) == ({"<:red:777>": 301}, 1)
    assert cog.refreshed == []


async def test_remove_suggests_the_panels_roles(tmp_path, monkeypatch):
    cog, _ = await _cog(tmp_path, monkeypatch)

    async def suggest(panel, locale=discord.Locale.chinese):
        interaction = SimpleNamespace(guild=_guild(), locale=locale, namespace=SimpleNamespace(panel=panel))
        return [(c.name, c.value) for c in await cog._button_autocomplete(interaction, "")]

    assert await suggest("111") == [("🎮 游戏", "🎮"), ("🎲 桌游", "🎲")]
    assert await suggest("112") == [(":red: 红色", "<:red:777>")]
    assert await suggest("颜色") == [] and await suggest(None) == []
    ROLES.pop(202)
    try:
        assert await suggest("111") == [("🎮 游戏", "🎮"), ("🎲 身份组已删除", "🎲")]
        assert (await suggest("111", discord.Locale.american_english))[1] == ("🎲 deleted role", "🎲")
    finally:
        ROLES[202] = _Role(202, "桌游")


# ─── /roles exclusive ───

async def test_exclusive_switches_mode(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    ctx = _ctx()
    await ReactionRoles.roles_exclusive.callback(cog, ctx, "111", True)
    assert await _stored(path, 111) == ({"🎮": 201, "🎲": 202}, 1)
    assert cog._cache[111]["exclusive"] is True
    assert cog.refreshed == [(111, {"🎮": 201, "🎲": 202}, True)]
    assert (_card(ctx).title, _card(ctx).description) == ("「游戏身份组」改成了单选", "成员只能领一个身份组，换选时自动替换。")
    ctx = _ctx()
    await ReactionRoles.roles_exclusive.callback(cog, ctx, "111", True)
    assert _card(ctx).title == "「游戏身份组」本来就是单选"
    ctx = _ctx()
    await ReactionRoles.roles_exclusive.callback(cog, ctx, "112", False)
    assert (_card(ctx).title, _card(ctx).description) == ("「颜色」改成了多选", "成员可以同时领多个身份组。")
    assert await _stored(path, 112) == ({"<:red:777>": 301}, 0)


async def test_exclusive_changes_nothing_when_the_panel_is_gone(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    cog.refresh_result = "gone"
    ctx = _ctx()
    await ReactionRoles.roles_exclusive.callback(cog, ctx, "111", True)
    assert _card(ctx).title == "面板消息已经不在了"
    assert await _stored(path, 111) == ({"🎮": 201, "🎲": 202}, 0)


def test_panel_description_tracks_the_hint():
    text = "点按钮领身份组"
    assert panel_description(text, True) == f"{text}\n\n{EXCLUSIVE_HINT}"
    assert panel_description(f"{text}\n\n{EXCLUSIVE_HINT}", False) == text
    assert panel_description(f"{text}\n\n{EXCLUSIVE_HINT}", True) == f"{text}\n\n{EXCLUSIVE_HINT}"
    assert panel_description(None, False) == "点击下方按钮领取对应身份组"
    assert panel_description("", True) == f"点击下方按钮领取对应身份组\n\n{EXCLUSIVE_HINT}"


async def test_refresh_keeps_the_panel_text():
    cog = ReactionRoles(SimpleNamespace())
    rebuilt = []

    async def rebuild(message, title, mappings, guild, description=""):
        rebuilt.append((message.id, title, dict(mappings), description))
        return cog.status

    cog._rebuild_panel = rebuild
    message = SimpleNamespace(id=111, embeds=[SimpleNamespace(description="自己写的说明")])
    fetch = {"result": message}

    async def fetch_message(message_id):
        if isinstance(fetch["result"], Exception):
            raise fetch["result"]
        return fetch["result"]

    guild = _guild({10: SimpleNamespace(id=10, fetch_message=fetch_message)})
    panel = {"message_id": 111, "channel_id": 10, "title": "游戏身份组"}
    for status, result in ((200, "ok"), (400, "bad_emoji"), (404, "gone"), (500, "failed"), (0, "failed")):
        cog.status = status
        assert await cog._refresh_panel(guild, panel, {"🎮": 201}, True) == result
    assert rebuilt[0] == (111, "游戏身份组", {"🎮": 201}, f"自己写的说明\n\n{EXCLUSIVE_HINT}")
    fetch["result"] = _http_error(discord.NotFound, 404)
    assert await cog._refresh_panel(guild, panel, {}, False) == "gone"
    fetch["result"] = _http_error(discord.Forbidden, 403)
    assert await cog._refresh_panel(guild, panel, {}, False) == "failed"
    assert await cog._refresh_panel(_guild(), panel, {}, False) == "gone"


async def test_rebuild_reports_the_discord_status(monkeypatch):
    class _Response:
        status = 400

        async def text(self):
            return "Invalid emoji"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Session:
        def patch(self, *args, **kwargs):
            return _Response()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(reactionroles.aiohttp, "ClientSession", _Session)
    cog = ReactionRoles(SimpleNamespace(http=SimpleNamespace(token="t")))
    message = SimpleNamespace(id=111, channel=SimpleNamespace(id=10))
    assert await cog._rebuild_panel(message, "标题", {"abc": 201}, _guild()) == 400


# ─── /roles delete、list ───

async def test_delete_removes_the_panel(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    deleted = _Recorder()
    channels = {10: SimpleNamespace(get_partial_message=lambda mid: SimpleNamespace(id=mid, delete=deleted))}
    ctx = _ctx(_guild(channels))
    await ReactionRoles.roles_delete.callback(cog, ctx, "111")
    assert await _stored(path, 111) is None and 111 not in cog._cache
    assert len(deleted.calls) == 1
    assert (_card(ctx).title, _card(ctx).description) == ("已删除面板「游戏身份组」", None)


async def test_delete_explains_a_message_it_cannot_remove(tmp_path, monkeypatch):
    cog, path = await _cog(tmp_path, monkeypatch)
    forbidden = _Recorder(_http_error(discord.Forbidden, 403))
    gone = _Recorder(_http_error(discord.NotFound, 404))
    channels = {
        10: SimpleNamespace(get_partial_message=lambda mid: SimpleNamespace(id=mid, delete=forbidden)),
        11: SimpleNamespace(get_partial_message=lambda mid: SimpleNamespace(id=mid, delete=gone)),
    }
    ctx = _ctx(_guild(channels))
    await ReactionRoles.roles_delete.callback(cog, ctx, "111")
    assert _card(ctx).description == "我没有权限删掉面板消息，请手动删除。"
    ctx = _ctx(_guild(channels))
    await ReactionRoles.roles_delete.callback(cog, ctx, "112")
    assert _card(ctx).description is None
    assert await _stored(path, 111) is None and await _stored(path, 112) is None


async def test_list_shows_panels_with_links(tmp_path, monkeypatch):
    cog, _ = await _cog(tmp_path, monkeypatch)
    channels = {10: SimpleNamespace(mention="<#10>"), 11: SimpleNamespace(mention="<#11>")}
    ctx = _ctx(_guild(channels))
    await ReactionRoles.roles_list.callback(cog, ctx)
    card = _card(ctx)
    assert card.title == "身份组面板"
    assert [(f.name, f.value) for f in card.fields] == [
        ("游戏身份组", "<#10>，2 个身份组，多选\n[跳到面板](https://discord.com/channels/5/10/111)"),
        ("颜色", "<#11>，1 个身份组，单选\n[跳到面板](https://discord.com/channels/5/11/112)"),
        ("颜色", "频道已删除，1 个身份组，多选"),
    ]


async def test_list_shows_at_most_25_panels(tmp_path, monkeypatch):
    many = [(1000 + i, 10, 5, f"面板{i}", {"🎮": 201}, 0) for i in range(27)]
    cog, _ = await _cog(tmp_path, monkeypatch, many)
    ctx = _ctx()
    await ReactionRoles.roles_list.callback(cog, ctx)
    assert len(_card(ctx).fields) == 25
    assert _card(ctx).footer.text == "还有 2 个面板没列出来"


async def test_list_without_panels_points_to_the_dashboard(tmp_path, monkeypatch):
    cog, _ = await _cog(tmp_path, monkeypatch, [])
    ctx = _ctx()
    await ReactionRoles.roles_list.callback(cog, ctx)
    assert (_card(ctx).title, _card(ctx).description) == ("还没有身份组面板", "在控制台的「领取身份组」里发一个。")
    assert ctx.send.calls[0][1]["view"].children[0].url == "https://rin-bot.com/dashboard/server/5#roles"


# ─── /serverlog ignore、unignore ───

CHANNEL = SimpleNamespace(id=10, name="闲聊", mention="<#10>")


async def _log_cog(tmp_path, monkeypatch, row=None):
    path = str(tmp_path / "sl.db")
    monkeypatch.setattr(serverlog, "DB_PATH", path)
    cog = ServerLog(BOT)
    await cog.cog_load()
    if row is not None:
        # 控制台刚保存、机器人还没收到重载通知：缓存是旧的
        async with aiosqlite.connect(path) as db:
            await db.execute("INSERT INTO serverlog_config VALUES (?, ?, ?, ?, ?)", row)
            await db.commit()
    return cog, path


async def _log_row(path):
    async with aiosqlite.connect(path) as db:
        return await (await db.execute(
            "SELECT channel_id, enabled, categories, ignored_channels FROM serverlog_config WHERE guild_id = 5"
        )).fetchone()


async def test_ignore_keeps_the_dashboard_settings(tmp_path, monkeypatch):
    cog, path = await _log_cog(tmp_path, monkeypatch, (5, 77, 1, "ban,message", "11"))
    ctx = _ctx()
    await ServerLog.sl_ignore.callback(cog, ctx, CHANNEL)
    assert await _log_row(path) == (77, 1, "ban,message", "10,11")
    assert cog.get_config(5)["ignored"] == {10, 11} and cog.get_config(5)["channel_id"] == 77
    card = _card(ctx)
    assert (card.title, card.description) == ("已忽略 #闲聊", "这个频道里删除和编辑的消息不会再记进日志。")
    assert [(f.name, f.value) for f in card.fields] == [("现在忽略的频道", "<#10> <#11>")]


async def test_ignore_without_a_saved_config(tmp_path, monkeypatch):
    cog, path = await _log_cog(tmp_path, monkeypatch)
    await ServerLog.sl_ignore.callback(cog, _ctx(), CHANNEL)
    assert await _log_row(path) == (0, 1, ",".join(sorted(DEFAULT_CATEGORIES)), "10")
    ctx = _ctx()
    await ServerLog.sl_ignore.callback(cog, ctx, CHANNEL)
    assert _card(ctx).title == "#闲聊 已经在忽略列表里了"


async def test_unignore(tmp_path, monkeypatch):
    cog, path = await _log_cog(tmp_path, monkeypatch, (5, 77, 1, "ban", "10"))
    ctx = _ctx()
    await ServerLog.sl_unignore.callback(cog, ctx, CHANNEL)
    assert await _log_row(path) == (77, 1, "ban", "")
    card = _card(ctx)
    assert (card.title, card.description) == ("已恢复记录 #闲聊", "这个频道里删除和编辑的消息会照常记进日志。")
    assert [(f.name, f.value) for f in card.fields] == [("现在忽略的频道", "没有")]
    ctx = _ctx()
    await ServerLog.sl_unignore.callback(cog, ctx, CHANNEL)
    assert _card(ctx).title == "#闲聊 本来就没有被忽略"


async def test_serverlog_bare_and_old_subcommands(tmp_path, monkeypatch):
    cog, _ = await _log_cog(tmp_path, monkeypatch, (5, 77, 1, "ban", "10"))
    await cog.reload_guild(5)
    ctx = _ctx()
    await ServerLog.serverlog_group.callback(cog, ctx)
    assert (_card(ctx).title, _card(ctx).description) == ("审计日志忽略的频道", "<#10>")
    ctx = _ctx(subcommand_passed="channel")
    await ServerLog.serverlog_group.callback(cog, ctx)
    assert _card(ctx).title == "这项设置已移到控制台"
    assert ctx.send.calls[0][1]["view"].children[0].url == "https://rin-bot.com/dashboard/server/5#serverlog"
