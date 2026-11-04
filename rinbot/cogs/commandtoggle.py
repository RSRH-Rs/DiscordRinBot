# cogs/commandtoggle.py
# RinBot — 指令开关模块 (指令管理)
# 功能：
#   • 管理员可按服务器禁用/启用任意指令
#   • Web 仪表盘和 /commands 指令都能操作
#   • 全局 before_invoke 钩子自动拦截被禁用的指令
#   • Web 修改后经变更日志回调重载该服务器缓存，即时生效

import discord
from discord.ext import commands
import aiosqlite
import os

from _botlog_helper import audit
from _perms import require
from _messages import Notice, embed, send_notice
from _inputs import choices
from _perms import is_owner_only
from rincore import command_i18n
from discord import app_commands
from rincore import legacy

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "commandtoggle.db",
)

# 这些指令永远不能被停用（和控制台共用一份）
from rincore.command_list import PROTECTED_COMMANDS  # noqa: E402


async def migrate_rows(db) -> None:
    """停用记录里的旧指令名换成新名字（幂等，每次加载跑一遍也没关系）。"""
    cur = await db.execute("SELECT guild_id, command_name FROM disabled_commands")
    by_guild: dict[int, set[str]] = {}
    for guild_id, name in await cur.fetchall():
        by_guild.setdefault(guild_id, set()).add(name)
    for guild_id, names in by_guild.items():
        migrated = legacy.migrate_disabled(names)
        if migrated != names:
            await db.execute("DELETE FROM disabled_commands WHERE guild_id = ?", (guild_id,))
            await db.executemany(
                "INSERT INTO disabled_commands (guild_id, command_name) VALUES (?, ?)",
                [(guild_id, name) for name in sorted(migrated)],
            )
    await db.commit()


