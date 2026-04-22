# cogs/commandtoggle.py
# RinBot — 指令开关模块 (指令管理)
# 功能：
#   • 管理员可按服务器禁用/启用任意指令
#   • Web 仪表盘和 /toggle 指令都能操作
#   • 全局 before_invoke 钩子自动拦截被禁用的指令
#   • 每 15 秒自动从 DB 刷新缓存，Web 修改即时生效

import discord
from discord.ext import commands, tasks
import aiosqlite

DB_PATH = "commandtoggle.db"

# 这些指令永远不能被禁用
PROTECTED_COMMANDS = {
    "toggle", "togglelist", "hot_update", "sync",
    "load", "unload", "extensions", "eval", "help",
}


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

        await self._refresh_cache()

        if not self.refresh_loop.is_running():
            self.refresh_loop.start()

        print("✅ 指令管理模块已准备就绪！")

    def cog_unload(self):
        self.refresh_loop.cancel()
        self.bot._before_invoke = None

    # ── 缓存刷新 ──

    async def _refresh_cache(self):
        """从 DB 重建缓存"""
        new_cache: dict[int, set[str]] = {}
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute("SELECT guild_id, command_name FROM disabled_commands")
                rows = await cursor.fetchall()
                for gid, cmd in rows:
                    if gid not in new_cache:
                        new_cache[gid] = set()
                    new_cache[gid].add(cmd)
        except Exception as e:
            print(f"[CommandToggle] refresh error: {e}")
            return
        self._disabled = new_cache

    @tasks.loop(seconds=15)
    async def refresh_loop(self):
        """每 15 秒刷新一次缓存，让 Web 修改即时生效"""
        await self._refresh_cache()

    @refresh_loop.before_loop
    async def before_refresh(self):
        await self.bot.wait_until_ready()

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
                    (guild_id, command_name))
                self._disabled.get(guild_id, set()).discard(command_name)
            else:
                await db.execute(
                    "INSERT OR IGNORE INTO disabled_commands (guild_id, command_name) VALUES (?, ?)",
                    (guild_id, command_name))
                if guild_id not in self._disabled:
                    self._disabled[guild_id] = set()
                self._disabled[guild_id].add(command_name)
            await db.commit()

    # ── Discord 指令 ──

    @commands.hybrid_command(name="toggle", description="[管理] 启用/禁用指定指令")
    @commands.has_permissions(manage_guild=True)
    async def toggle_cmd(self, ctx, command_name: str):
        """command_name: 要切换的指令名 (如 play, kick, roll)"""
        if command_name in PROTECTED_COMMANDS:
            await ctx.send(f"⚠️ `{command_name}` 是核心指令，不能被禁用。", ephemeral=True)
            return

        cmd = self.bot.get_command(command_name)
        if not cmd:
            await ctx.send(f"❌ 找不到指令 `{command_name}`。", ephemeral=True)
            return

        currently_disabled = self.is_disabled(ctx.guild.id, command_name)
        await self.set_command(ctx.guild.id, command_name, enabled=currently_disabled)

        if currently_disabled:
            await ctx.send(f"✅ `/{command_name}` 已**启用**。", ephemeral=True)
        else:
            await ctx.send(f"⏹ `/{command_name}` 已**禁用**。", ephemeral=True)

    @commands.hybrid_command(name="togglelist", description="[管理] 查看所有已禁用的指令")
    @commands.has_permissions(manage_guild=True)
    async def toggle_list(self, ctx):
        disabled = self._disabled.get(ctx.guild.id, set())
        if not disabled:
            await ctx.send("✅ 当前所有指令都处于启用状态。", ephemeral=True)
            return

        lines = [f"⏹ `/{cmd}`" for cmd in sorted(disabled)]
        embed = discord.Embed(
            title="🔒 已禁用的指令",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"共 {len(disabled)} 个指令被禁用 | 使用 /toggle <指令名> 恢复")
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(CommandToggle(bot))