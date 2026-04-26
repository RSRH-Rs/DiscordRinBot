import aiosqlite
from discord.ext import commands

DB_PATH = "musicconfig.db"


class MusicConfig(commands.Cog):
    """音乐配置 — 存储 DJ 身份组和通知频道"""

    def __init__(self, bot):
        self.bot = bot
        # 缓存: {guild_id: {"dj_role": int, "notify_channel": int}}
        self._cache: dict[int, dict] = {}

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS music_config (
                guild_id INTEGER PRIMARY KEY,
                dj_role INTEGER DEFAULT 0,
                notify_channel INTEGER DEFAULT 0
            )"""
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT guild_id, dj_role, notify_channel FROM music_config"
            )
            for row in await cursor.fetchall():
                self._cache[row[0]] = {"dj_role": row[1], "notify_channel": row[2]}

        print("✅ 音乐配置模块已准备就绪！")

    def get_config(self, guild_id: int) -> dict:
        return self._cache.get(guild_id, {"dj_role": 0, "notify_channel": 0})

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
