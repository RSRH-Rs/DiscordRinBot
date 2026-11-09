import os
import sqlite3
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from rincore import guild_cleanup, storage
from cogs.guildcleanup import GuildCleanup

DAY = 86400
NOW = 1_800_000_000.0
OLD, RECENT, STAYING = 111, 222, 333  # 移出 31 天 / 移出 10 天 / 一直在

# 库名 -> 建表语句（与线上表结构一致的最小子集）
SCHEMAS = {
    "leveling": ["CREATE TABLE users (guild_id INTEGER, user_id INTEGER, xp INTEGER DEFAULT 0, "
                 "level INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))",
                 "CREATE TABLE level_config (guild_id INTEGER PRIMARY KEY)"],
    "moderation": [
        "CREATE TABLE warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, "
        "user_id INTEGER NOT NULL)",
        "CREATE TABLE mod_cases (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, "
        "user_id INTEGER NOT NULL)",
        "CREATE TABLE mod_config (guild_id INTEGER PRIMARY KEY, log_channel INTEGER DEFAULT 0)",
        "CREATE TABLE tempbans (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
        "PRIMARY KEY (guild_id, user_id))",
    ],
    "giveaway": [
        "CREATE TABLE giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL)",
        "CREATE TABLE giveaway_entries (giveaway_id INTEGER, user_id INTEGER, "
        "PRIMARY KEY (giveaway_id, user_id))",
        "CREATE TABLE giveaway_winners (giveaway_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
        "PRIMARY KEY (giveaway_id, user_id))",
    ],
    "music": ["CREATE TABLE saved_queues (guild_id INTEGER NOT NULL, name TEXT NOT NULL, "
              "PRIMARY KEY (guild_id, name))"],
    "reactionroles": ["CREATE TABLE rr_panels (message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL)"],
    "welcome": ["CREATE TABLE welcome_config (guild_id INTEGER PRIMARY KEY, welcome_image_file TEXT DEFAULT '')"],
    "automod": ["CREATE TABLE automod_config (guild_id INTEGER PRIMARY KEY)"],
    "serverlog": ["CREATE TABLE serverlog_config (guild_id INTEGER PRIMARY KEY)"],
    "botlog": ["CREATE TABLE botlog_config (guild_id INTEGER PRIMARY KEY)"],
    "musicconfig": ["CREATE TABLE music_config (guild_id INTEGER PRIMARY KEY)"],
    "commandtoggle": ["CREATE TABLE disabled_commands (guild_id INTEGER NOT NULL, command_name TEXT NOT NULL, "
                      "PRIMARY KEY (guild_id, command_name))"],
    "globalsettings": [
        "CREATE TABLE global_flags (key TEXT PRIMARY KEY, value TEXT DEFAULT '')",
        "CREATE TABLE blacklist (user_id INTEGER PRIMARY KEY, reason TEXT DEFAULT '')",
        "CREATE TABLE broadcasts (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL)",
        "CREATE TABLE global_disabled_cmds (name TEXT PRIMARY KEY)",
    ],
}

# 每张按服务器存的表：(库名, 表名)
GUILD_TABLES = [
    ("leveling", "users"), ("leveling", "level_config"), ("moderation", "warnings"), ("moderation", "mod_cases"),
    ("moderation", "mod_config"), ("moderation", "tempbans"), ("giveaway", "giveaways"),
    ("music", "saved_queues"), ("reactionroles", "rr_panels"), ("welcome", "welcome_config"),
    ("automod", "automod_config"), ("serverlog", "serverlog_config"), ("botlog", "botlog_config"),
    ("musicconfig", "music_config"), ("commandtoggle", "disabled_commands"),
]


@contextmanager
def _con(name):
    """提交并关闭（sqlite3 自带的 with 只提交不关闭，Windows 上文件会一直被占用）。"""
    con = sqlite3.connect(storage.db_path(name))
    try:
        with con:
            yield con
    finally:
        con.close()


