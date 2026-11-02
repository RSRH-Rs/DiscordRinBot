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
