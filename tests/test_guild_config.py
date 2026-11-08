import sqlite3
from contextlib import contextmanager

import pytest

from rincore import guild_config, storage


@contextmanager
def _con(name):
    """提交并关闭（Windows 上不关闭文件会一直被占用）。"""
    con = sqlite3.connect(storage.db_path(name))
    try:
        with con:
            yield con
    finally:
        con.close()


@pytest.fixture(autouse=True)
def dbs(tmp_path, monkeypatch):
    for name in storage.DB_FILES:
        monkeypatch.setitem(storage.DB_FILES, name, str(tmp_path / f"{name}.db"))


def _mod_config(**values):
    with _con("moderation") as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS mod_config (guild_id INTEGER PRIMARY KEY, "
            "log_channel INTEGER DEFAULT 0, warn_kick_threshold INTEGER DEFAULT 0, "
            "warn_ban_threshold INTEGER DEFAULT 0, warn_mute_threshold INTEGER DEFAULT 3, "
            "warn_mute_duration INTEGER DEFAULT 600)"
        )
        c.execute("INSERT INTO mod_config (guild_id) VALUES (1)")
        for column, value in values.items():
            c.execute(f"UPDATE mod_config SET {column}=? WHERE guild_id=1", (value,))


def _table_row(db_name, table):
    with _con(db_name) as c:
        c.execute(f"CREATE TABLE {table} (guild_id INTEGER PRIMARY KEY)")
        c.execute(f"INSERT INTO {table} (guild_id) VALUES (1)")


async def test_default_mod_config_row_is_not_config():
    _mod_config()
    assert await guild_config.has_config(1) is False


@pytest.mark.parametrize("column,value", [
    ("log_channel", 5), ("warn_kick_threshold", 2), ("warn_ban_threshold", 4),
    ("warn_mute_threshold", 5), ("warn_mute_duration", 60),
])
async def test_changed_mod_config_is_config(column, value):
    _mod_config(**{column: value})
    assert await guild_config.has_config(1) is True


@pytest.mark.parametrize("db_name,table", guild_config.CONFIG_TABLES)
async def test_any_config_table_row_is_config(db_name, table):
    _table_row(db_name, table)
    assert await guild_config.has_config(1) is True


async def test_config_of_other_guild_is_not_config():
    _table_row("welcome", "welcome_config")
    assert await guild_config.has_config(2) is False


async def test_missing_database_files_are_no_config():
    assert await guild_config.has_config(1) is False


async def test_existing_database_without_table_is_no_config():
    with _con("welcome") as c:
        c.execute("CREATE TABLE other (x INTEGER)")
    assert await guild_config.has_config(1) is False