def _seed_guild(gid):
    with _con("leveling") as c:
        c.execute("INSERT INTO users (guild_id, user_id, xp) VALUES (?, 7, 50)", (gid,))
        c.execute("INSERT INTO level_config (guild_id) VALUES (?)", (gid,))
    with _con("moderation") as c:
        c.execute("INSERT INTO warnings (guild_id, user_id) VALUES (?, 7)", (gid,))
        c.execute("INSERT INTO mod_cases (guild_id, user_id) VALUES (?, 7)", (gid,))
        c.execute("INSERT INTO mod_config (guild_id) VALUES (?)", (gid,))
        c.execute("INSERT INTO tempbans (guild_id, user_id) VALUES (?, 7)", (gid,))
    with _con("giveaway") as c:
        cur = c.execute("INSERT INTO giveaways (guild_id) VALUES (?)", (gid,))
        c.execute("INSERT INTO giveaway_entries VALUES (?, 7)", (cur.lastrowid,))
        c.execute("INSERT INTO giveaway_winners VALUES (?, 7)", (cur.lastrowid,))
    for name, sql in (
        ("music", "INSERT INTO saved_queues (guild_id, name) VALUES (?, 'q')"),
        ("reactionroles", f"INSERT INTO rr_panels (message_id, guild_id) VALUES ({gid * 10}, ?)"),
        ("welcome", "INSERT INTO welcome_config (guild_id) VALUES (?)"),
        ("automod", "INSERT INTO automod_config (guild_id) VALUES (?)"),
        ("serverlog", "INSERT INTO serverlog_config (guild_id) VALUES (?)"),
        ("botlog", "INSERT INTO botlog_config (guild_id) VALUES (?)"),
        ("musicconfig", "INSERT INTO music_config (guild_id) VALUES (?)"),
        ("commandtoggle", "INSERT INTO disabled_commands (guild_id, command_name) VALUES (?, 'roll')"),
    ):
        with _con(name) as c:
            c.execute(sql, (gid,))


def _count(name, table, gid):
    with _con(name) as c:
        return c.execute(f"SELECT COUNT(*) FROM {table} WHERE guild_id=?", (gid,)).fetchone()[0]


def _giveaway_children(gid):
    with _con("giveaway") as c:
        return [
            c.execute(
                f"SELECT COUNT(*) FROM {t} WHERE giveaway_id IN (SELECT id FROM giveaways WHERE guild_id=?)",
                (gid,),
            ).fetchone()[0]
            for t in ("giveaway_entries", "giveaway_winners")
        ]


def _all_children():
    with _con("giveaway") as c:
        return [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("giveaway_entries", "giveaway_winners")]


def _image(upload_dir, name):
    path = os.path.join(upload_dir, name)
    with open(path, "wb") as f:
        f.write(b"x")
    return path


@pytest.fixture
def dbs(tmp_path, monkeypatch):
    files = {name: str(tmp_path / f"{name}.db") for name in storage.DB_FILES}
    monkeypatch.setattr(storage, "DB_FILES", files)
    upload_dir = tmp_path / "uploads" / "welcome"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(guild_cleanup, "WELCOME_UPLOAD_DIR", str(upload_dir))
    for name, statements in SCHEMAS.items():
        with _con(name) as c:
            for sql in statements:
                c.execute(sql)
    for gid in (OLD, RECENT, STAYING):
        _seed_guild(gid)
    with _con("globalsettings") as c:
        c.execute("INSERT INTO global_flags VALUES ('maintenance', '1')")
        c.execute(f"INSERT INTO blacklist (user_id) VALUES ({OLD})")
        c.execute("INSERT INTO broadcasts (message) VALUES ('hi')")
        c.execute("INSERT INTO global_disabled_cmds VALUES ('roll')")
    return SimpleNamespace(upload_dir=str(upload_dir))


async def _remove_old_and_recent():
    await guild_cleanup.mark_removed(OLD, now=NOW - 31 * DAY)
    await guild_cleanup.mark_removed(RECENT, now=NOW - 10 * DAY)


async def test_mark_removed_records_pending_row(dbs):
    await guild_cleanup.mark_removed(OLD, now=NOW)
    assert await guild_cleanup.pending() == {OLD: NOW}


async def test_mark_removed_keeps_first_removal_time(dbs):
    await guild_cleanup.mark_removed(OLD, now=NOW - DAY)
    await guild_cleanup.mark_removed(OLD, now=NOW)
    assert await guild_cleanup.pending() == {OLD: NOW - DAY}


async def test_clear_removed_drops_pending_row(dbs):
    await _remove_old_and_recent()
    await guild_cleanup.clear_removed(OLD)
    assert await guild_cleanup.pending() == {RECENT: NOW - 10 * DAY}


async def test_purge_deletes_only_guilds_past_30_days(dbs):
    await _remove_old_and_recent()
    purged = await guild_cleanup.purge_due(now=NOW)
    assert purged == [OLD]
    for name, table in GUILD_TABLES:
        assert _count(name, table, OLD) == 0, table
        assert _count(name, table, RECENT) == 1, table
        assert _count(name, table, STAYING) == 1, table
    assert _giveaway_children(RECENT) == [1, 1] and _giveaway_children(STAYING) == [1, 1]
    assert _all_children() == [2, 2]  # 被删服务器的参与/中奖记录也一起删掉
    assert await guild_cleanup.pending() == {RECENT: NOW - 10 * DAY}


