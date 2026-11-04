# cogs/globalsettings.py
# 执行网页「全局设置」里的：维护模式、黑名单、全局公告
# 与网站共享 globalsettings.db；维护/黑名单靠全局 check 拦截，公告由 bot 遍历服务器发送

import discord
from discord.ext import commands, tasks
import aiosqlite
import os
import time
from typing import NamedTuple

from _messages import block_notice, embed, send_notice

try:
    from config import OWNER_ID
except ImportError:
    OWNER_ID = 0

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "globalsettings.db"
)


class Block(NamedTuple):
    """拦截原因：blacklist（黑名单）/ maintenance（维护，text 为网页里填的说明）/ disabled（全局停用）"""

    kind: str
    text: str = ""


def decide_block(user_id, owner_id, blacklist, maintenance, maint_msg, disabled, command_name):
    """纯判定：None 放行，否则返回 Block。"""
    if user_id == owner_id:
        return None
    if user_id in blacklist:
        return Block("blacklist")
    if maintenance:
        return Block("maintenance", maint_msg or "")
    if command_name and command_name in disabled:
        return Block("disabled")
    return None


class GlobalSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_id = int(OWNER_ID or 0)
        self._maintenance = False
        self._maint_msg = ""
        self._blacklist = set()
        self._disabled_cmds = set()

    async def cog_load(self):
        await self._ensure_tables()
        await self._reload()
        self.bot.add_check(self._global_check)
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("global", self.reload_guild)
        if not self._tick.is_running():
            self._tick.start()

    def cog_unload(self):
        self.bot.remove_check(self._global_check)
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("global", self.reload_guild)
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
            await db.execute(
                "CREATE TABLE IF NOT EXISTS global_disabled_cmds (name TEXT PRIMARY KEY)"
            )
            await db.commit()

    async def _reload(self):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT key, value FROM global_flags WHERE key IN ('maintenance','maintenance_msg')"
            )
            flags = dict(await cur.fetchall())
            cur = await db.execute("SELECT user_id FROM blacklist")
            blacklist = {r[0] for r in await cur.fetchall()}
            cur = await db.execute("SELECT name FROM global_disabled_cmds")
            disabled = {r[0] for r in await cur.fetchall()}
        # 全部读完再赋值，避免缓存只更新一半
        self._maintenance = flags.get("maintenance") == "1"
        self._maint_msg = flags.get("maintenance_msg", "")
        self._blacklist = blacklist
        self._disabled_cmds = disabled

    async def reload_guild(self, guild_id: int = 0):
        # 全局设置：忽略参数，全量重载（只有几个标志与两张小表）
        await self._reload()

    def blocked_reason(self, user_id: int, command_name: str | None = None) -> Block | None:
        """None 放行，否则返回拦截原因 Block。"""
        return decide_block(
            user_id,
            self.owner_id,
            self._blacklist,
            self._maintenance,
            self._maint_msg,
            self._disabled_cmds,
            command_name,
        )

    # 全局拦截：黑名单静默拒绝；维护模式/全局禁用指令对非主人拒绝并提示
    async def _global_check(self, ctx):
        command_name = None
        if ctx.command is not None:
            command_name = ctx.command.qualified_name.split()[0]
        block = self.blocked_reason(ctx.author.id, command_name)
        if block is None:
            return True
        notice = block_notice(block)
        if notice:
            await send_notice(ctx, notice)
        return False

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
        # 处理待发送的公告（维护/黑名单缓存由 global 同步回调刷新）
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
            card = embed("info", "机器人主人的公告", message)
            sent = 0
            for guild in guilds:
                ch = self._pick_channel(guild)
                if ch:
                    try:
                        await ch.send(embed=card)
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
