"""机器人被移出服务器满 30 天后，自动删除该服务器存下的数据；30 天内重新邀请则全部保留。

待删记录在 guildcleanup.db 的 removed_guilds 表；cogs/guildcleanup.py 负责记录移出 / 重新加入，
并每天调用 reconcile() + purge_due() 一次。
全局表（blacklist / global_flags / broadcasts / global_disabled_cmds）不按服务器存，这里不碰。
"""
import os
import re
import sqlite3
import time
from typing import Dict, Iterable, List, Optional, Set

import aiosqlite

from rincore import storage, sync

RETENTION = 30 * 86400  # 秒：移出后保留多久

_BUSY_TIMEOUT = 5.0

WELCOME_UPLOAD_DIR = os.path.abspath(
    os.environ.get(
        "RINBOT_WELCOME_UPLOAD_DIR", os.path.join(storage.BOT_DIR, "uploads", "welcome")
    )
)
# 与 website/routes.py、cogs/welcome.py 的上传文件名规则一致：<guild_id>-<welcome|farewell>-<16位hex>.<后缀>
_WELCOME_IMAGE_NAME = re.compile(
    r"^(?P<gid>[1-9][0-9]*)-(?:welcome|farewell)-[0-9a-f]{16}(?:\.png|\.jpg|\.gif|\.webp)$"
)

_CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS removed_guilds ("
    "guild_id INTEGER PRIMARY KEY, "
    "removed_at REAL NOT NULL)"
)

# 直接按 guild_id 删的表：(库名, 表名)
GUILD_TABLES = (
    ("leveling", "users"),
    ("leveling", "level_config"),
    ("moderation", "warnings"),
    ("moderation", "mod_cases"),
    ("moderation", "mod_config"),
    ("moderation", "tempbans"),
    ("music", "saved_queues"),
    ("musicconfig", "music_config"),
    ("reactionroles", "rr_panels"),
    ("welcome", "welcome_config"),
    ("automod", "automod_config"),
    ("serverlog", "serverlog_config"),
    ("botlog", "botlog_config"),
    ("commandtoggle", "disabled_commands"),
)

# 抽奖的参与 / 中奖记录没有 guild_id，要先按该服务器的抽奖 id 删，再删抽奖本身
_GIVEAWAY_IDS = "SELECT id FROM giveaways WHERE guild_id=?"
_GIVEAWAY_STATEMENTS = (
    ("giveaway_entries", f"DELETE FROM giveaway_entries WHERE giveaway_id IN ({_GIVEAWAY_IDS})"),
    ("giveaway_winners", f"DELETE FROM giveaway_winners WHERE giveaway_id IN ({_GIVEAWAY_IDS})"),
    ("giveaways", "DELETE FROM giveaways WHERE guild_id=?"),
)

# 每组 (库名, 主表, [(表名, DELETE 语句)])：主表带 guild_id 列，不存在就整组跳过；
# 一组在一个事务里删完，失败只回滚这一组，其他组照常删
_GROUPS = tuple(
    (db, table, ((table, f"DELETE FROM {table} WHERE guild_id=?"),))
    for db, table in GUILD_TABLES
) + (("giveaway", "giveaways", _GIVEAWAY_STATEMENTS),)


def _pending_path() -> str:
    return storage.db_path("guildcleanup")


async def mark_removed(guild_id: int, *, now: Optional[float] = None) -> None:
    """记录机器人被移出服务器的时间；已有记录则保留最早的那次。"""
    now = time.time() if now is None else now
    async with aiosqlite.connect(_pending_path(), timeout=_BUSY_TIMEOUT) as db:
        await db.execute(_CREATE_SQL)
        await db.execute(
            "INSERT OR IGNORE INTO removed_guilds (guild_id, removed_at) VALUES (?, ?)",
            (int(guild_id), now),
        )
        await db.commit()


async def clear_removed(guild_id: int) -> None:
    """机器人回到服务器（或数据已删完）：去掉待删记录。"""
    async with aiosqlite.connect(_pending_path(), timeout=_BUSY_TIMEOUT) as db:
        await db.execute(_CREATE_SQL)
        await db.execute("DELETE FROM removed_guilds WHERE guild_id=?", (int(guild_id),))
        await db.commit()


async def pending() -> Dict[int, float]:
    """全部待删记录：{guild_id: 移出时间}。"""
    async with aiosqlite.connect(_pending_path(), timeout=_BUSY_TIMEOUT) as db:
        await db.execute(_CREATE_SQL)
        async with db.execute("SELECT guild_id, removed_at FROM removed_guilds") as cur:
            return {int(gid): float(at) for gid, at in await cur.fetchall()}


async def _table_names(db) -> Set[str]:
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        return {row[0] for row in await cur.fetchall()}


