# cogs/botconfig.py
# RinBot — Bot 个性化模块
# 由网页仪表盘写入配置，Bot 定时读取并应用
# 功能：
#   • 自动应用状态 (online/idle/dnd)、活动类型、活动文字
#   • 头像和用户名通过 REST API 直接修改

import discord
from discord.ext import commands, tasks
import aiosqlite

DB_PATH = "botconfig.db"


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
        if not self.check_presence.is_running():
            self.check_presence.start()

    def cog_unload(self):
        self.check_presence.cancel()

    @tasks.loop(seconds=30)
    async def check_presence(self):
        """每 30 秒检查一次是否有新的配置"""
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
            print(f"[BotConfig] check_presence error: {e}")

    @check_presence.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(BotConfig(bot))