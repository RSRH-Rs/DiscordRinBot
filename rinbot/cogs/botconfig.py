# cogs/botconfig.py
# RinBot — Bot 个性化模块
# 由网页仪表盘写入配置，经变更日志（global）通知后 Bot 读取并应用
# 功能：
#   • 自动应用状态 (online/idle/dnd)、活动类型、活动文字
#   • 头像和用户名通过 REST API 直接修改

import discord
from discord.ext import commands
import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botconfig.db")


class BotConfig(commands.Cog):
    """Bot 个性化 — 从数据库读取配置并应用"""

    def __init__(self, bot):
        self.bot = bot
        self._last_hash = None

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS bot_personalizer (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                bot_status TEXT DEFAULT 'online',
                activity_type TEXT DEFAULT 'watching',
                activity_text TEXT DEFAULT '正在偷看你的聊天记录|rin-bot.com',
                updated_at REAL DEFAULT 0
            )""")
            await db.execute(
                "INSERT OR IGNORE INTO bot_personalizer (id) VALUES (1)")
            await db.commit()
        print("✅ Bot 个性化模块已准备就绪！")
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("global", self.reload_guild)
        # bot 已就绪（热加载）则立即应用；否则由 on_ready 监听器应用
        if self.bot.is_ready():
            await self.apply_presence()

    def cog_unload(self):
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("global", self.reload_guild)

    @commands.Cog.listener()
    async def on_ready(self):
        # main.py 的 on_ready 每次(重)连都会写入默认状态，需强制重新应用面板配置
        self._last_hash = None
        await self.apply_presence()

    async def reload_guild(self, guild_id: int = 0):
        # 全局设置：忽略参数，重读 bot_personalizer 一行（hash 比对避免重复调用 API）
        await self.apply_presence()

    async def apply_presence(self):
        """读取 bot_personalizer 并应用在线状态/活动"""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("SELECT * FROM bot_personalizer WHERE id=1")
                row = await cur.fetchone()

            if not row:
                return

            # 用 updated_at 做变更检测，避免每次都调 API
            h = f"{row['bot_status']}|{row['activity_type']}|{row['activity_text']}|{row['updated_at']}"
            if h == self._last_hash:
                return
            self._last_hash = h

            # 解析状态
            status_map = {
                "online": discord.Status.online,
                "idle": discord.Status.idle,
                "dnd": discord.Status.dnd,
                "invisible": discord.Status.invisible,
            }
            status = status_map.get(row["bot_status"], discord.Status.online)

            # 解析活动
            activity = None
            atype = row["activity_type"]
            atext = row["activity_text"] or ""

            if atype == "playing":
                activity = discord.Game(name=atext)
            elif atype == "watching":
                activity = discord.Activity(type=discord.ActivityType.watching, name=atext)
            elif atype == "listening":
                activity = discord.Activity(type=discord.ActivityType.listening, name=atext)
            elif atype == "competing":
                activity = discord.Activity(type=discord.ActivityType.competing, name=atext)
            elif atype == "custom":
                activity = discord.CustomActivity(name=atext)
            elif atype == "none":
                activity = None

            await self.bot.change_presence(status=status, activity=activity)

        except Exception as e:
            print(f"[BotConfig] apply_presence error: {e}")


async def setup(bot):
    await bot.add_cog(BotConfig(bot))