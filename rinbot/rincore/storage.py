"""RinBot 共享存储：数据库路径表 + SQLite WAL 开关（bot 与网站面板共用）。"""
import os
from typing import Iterable, Optional

import aiosqlite

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
    }.items()
}


def db_path(name: str) -> str:
    """按名字取数据库的绝对路径。"""
    return DB_FILES[name]


async def enable_wal(paths: Optional[Iterable[str]] = None) -> None:
    """为数据库开启 WAL（默认全部 DB_FILES；文件不存在会被创建）。

    journal_mode=WAL 写入库文件本身且幂等，bot 与网站进程同时调用也安全。
    """
    for path in (DB_FILES.values() if paths is None else paths):
        async with aiosqlite.connect(path, timeout=30) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.commit()
