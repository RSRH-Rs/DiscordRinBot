# cogs/globalsettings.py
# 执行网页「全局设置」里的：维护模式、黑名单、全局公告
# 与网站共享 globalsettings.db；维护/黑名单靠全局 check 拦截，公告由 bot 遍历服务器发送

import discord
from discord.ext import commands, tasks
import aiosqlite
import os
import time

try:
    from config import OWNER_ID
except ImportError:
    OWNER_ID = 0

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "globalsettings.db"
)


class GlobalSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_id = int(OWNER_ID or 0)
        self._maintenance = False
        self._maint_msg = ""
        self._blacklist = set()

    async def cog_load(self):
        await self._ensure_tables()
        await self._reload()
        self.bot.add_check(self._global_check)
        if not self._tick.is_running():
            self._tick.start()

    def cog_unload(self):
        self.bot.remove_check(self._global_check)
        self._tick.cancel()

    async def _ensure_tables(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS global_flags (key TEXT PRIMARY KEY, value TEXT DEFAULT '')"
            )
            await db.execute(
                "CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, reason TEXT DEFAULT '', added_at REAL DEFAULT 0)"
            )
            await db.execute(
                """CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL,
                status TEXT DEFAULT 'pending', sent_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0, created_at REAL DEFAULT 0, done_at REAL DEFAULT 0)"""
            )
            await db.commit()

    async def _reload(self):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT key, value FROM global_flags WHERE key IN ('maintenance','maintenance_msg')"
            )
            flags = dict(await cur.fetchall())
            self._maintenance = flags.get("maintenance") == "1"
            self._maint_msg = flags.get("maintenance_msg", "")
            cur = await db.execute("SELECT user_id FROM blacklist")
            self._blacklist = {r[0] for r in await cur.fetchall()}

    # 全局拦截：黑名单静默拒绝；维护模式对非主人拒绝并提示
    async def _global_check(self, ctx):
        uid = ctx.author.id
        if uid == self.owner_id:
            return True
        if uid in self._blacklist:
            return False
        if self._maintenance:
            try:
                await ctx.send(
                    self._maint_msg or "🔧 机器人维护中，请稍后再试 (｡•́︿•̀｡)",
                    ephemeral=True,
                )
            except Exception:
                pass
            return False
        return True

    def _pick_channel(self, guild):
        me = guild.me
        if me is None:
            return None
        sc = guild.system_channel
        if sc and sc.permissions_for(me).send_messages:
            return sc
        for ch in guild.text_channels:
            if ch.permissions_for(me).send_messages:
                return ch
        return None

    @tasks.loop(seconds=10)
    async def _tick(self):
        # 1) 刷新维护/黑名单缓存（让网页改动生效）
        try:
            await self._reload()
        except Exception as e:
            print(f"[globalsettings] reload 失败: {e}")
        # 2) 处理待发送的公告
        try:
            await self._process_broadcasts()
        except Exception as e:
            print(f"[globalsettings] 公告处理失败: {e}")

    async def _process_broadcasts(self):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT id, message FROM broadcasts WHERE status='pending' ORDER BY id ASC"
            )
            pending = await cur.fetchall()
        for bid, message in pending:
            guilds = list(self.bot.guilds)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE broadcasts SET status='sending', total_count=? WHERE id=?",
                    (len(guilds), bid),
                )
                await db.commit()
            embed = discord.Embed(
                title="📢 来自机器人主人的公告",
                description=message,
                color=0xF0607A,
            )
            embed.set_footer(text="小凛 RinBot")
            sent = 0
            for guild in guilds:
                ch = self._pick_channel(guild)
                if ch:
                    try:
                        await ch.send(embed=embed)
                        sent += 1
                    except Exception:
                        pass
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE broadcasts SET status='done', sent_count=?, done_at=? WHERE id=?",
                    (sent, time.time(), bid),
                )
                await db.commit()
            print(f"[globalsettings] 公告已发送：{sent}/{len(guilds)} 个服务器")

    @_tick.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GlobalSettings(bot))
