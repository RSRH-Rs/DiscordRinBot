# cogs/musicconfig.py
# 音乐配置 — DJ 身份组 / 通知频道。启动时全量加载到内存，网页保存后经变更日志（music）按服务器重载。

import aiosqlite
import os
from discord.ext import commands

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "musicconfig.db"
)


class MusicConfig(commands.Cog):
    """音乐配置 — 存储 DJ 身份组和通知频道"""

    def __init__(self, bot):
        self.bot = bot
        # 缓存: {guild_id: {"dj_role": int, "notify_channel": int}}
        self._cache: dict[int, dict] = {}

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS music_config (
                guild_id INTEGER PRIMARY KEY,
                dj_role INTEGER DEFAULT 0,
                notify_channel INTEGER DEFAULT 0
            )""")
            await db.commit()
            cursor = await db.execute(
                "SELECT guild_id, dj_role, notify_channel FROM music_config"
            )
            self._cache = {
                gid: {"dj_role": dj, "notify_channel": nc}
                for gid, dj, nc in await cursor.fetchall()
            }
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("music", self.reload_guild)
        print("✅ 音乐配置模块已准备就绪！")

    def cog_unload(self):
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("music", self.reload_guild)

    async def reload_guild(self, guild_id: int):
        """网页保存后由变更日志回调：只重读该服务器的一行配置"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT dj_role, notify_channel FROM music_config WHERE guild_id=?",
                (guild_id,),
            )
            row = await cursor.fetchone()
        if row:
            self._cache[guild_id] = {"dj_role": row[0], "notify_channel": row[1]}
        else:
            self._cache.pop(guild_id, None)

    def get_config(self, guild_id: int) -> dict:
        # 读内存；未配置的服务器返回默认值
        row = self._cache.get(guild_id)
        if row:
            return dict(row)
        return {"dj_role": 0, "notify_channel": 0}

    async def set_config(
        self, guild_id: int, dj_role: int = 0, notify_channel: int = 0
    ):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO music_config (guild_id, dj_role, notify_channel) VALUES (?, ?, ?)",
                (guild_id, dj_role, notify_channel),
            )
            await db.commit()
        self._cache[guild_id] = {"dj_role": dj_role, "notify_channel": notify_channel}


async def setup(bot):
    await bot.add_cog(MusicConfig(bot))
