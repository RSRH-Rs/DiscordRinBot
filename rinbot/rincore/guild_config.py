"""判断一个服务器是否已经有人配置过小凛，只读各模块的配置表。"""
import os
import sqlite3

import aiosqlite

from rincore import storage

_BUSY_TIMEOUT = 5.0

# 有一行就算配置过的表：(库名, 表名)
CONFIG_TABLES = (
    ("welcome", "welcome_config"),
    ("automod", "automod_config"),
    ("botlog", "botlog_config"),
    ("serverlog", "serverlog_config"),
    ("musicconfig", "music_config"),
)

# mod_config 的默认值：整行都等于默认值，说明只是被建出来、没人改过
_MOD_DEFAULTS = (
    ("log_channel", 0),
    ("warn_kick_threshold", 0),
    ("warn_ban_threshold", 0),
    ("warn_mute_threshold", 3),
    ("warn_mute_duration", 600),
)


async def _table_names(db) -> set:
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        return {row[0] for row in await cur.fetchall()}


async def _has_row(db_name: str, table: str, guild_id: int) -> bool:
    """只读检查：库、表不存在都算没有；mod_config 只在偏离默认值时算有。"""
    path = storage.db_path(db_name)
    if not os.path.exists(path):  # 不要凭空建出空库
        return False
    try:
        async with aiosqlite.connect(path, timeout=_BUSY_TIMEOUT) as db:
            if table not in await _table_names(db):
                return False
            if table == "mod_config":
                columns = ", ".join(name for name, _ in _MOD_DEFAULTS)
                query = f"SELECT {columns} FROM mod_config WHERE guild_id=?"
            else:
                query = f"SELECT 1 FROM {table} WHERE guild_id=?"
            async with db.execute(query, (guild_id,)) as cur:
                row = await cur.fetchone()
    except (aiosqlite.Error, sqlite3.Error, OSError) as e:
        print(f"[guild_config] 读取 {db_name}.{table} 失败: {e!r}")
        return False
    if row is None:
        return False
    if table == "mod_config":
        return tuple(row) != tuple(default for _, default in _MOD_DEFAULTS)
    return True


async def has_config(guild_id: int) -> bool:
    """服务器是否已经有人配置过（任一配置表有行，或 mod_config 偏离默认值）。"""
    gid = int(guild_id)
    for db_name, table in CONFIG_TABLES + (("moderation", "mod_config"),):
        if await _has_row(db_name, table, gid):
            return True
    return False
