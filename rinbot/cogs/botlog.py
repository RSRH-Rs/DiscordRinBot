# cogs/botlog.py
# RinBot — 系统日志模块

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import traceback
from datetime import datetime, timezone
from typing import Optional

DB_PATH = "botlog.db"

LEVEL_META = {
    "error": {"emoji": "❌", "color": 0xE24B4A, "label": "错误"},
    "warning": {"emoji": "⚠️", "color": 0xEF9F27, "label": "警告"},
    "info": {"emoji": "ℹ️", "color": 0x85B7EB, "label": "信息"},
    "config": {"emoji": "⚙️", "color": 0x5A9E6F, "label": "配置变更"},
}


class BotLog(commands.Cog):
    """系统日志 — 将 bot 内部活动转发到指定频道"""

    def __init__(self, bot):
        self.bot = bot
        # 缓存: {guild_id: {"channel_id": int, "enabled": bool, "levels": set[str]}}
        self._cache: dict[int, dict] = {}
        # hook slash command 错误 handler,保存原 handler 以便链式调用
        self._original_tree_error = bot.tree.on_error
        bot.tree.on_error = self._on_app_command_error

    def cog_unload(self):
        # 还原原 handler,避免 cog reload 后引用残留
        try:
            self.bot.tree.on_error = self._original_tree_error
        except Exception:
            pass

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS botlog_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                levels TEXT DEFAULT 'error,warning,info,config'
            )""")
            await db.commit()

            cursor = await db.execute(
                "SELECT guild_id, channel_id, enabled, levels FROM botlog_config"
            )
            for row in await cursor.fetchall():
                self._cache[row[0]] = {
                    "channel_id": row[1],
                    "enabled": bool(row[2]),
                    "levels": set(row[3].split(",")) if row[3] else set(),
                }

        print("✅ 系统日志模块已准备就绪!")

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
            ),
        ):
            return
        if not ctx.guild:
            return
        cmd = ctx.command.qualified_name if ctx.command else "未知指令"
        tb = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        await self.log(
            ctx.guild.id,
            "error",
            f"指令执行失败: /{cmd}",
            f"```py\n{tb[-1500:]}\n```",
            **{"用户": ctx.author.mention, "频道": ctx.channel.mention},
        )

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """slash command 错误 — 替换默认 tree.on_error 接住所有 slash 异常"""
        # 解包 CommandInvokeError 拿到真正的底层异常
        original = getattr(error, "original", error)

        # 忽略预期错误(不污染日志)
        if isinstance(
            error,
            (
                app_commands.CommandNotFound,
                app_commands.MissingPermissions,
                app_commands.CheckFailure,
                app_commands.CommandOnCooldown,
            ),
        ):
            # 让原 handler 处理(通常是给用户回复一条提示)
            if self._original_tree_error:
                try:
                    await self._original_tree_error(interaction, error)
                except Exception:
                    pass
            return

        # 记录到 botlog 频道
        if interaction.guild:
            cmd = (
                interaction.command.qualified_name
                if interaction.command
                else "未知指令"
            )
            tb = "".join(
                traceback.format_exception(
                    type(original), original, original.__traceback__
                )
            )
            channel_mention = (
                interaction.channel.mention if interaction.channel else "私信"
            )
            await self.log(
                interaction.guild.id,
                "error",
                f"Slash 指令执行失败: /{cmd}",
                f"```py\n{tb[-1500:]}\n```",
                **{"用户": interaction.user.mention, "频道": channel_mention},
            )

        # 给用户一个反馈,避免 Discord 显示"应用未响应"
        try:
            msg = "❌ 执行指令时发生错误,管理员已收到通知。"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(BotLog(bot))
