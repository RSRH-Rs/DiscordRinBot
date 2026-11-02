import os
import sqlite3

from rincore import storage

EXPECTED_KEYS = {
    "welcome", "automod", "moderation", "giveaway", "leveling", "botconfig",
    "reactionroles", "commandtoggle", "musicconfig", "botlog", "serverlog",
    "globalsettings", "music", "sync",
}


async def test_enable_wal_sets_journal_mode(tmp_path):
    a = str(tmp_path / "a.db")
    b = str(tmp_path / "b.db")
    sqlite3.connect(a).close()  # 已存在的库；b 不存在，应被创建
    await storage.enable_wal([a, b])
    for p in (a, b):
        assert os.path.exists(p)
        con = sqlite3.connect(p)
        try:
            assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        finally:
            con.close()


async def test_enable_wal_is_idempotent(tmp_path):
    a = str(tmp_path / "a.db")
    await storage.enable_wal([a])
    await storage.enable_wal([a])
    con = sqlite3.connect(a)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        con.close()


def test_db_files_cover_dashboard_constants():
    assert EXPECTED_KEYS <= set(storage.DB_FILES)
    assert storage.db_path("sync").endswith("sync.db")
    for path in storage.DB_FILES.values():
        assert os.path.isabs(path)
        assert os.path.dirname(path) == storage.BOT_DIR


async def test_enable_wal_survives_locked_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(storage, "_WAL_RETRY_DELAY", 0.01)
    monkeypatch.setattr(storage, "_WAL_TIMEOUT", 0.05)
    locked = str(tmp_path / "locked.db")
    other = str(tmp_path / "other.db")
    holder = sqlite3.connect(locked, isolation_level=None)
    holder.execute("CREATE TABLE t (x INTEGER)")
    holder.execute("BEGIN IMMEDIATE")  # 持有写事务，阻止切换 journal_mode
    try:
        await storage.enable_wal([locked, other])  # 不应抛异常
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    out = capsys.readouterr().out
    assert "locked.db" in out  # 失败要有日志
    con = sqlite3.connect(other)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        con.close()
    con = sqlite3.connect(locked)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    finally:
        con.close()


async def test_enable_wal_survives_unopenable_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(storage, "_WAL_RETRY_DELAY", 0.01)
    bad = str(tmp_path / "no_such_dir" / "x.db")
    good = str(tmp_path / "good.db")
    await storage.enable_wal([bad, good])
    assert "x.db" in capsys.readouterr().out
    con = sqlite3.connect(good)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        con.close()
