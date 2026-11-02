"""配置变更日志：网页面板保存设置后 notify()，bot 端 ChangeWatcher 轮询并回调各模块重载。

两个进程共用 sync.db；表由任一方 CREATE TABLE IF NOT EXISTS 创建，互不依赖启动顺序。
"""
import asyncio
import time
from typing import Awaitable, Callable, Dict, List, Optional

import aiosqlite

from rincore import storage

MODULES = (
    "welcome",
    "automod",
    "moderation",
    "music",
    "botlog",
    "serverlog",
    "reactionroles",
    "commands",
    "global",
)

_BUSY_TIMEOUT = 5.0  # 秒，与 sqlite3 默认一致
_PRUNE_INTERVAL = 3600.0  # 每小时清理一次旧记录

_CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS changes ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "module TEXT NOT NULL, "
    "guild_id INTEGER NOT NULL, "
    "created_at REAL NOT NULL)"
)

Callback = Callable[[int], Awaitable[None]]


def _resolve(path: Optional[str]) -> str:
    return path if path is not None else storage.db_path("sync")


async def notify(module: str, guild_id: int, *, path: Optional[str] = None) -> None:
    """记录一次配置变更（网页面板调用）。全局设置用 guild_id = 0。"""
    if module not in MODULES:
        raise ValueError(f"未知的同步模块: {module!r}")
    async with aiosqlite.connect(_resolve(path), timeout=_BUSY_TIMEOUT) as db:
        await db.execute(_CREATE_SQL)
        await db.execute(
            "INSERT INTO changes (module, guild_id, created_at) VALUES (?, ?, ?)",
            (module, int(guild_id), time.time()),
        )
        await db.commit()


class ChangeWatcher:
    """bot 端：轮询变更日志，按 (module, guild_id) 去重后调用已注册的重载回调。"""

    def __init__(
        self,
        path: Optional[str] = None,
        interval: float = 3.0,
        retention: float = 86400.0,
    ):
        self.path = _resolve(path)
        self.interval = interval
        self.retention = retention
        self._callbacks: Dict[str, List[Callback]] = {}
        self._cursor = 0
        self._task: Optional[asyncio.Task] = None

    def register(self, module: str, callback: Callback) -> None:
        self._callbacks.setdefault(module, []).append(callback)

    def unregister(self, module: str, callback: Callback) -> None:
        callbacks = self._callbacks.get(module)
        if callbacks and callback in callbacks:
            callbacks.remove(callback)

    async def start(self) -> None:
        """建表、把游标定在当前最大 id（各 cog 启动时已全量加载配置，无需回放）、启动后台轮询。"""
        if self._task is not None and not self._task.done():
            return
        async with aiosqlite.connect(self.path, timeout=_BUSY_TIMEOUT) as db:
            await db.execute(_CREATE_SQL)
            await db.commit()
            async with db.execute("SELECT COALESCE(MAX(id), 0) FROM changes") as cur:
                row = await cur.fetchone()
        self._cursor = row[0] if row else 0
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def poll_once(self) -> int:
        """处理一次新记录，返回分发的 (module, guild_id) 数。"""
        async with aiosqlite.connect(self.path, timeout=_BUSY_TIMEOUT) as db:
            async with db.execute(
                "SELECT id, module, guild_id FROM changes WHERE id > ? ORDER BY id",
                (self._cursor,),
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            return 0
        # 先推进游标：回调失败也不会重复处理同一批记录
        self._cursor = rows[-1][0]
        pairs = list(dict.fromkeys((module, guild_id) for _, module, guild_id in rows))
        for module, guild_id in pairs:
            for callback in list(self._callbacks.get(module, ())):
                try:
                    await callback(guild_id)
                except Exception as e:
                    print(f"[sync] {module} 重载回调出错 (guild {guild_id}): {e!r}")
        return len(pairs)

    async def prune(self, now: Optional[float] = None) -> int:
        """删除早于 retention 的记录，返回删除条数。"""
        cutoff = (time.time() if now is None else now) - self.retention
        async with aiosqlite.connect(self.path, timeout=_BUSY_TIMEOUT) as db:
            cur = await db.execute("DELETE FROM changes WHERE created_at < ?", (cutoff,))
            deleted = cur.rowcount
            await db.commit()
        return deleted

    async def _run(self) -> None:
        last_prune: Optional[float] = None
        while True:
            try:
                await self.poll_once()
                if last_prune is None or time.monotonic() - last_prune >= _PRUNE_INTERVAL:
                    last_prune = time.monotonic()
                    await self.prune()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[sync] 轮询出错: {e!r}")
            await asyncio.sleep(self.interval)
