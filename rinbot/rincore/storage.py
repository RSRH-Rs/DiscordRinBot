"""RinBot 共享存储：数据库路径表 + SQLite WAL 开关（bot 与网站面板共用）。"""
import asyncio
import os
import sqlite3
from typing import Iterable, Optional

import aiosqlite

# WAL 切换的重试参数：最坏情况每个库约 3*0.5 + 2*0.5 秒，不会拖住启动
_WAL_ATTEMPTS = 3
_WAL_RETRY_DELAY = 0.5
_WAL_TIMEOUT = 0.5

# rinbot/ 目录（rincore 的上一级），所有 .db 都放在这里
BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_FILES = {
    name: os.path.join(BOT_DIR, filename)
    for name, filename in {
        "welcome": "welcome.db",
        "automod": "automod.db",
        "moderation": "moderation.db",
        "giveaway": "giveaway.db",
        "leveling": "leveling.db",
        "botconfig": "botconfig.db",
        "reactionroles": "reactionroles.db",
        "commandtoggle": "commandtoggle.db",
        "musicconfig": "musicconfig.db",
        "botlog": "botlog.db",
        "serverlog": "serverlog.db",
        "globalsettings": "globalsettings.db",
        "music": "music.db",
        "sync": "sync.db",
        "guildcleanup": "guildcleanup.db",
    }.items()
}


def db_path(name: str) -> str:
    """按名字取数据库的绝对路径。"""
    return DB_FILES[name]


async def _enable_wal_one(path: str) -> None:
    """对单个库尝试开启 WAL；失败只打印日志，绝不抛出。"""
    last = None
    for attempt in range(_WAL_ATTEMPTS):
        if attempt:
            await asyncio.sleep(_WAL_RETRY_DELAY)
        try:
            async with aiosqlite.connect(path, timeout=_WAL_TIMEOUT) as db:
                async with db.execute("PRAGMA journal_mode=WAL") as cur:
                    row = await cur.fetchone()
                await db.commit()
            mode = str(row[0]).lower() if row else ""
            if mode == "wal":
                return
            last = f"journal_mode={mode or '?'}"  # 拿不到锁时 SQLite 会静默保持原模式
        except (aiosqlite.Error, sqlite3.Error, OSError) as e:
            last = repr(e)
    print(f"[storage] 无法为 {os.path.basename(path)} 开启 WAL: {last}")


async def enable_wal(paths: Optional[Iterable[str]] = None) -> None:
    """为数据库开启 WAL（默认全部 DB_FILES；文件不存在会被创建）。

    journal_mode=WAL 写入库文件本身且幂等，bot 与网站进程同时调用也安全。
    单个库失败（如被另一进程锁住）会重试几次后记录日志并继续，本函数不会抛异常。
    """
    for path in (DB_FILES.values() if paths is None else paths):
        await _enable_wal_one(path)