async def _stored_guild_ids() -> Set[int]:
    """各表里出现过的服务器 id（读不到的库 / 表跳过）。"""
    ids: Set[int] = set()
    for db_name, table, _ in _GROUPS:
        path = storage.db_path(db_name)
        if not os.path.exists(path):  # 不要凭空建出空库
            continue
        try:
            async with aiosqlite.connect(path, timeout=_BUSY_TIMEOUT) as db:
                if table not in await _table_names(db):
                    continue
                async with db.execute(
                    f"SELECT DISTINCT guild_id FROM {table} WHERE guild_id > 0"
                ) as cur:
                    ids.update(int(row[0]) for row in await cur.fetchall())
        except (aiosqlite.Error, sqlite3.Error, OSError) as e:
            print(f"[guild_cleanup] 读取 {db_name}.{table} 失败: {e!r}")
    return ids


async def reconcile(current_ids: Iterable[int], *, now: Optional[float] = None) -> None:
    """按机器人现在所在的服务器校正待删记录，补上离线期间错过的移出 / 重新邀请事件。

    在 current_ids 里的服务器去掉待删记录；表里有数据、机器人却不在的服务器从现在开始计时
    （已有记录的保留原来的时间）。current_ids 为空多半是还没连上，什么都不做。
    """
    current = {int(g) for g in current_ids}
    if not current:
        return
    now = time.time() if now is None else now
    missing = await _stored_guild_ids() - current
    async with aiosqlite.connect(_pending_path(), timeout=_BUSY_TIMEOUT) as db:
        await db.execute(_CREATE_SQL)
        async with db.execute("SELECT guild_id FROM removed_guilds") as cur:
            back = [int(row[0]) for row in await cur.fetchall() if int(row[0]) in current]
        await db.executemany("DELETE FROM removed_guilds WHERE guild_id=?", [(g,) for g in back])
        await db.executemany(
            "INSERT OR IGNORE INTO removed_guilds (guild_id, removed_at) VALUES (?, ?)",
            [(g, now) for g in sorted(missing)],
        )
        await db.commit()


def _remove_welcome_images(guild_id: int) -> bool:
    """删掉该服务器上传的欢迎 / 道别图片；全部删掉（或本来就没有）返回 True。"""
    try:
        entries = list(os.scandir(WELCOME_UPLOAD_DIR))
    except FileNotFoundError:
        return True
    except OSError as e:
        print(f"[guild_cleanup] 读取欢迎图片目录失败: {e!r}")
        return False
    ok = True
    for entry in entries:
        match = _WELCOME_IMAGE_NAME.fullmatch(entry.name)
        if not match or int(match.group("gid")) != guild_id:
            continue
        try:
            if entry.is_file(follow_symlinks=False):
                os.remove(entry.path)
        except FileNotFoundError:
            pass
        except OSError as e:
            ok = False
            print(f"[guild_cleanup] 删除欢迎图片 {entry.name} 失败: {e!r}")
    return ok


async def purge_guild(guild_id: int) -> bool:
    """删除一个服务器在各表里的数据和上传的图片；全部成功返回 True。

    一张表失败只记日志，其他表照删；之后通知各模块丢掉这个服务器的内存缓存。
    """
    guild_id = int(guild_id)
    ok = True
    for db_name, main_table, statements in _GROUPS:
        path = storage.db_path(db_name)
        if not os.path.exists(path):
            continue
        table = main_table
        try:
            async with aiosqlite.connect(path, timeout=_BUSY_TIMEOUT) as db:
                tables = await _table_names(db)
                if main_table not in tables:
                    continue
                for table, sql in statements:
                    if table in tables:
                        await db.execute(sql, (guild_id,))
                await db.commit()  # 出错时不提交，连接关闭即回滚这一组
        except (aiosqlite.Error, sqlite3.Error, OSError) as e:
            ok = False
            print(f"[guild_cleanup] 删除服务器 {guild_id} 的 {db_name}.{table} 失败: {e!r}")
    if not _remove_welcome_images(guild_id):
        ok = False
    for module in sync.MODULES:
        if module == "global":
            continue
        try:
            await sync.notify(module, guild_id)
        except (aiosqlite.Error, sqlite3.Error, OSError) as e:
            print(f"[guild_cleanup] 通知 {module} 重载服务器 {guild_id} 失败: {e!r}")
    return ok


async def purge_due(*, now: Optional[float] = None) -> List[int]:
    """删除移出满 RETENTION 的服务器的数据，返回删干净的服务器 id。

    没删干净的保留待删记录，下次再试（删除可以重复执行）。
    """
    now = time.time() if now is None else now
    cutoff = now - RETENTION
    due = sorted(gid for gid, removed_at in (await pending()).items() if removed_at <= cutoff)
    purged = []
    for guild_id in due:
        if await purge_guild(guild_id):
            await clear_removed(guild_id)
            purged.append(guild_id)
            print(f"[guild_cleanup] 已删除服务器 {guild_id} 的数据（移出已满 30 天）")
    return purged