async def test_purge_leaves_global_tables_alone(dbs):
    await _remove_old_and_recent()
    await guild_cleanup.purge_due(now=NOW)
    with _con("globalsettings") as c:
        assert c.execute("SELECT key, value FROM global_flags").fetchall() == [("maintenance", "1")]
        assert c.execute("SELECT user_id FROM blacklist").fetchall() == [(OLD,)]
        assert c.execute("SELECT message FROM broadcasts").fetchall() == [("hi",)]
        assert c.execute("SELECT name FROM global_disabled_cmds").fetchall() == [("roll",)]


async def test_purge_deletes_only_that_guilds_welcome_images(dbs):
    gone = [_image(dbs.upload_dir, f"{OLD}-welcome-0123456789abcdef.png"),
            _image(dbs.upload_dir, f"{OLD}-farewell-fedcba9876543210.gif")]
    kept = [_image(dbs.upload_dir, f"{RECENT}-welcome-0123456789abcdef.png"),
            _image(dbs.upload_dir, f"{OLD}1-welcome-0123456789abcdef.png"),  # 另一个 id 以 111 开头
            _image(dbs.upload_dir, f"{OLD}-notes.txt")]
    await _remove_old_and_recent()
    await guild_cleanup.purge_due(now=NOW)
    assert not any(os.path.exists(p) for p in gone)
    assert all(os.path.exists(p) for p in kept)


async def test_purge_skips_missing_tables_and_databases_quietly(dbs, capsys):
    os.remove(storage.db_path("music"))
    with _con("giveaway") as c:
        c.execute("DROP TABLE giveaway_winners")
    await _remove_old_and_recent()
    assert await guild_cleanup.purge_due(now=NOW) == [OLD]
    assert not os.path.exists(storage.db_path("music"))  # 不会凭空建出空库
    assert _count("giveaway", "giveaways", OLD) == 0
    assert "失败" not in capsys.readouterr().out
    assert await guild_cleanup.pending() == {RECENT: NOW - 10 * DAY}


async def test_failing_table_is_logged_and_others_still_deleted(dbs, capsys):
    with _con("leveling") as c:  # 让这张表的删除报错
        c.execute("CREATE TRIGGER no_delete BEFORE DELETE ON users BEGIN SELECT RAISE(ABORT, 'locked'); END")
    await _remove_old_and_recent()
    assert await guild_cleanup.purge_due(now=NOW) == []
    out = capsys.readouterr().out
    assert "失败" in out and "users" in out
    assert _count("leveling", "users", OLD) == 1
    assert _count("moderation", "warnings", OLD) == 0
    assert _count("commandtoggle", "disabled_commands", OLD) == 0
    # 没删干净就保留待删记录，下次再试
    assert OLD in await guild_cleanup.pending()


async def test_purge_tells_cogs_to_drop_cached_config(dbs):
    await _remove_old_and_recent()
    await guild_cleanup.purge_due(now=NOW)
    with _con("sync") as c:
        rows = c.execute("SELECT module, guild_id FROM changes").fetchall()
    assert {g for _, g in rows} == {OLD}
    assert {"automod", "commands", "reactionroles", "serverlog"} <= {m for m, _ in rows}
    assert "global" not in {m for m, _ in rows}


async def test_reconcile_clears_present_and_marks_missed_removals(dbs):
    await guild_cleanup.mark_removed(STAYING, now=NOW - 40 * DAY)  # 离线期间被重新邀请
    await guild_cleanup.mark_removed(OLD, now=NOW - 31 * DAY)
    await guild_cleanup.reconcile({STAYING}, now=NOW)
    # RECENT 有数据但机器人不在里面（离线时被移出）：从现在开始计时；OLD 保留原来的时间
    assert await guild_cleanup.pending() == {OLD: NOW - 31 * DAY, RECENT: NOW}


async def test_reconcile_does_nothing_when_bot_sees_no_guilds(dbs):
    await guild_cleanup.reconcile(set(), now=NOW)
    assert await guild_cleanup.pending() == {}


def _cog(guilds=()):
    bot = SimpleNamespace(guilds=[SimpleNamespace(id=g) for g in guilds])
    return GuildCleanup(bot)


async def test_cog_records_removal_and_rejoin_clears_it(dbs):
    cog = _cog()
    before = time.time()
    await cog.on_guild_remove(SimpleNamespace(id=OLD))
    pending = await guild_cleanup.pending()
    assert list(pending) == [OLD] and pending[OLD] >= before
    await cog.on_guild_join(SimpleNamespace(id=OLD))
    assert await guild_cleanup.pending() == {}


async def test_cog_run_once_reconciles_then_purges(dbs):
    await guild_cleanup.mark_removed(OLD, now=time.time() - 31 * DAY)
    await guild_cleanup.mark_removed(STAYING, now=time.time() - 31 * DAY)  # 已经回来了，不能删
    await _cog(guilds=[STAYING]).run_once()
    assert _count("leveling", "users", OLD) == 0
    assert _count("leveling", "users", STAYING) == 1
    assert set(await guild_cleanup.pending()) == {RECENT}