class CommandToggle(commands.Cog):
    """指令管理 — 按服务器启用/禁用指令"""

    def __init__(self, bot):
        self.bot = bot
        # 缓存: {guild_id: set(disabled_command_names)}
        self._disabled: dict[int, set[str]] = {}
        # 注册全局 before_invoke 钩子
        self.bot.before_invoke(self._check_command_enabled)

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS disabled_commands (
                guild_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                PRIMARY KEY (guild_id, command_name)
            )""")
            await db.commit()
            try:
                await migrate_rows(db)
            except Exception as e:
                print(f"[CommandToggle] 停用记录迁移失败，下次加载再试: {e}")

        await self._refresh_cache()

        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("commands", self.reload_guild)

        print("✅ 指令管理模块已准备就绪！")

    def cog_unload(self):
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("commands", self.reload_guild)
        self.bot._before_invoke = None

    # ── 缓存刷新 ──

    async def _refresh_cache(self):
        """从 DB 重建缓存"""
        new_cache: dict[int, set[str]] = {}
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT guild_id, command_name FROM disabled_commands"
                )
                rows = await cursor.fetchall()
                for gid, cmd in rows:
                    if gid not in new_cache:
                        new_cache[gid] = set()
                    new_cache[gid].add(cmd)
        except Exception as e:
            print(f"[CommandToggle] refresh error: {e}")
            return
        self._disabled = new_cache

    async def reload_guild(self, guild_id: int):
        """Web 修改后由变更日志回调：只重载该服务器的禁用指令集合"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT command_name FROM disabled_commands WHERE guild_id = ?",
                (guild_id,),
            )
            names = {r[0] for r in await cursor.fetchall()}
        if names:
            self._disabled[guild_id] = names
        else:
            self._disabled.pop(guild_id, None)

    # ── 拦截钩子 ──

    def is_disabled(self, guild_id: int, command_name: str) -> bool:
        return command_name in self._disabled.get(guild_id, set())

    async def _check_command_enabled(self, ctx):
        """全局 before_invoke — 被禁用的指令不会执行"""
        if not ctx.guild:
            return
        cmd_name = ctx.command.qualified_name.split()[0]
        if cmd_name in PROTECTED_COMMANDS:
            return
        if self.is_disabled(ctx.guild.id, cmd_name):
            await ctx.send(
                f"❌ `/{cmd_name}` 已被管理员在本服务器禁用。",
                ephemeral=True,
            )
            raise commands.CheckFailure(f"Command {cmd_name} is disabled")

    # ── DB 写入 ──

    async def set_command(self, guild_id: int, command_name: str, enabled: bool):
        async with aiosqlite.connect(DB_PATH) as db:
            if enabled:
                await db.execute(
                    "DELETE FROM disabled_commands WHERE guild_id=? AND command_name=?",
                    (guild_id, command_name),
                )
                self._disabled.get(guild_id, set()).discard(command_name)
            else:
                await db.execute(
                    "INSERT OR IGNORE INTO disabled_commands (guild_id, command_name) VALUES (?, ?)",
                    (guild_id, command_name),
                )
                if guild_id not in self._disabled:
                    self._disabled[guild_id] = set()
                self._disabled[guild_id].add(command_name)
            await db.commit()

    # ── Discord 指令 ──

    async def _set(self, ctx, command: str, enabled: bool) -> None:
        words = command.strip().lstrip("/").split()
        if len(words) > 1:
            await send_notice(ctx, Notice("error", "只能停用整条指令", f"填 {words[0]} 会停用整个 /{words[0]}。"))
            return
        name = words[0] if words else ""
        if name in PROTECTED_COMMANDS:
            await send_notice(ctx, Notice("error", "这条指令不能停用"))
            return
        if not name or self.bot.get_command(name) is None:
            await send_notice(ctx, Notice("error", "找不到这条指令"))
            return
        await self.set_command(ctx.guild.id, name, enabled=enabled)
        await audit(
            self.bot,
            ctx.guild.id,
            f"{'启用' if enabled else '停用'}了指令",
            **{"操作者": ctx.author.mention, "指令": f"/{name}"},
        )
        if enabled:
            await ctx.send(f"✅ `/{name}` 已**启用**。", ephemeral=True)
        else:
            await ctx.send(f"⏹ `/{name}` 已**停用**。", ephemeral=True)

    @commands.hybrid_group(name="commands", description="Turn commands on or off for this server")
    @commands.guild_only()
    @require(manage_guild=True)
    async def commands_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("用法：`r!commands disable <指令>`、`r!commands enable <指令>`、`r!commands list`")

    @commands_group.command(name="disable", description="Turn a command off for this server")
    @app_commands.describe(command="The command to turn off; pick from the list")
    @commands.guild_only()
    @require(manage_guild=True)
    async def commands_disable(self, ctx, command: str):
        await self._set(ctx, command, enabled=False)

    @commands_group.command(name="enable", description="Turn a command back on")
    @app_commands.describe(command="The command to turn on; pick from the list")
    @commands.guild_only()
    @require(manage_guild=True)
    async def commands_enable(self, ctx, command: str):
        await self._set(ctx, command, enabled=True)

    @commands_group.command(name="toggle", with_app_command=False, hidden=True)
    @commands.guild_only()
    @require(manage_guild=True)
    async def commands_toggle(self, ctx, command: str):
        """旧的 r!toggle：停用和启用来回切换"""
        name = command.strip().lstrip("/").split()[0] if command.strip() else ""
        await self._set(ctx, command, enabled=self.is_disabled(ctx.guild.id, name))

    @commands_group.command(name="list", description="Show the commands turned off here")
    @commands.guild_only()
    @require(manage_guild=True)
    async def commands_list(self, ctx):
        disabled = self._disabled.get(ctx.guild.id, set())
        if not disabled:
            await ctx.send("✅ 当前所有指令都处于启用状态。", ephemeral=True)
            return

        lines = [f"⏹ `/{cmd}`" for cmd in sorted(disabled)]
        card = embed(
            "info",
            "已停用的指令",
            "\n".join(lines),
            footer=f"共 {len(disabled)} 个指令被禁用 | 使用 /commands enable <指令> 恢复",
        )
        await ctx.send(embed=card, ephemeral=True)

    @commands_disable.autocomplete("command")
    async def _disable_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        disabled = self._disabled.get(interaction.guild.id, set())
        items = []
        for cmd in sorted(self.bot.commands, key=lambda c: c.name):
            if cmd.hidden or cmd.name in PROTECTED_COMMANDS or cmd.name in disabled or is_owner_only(cmd):
                continue
            if getattr(cmd, "app_command", None) is None:
                continue
            text = command_i18n.zh_description(cmd.name) or cmd.description
            items.append((f"{cmd.name} {text[:50]}", cmd.name))
        return choices(items, current)

    @commands_enable.autocomplete("command")
    async def _enable_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        items = []
        for name in sorted(self._disabled.get(interaction.guild.id, set())):
            text = command_i18n.zh_description(name) or ""
            items.append((f"{name} {text[:50]}".strip(), name))
        return choices(items, current)

async def setup(bot):
    await bot.add_cog(CommandToggle(bot))
