# cogs/musicconfig.py
# 音乐配置 — DJ 身份组 / 通知频道。按需直接读 DB（无缓存、无轮询），网页改完即时生效。

import sqlite3
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

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS music_config (
                guild_id INTEGER PRIMARY KEY,
                dj_role INTEGER DEFAULT 0,
                notify_channel INTEGER DEFAULT 0
            )""")
            await db.commit()
        print("✅ 音乐配置模块已准备就绪！")

    def get_config(self, guild_id: int) -> dict:
        # 单行主键查询，亚毫秒级；直接读保证网页改动即时生效
        try:
            con = sqlite3.connect(DB_PATH, timeout=2)
            row = con.execute(
                "SELECT dj_role, notify_channel FROM music_config WHERE guild_id=?",
                (guild_id,),
            ).fetchone()
            con.close()
        except Exception:
            row = None
        if row:
            return {"dj_role": row[0], "notify_channel": row[1]}
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


async def setup(bot):
    await bot.add_cog(MusicConfig(bot))
