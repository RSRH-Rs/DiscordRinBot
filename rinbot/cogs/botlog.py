# cogs/botlog.py
# RinBot — 系统日志模块

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import traceback
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

try:
    from config import DEV_GUILD_ID
except ImportError:
    DEV_GUILD_ID = 0

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botlog.db"
)

LEVEL_META = {
    "error": {"emoji": "❌", "color": 0xE24B4A, "label": "错误"},
    "warning": {"emoji": "⚠️", "color": 0xEF9F27, "label": "警告"},
    "info": {"emoji": "ℹ️", "color": 0x85B7EB, "label": "信息"},
    "config": {"emoji": "⚙️", "color": 0x5A9E6F, "label": "配置变更"},
}


def new_error_id() -> str:
    """8 位大写十六进制错误编号，用户与日志据此对应"""
    return uuid.uuid4().hex[:8].upper()


class BotLog(commands.Cog):
    """系统日志 — 将 bot 内部活动转发到指定频道"""

    def __init__(self, bot):
        self.bot = bot
        # 缓存: {guild_id: {"channel_id": int, "enabled": bool, "levels": set[str]}}
        self._cache: dict[int, dict] = {}

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS botlog_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                levels TEXT DEFAULT 'error,warning,info,config'
            )""")
            await db.commit()
        await self._reload()
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("botlog", self.reload_guild)
        print("✅ 系统日志模块已准备就绪!")

    def cog_unload(self):
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("botlog", self.reload_guild)

    async def _reload(self):
        """从 DB 重新载入配置缓存（让网页改动无需重启即可生效）"""
        cache = {}
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT guild_id, channel_id, enabled, levels FROM botlog_config"
            )
            for row in await cursor.fetchall():
                cache[row[0]] = {
                    "channel_id": row[1],
                    "enabled": bool(row[2]),
                    "levels": set(row[3].split(",")) if row[3] else set(),
                }
        self._cache = cache

    async def reload_guild(self, guild_id: int):
        """网页保存后由变更日志回调：只重读该服务器的一行配置"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT channel_id, enabled, levels FROM botlog_config WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cursor.fetchone()
        if row:
            self._cache[guild_id] = {
                "channel_id": row[0],
                "enabled": bool(row[1]),
                "levels": set(row[2].split(",")) if row[2] else set(),
            }
        else:
            self._cache.pop(guild_id, None)

    # ─── 配置 ───

    def get_config(self, guild_id: int) -> dict:
        return self._cache.get(
            guild_id,
            {
                "channel_id": 0,
                "enabled": False,
                "levels": set(),
            },
        )

    async def set_config(
        self, guild_id: int, channel_id: int, enabled: bool, levels: list[str]
    ):
        levels_str = ",".join(sorted(set(levels) & set(LEVEL_META.keys())))
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO botlog_config (guild_id, channel_id, enabled, levels) VALUES (?, ?, ?, ?)",
                (guild_id, channel_id, int(enabled), levels_str),
            )
            await db.commit()
        self._cache[guild_id] = {
            "channel_id": channel_id,
            "enabled": enabled,
            "levels": set(levels_str.split(",")) if levels_str else set(),
        }

    # ─── 核心 API ───

    async def log(
        self, guild_id: int, level: str, title: str, description: str = "", **fields
    ):
        """供任何 cog / routes 调用"""
        cfg = self.get_config(guild_id)
        if not cfg["enabled"] or not cfg["channel_id"]:
            return
        if level not in cfg["levels"]:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(cfg["channel_id"])
        if not channel:
            return

        meta = LEVEL_META.get(level, LEVEL_META["info"])
        embed = discord.Embed(
            title=f"{meta['emoji']} {title}",
            description=description[:4000] if description else None,
            color=meta["color"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"系统日志 · {meta['label']}")
        for k, v in fields.items():
            if v is None or v == "":
                continue
            embed.add_field(name=k, value=str(v)[:1000], inline=True)
        embed.set_footer(text=f"Guild ID: {guild_id}")

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def report_exception(
        self, guild_id: Optional[int], title: str, exc: BaseException, **fields
    ) -> str:
        """上报未预期的异常，返回错误编号。永远不会抛出异常（供错误处理器调用）。

        完整 traceback 只发到开发服务器(DEV_GUILD_ID)的 bot 日志并打印到 journal；
        来源服务器的日志只收到不含 traceback 的“出错了（错误编号）”条目。
        同一个异常对象只上报一次，重复调用返回同一个编号。
        """
        existing = getattr(exc, "_rinbot_error_id", None)
        if existing:
            return existing
        error_id = new_error_id()
        try:
            exc._rinbot_error_id = error_id
        except Exception:
            pass
        try:
            tb = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        except Exception:
            tb = repr(exc)
        print(f"[error {error_id}] {title} (guild {guild_id})\n{tb}")

        if DEV_GUILD_ID:
            try:
                await self.log(
                    DEV_GUILD_ID,
                    "error",
                    f"{title}（错误编号 {error_id}）",
                    f"```py\n{tb[-1500:]}\n```",
                    **{"来源服务器": guild_id if guild_id is not None else "私信"},
                    **fields,
                )
            except Exception:
                pass
        if guild_id is not None and guild_id != DEV_GUILD_ID:
            try:
                await self.log(
                    guild_id,
                    "error",
                    f"出错了（错误编号 {error_id}）",
                    title,
                    **fields,
                )
            except Exception:
                pass
        return error_id

    # ─── 全局命令错误监听 ───

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # 忽略一些预期错误
        if isinstance(
            error,
            (
                commands.CommandNotFound,
                commands.CheckFailure,
                commands.MissingPermissions,
                commands.MissingRequiredArgument,
                commands.BadArgument,
                commands.UserInputError,
                commands.CommandOnCooldown,
            ),
        ):
            return
        cmd = ctx.command.qualified_name if ctx.command else "未知指令"
        original = error
        while getattr(original, "original", None) is not None:
            original = original.original
        await self.report_exception(
            ctx.guild.id if ctx.guild else None,
            f"指令执行失败: /{cmd}",
            original,
            **{
                "用户": ctx.author.mention,
                "频道": getattr(ctx.channel, "mention", "私信"),
            },
        )


async def setup(bot):
    await bot.add_cog(BotLog(bot))
