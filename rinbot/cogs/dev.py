# cogs/dev.py
# RinBot — Developer & Hot-Reload Module
# 功能：
#   • /hot_update [cog] [sync_scope] — 热更新代码 + 可选同步指令
#   • /load   <cog>      — 加载新 cog
#   • /unload <cog>      — 卸载 cog
#   • /extensions        — 查看所有扩展状态
#   • /sync  [scope]     — 手动同步斜杠指令
#   • r!eval <code>      — 动态执行 Python（Owner 专属，高危）

import discord
from discord.ext import commands
import os
import traceback
from typing import Literal, Optional
from io import StringIO
import contextlib

COGS_DIR = "./cogs"


# ─────────────────────────────────────────────
class Dev(commands.Cog):
    """开发者工具 & 热更新"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ──────────────── 内部工具 ────────────────

    async def _smart_reload(self, ext: str) -> tuple[bool, str]:
        """尝试 reload，若未加载则 load；返回 (成功?, 错误信息)"""
        try:
            try:
                await self.bot.reload_extension(ext)
            except commands.ExtensionNotLoaded:
                await self.bot.load_extension(ext)
            return True, ""
        except Exception:
            return False, traceback.format_exc(limit=3).strip().splitlines()[-1]

    def _all_cog_exts(self) -> list[str]:
        if not os.path.isdir(COGS_DIR):
            return []
        return [
            f"cogs.{f[:-3]}"
            for f in os.listdir(COGS_DIR)
            if f.endswith(".py")
        ]

    # ──────────────── 指令：hot_update ────────────────

    @commands.hybrid_command(name="hot_update", description="[Dev] 热更新代码并可选同步指令")
    @commands.is_owner()
    async def hot_update(
        self,
        ctx,
        cog: Optional[str] = None,
        sync: Literal["no_sync", "guild", "global"] = "no_sync",
    ):
        """
        cog   : 留空=全部重载，填名字=只重载指定 cog（如 music）
        sync  : no_sync=不同步 | guild=同步到本服务器 | global=推送全球
        """
        await ctx.defer(ephemeral=True)
        log = []

        # ── 1. 重载 ──
        if cog:
            ext = cog if cog.startswith("cogs.") else f"cogs.{cog}"
            ok, err = await self._smart_reload(ext)
            short = ext.replace("cogs.", "")
            log.append(f"{'✅' if ok else '❌'} `{short}` {'重载成功' if ok else f'失败：{err}'}")
        else:
            for ext in self._all_cog_exts():
                ok, err = await self._smart_reload(ext)
                short = ext.replace("cogs.", "")
                log.append(f"{'✅' if ok else '❌'} `{short}` {'— ' + err if not ok else ''}")

        # ── 2. 同步（可选）──
        try:
            if sync == "guild":
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                log.append(f"⚡ 指令已同步到本服务器（{len(synced)} 个，即时生效）")
            elif sync == "global":
                synced = await self.bot.tree.sync()
                log.append(f"🌎 指令已全球推送（{len(synced)} 个，最长 1 小时生效）")
            else:
                log.append("⏩ 跳过指令同步")
        except Exception as e:
            log.append(f"❌ 同步失败：{e}")

        embed = discord.Embed(
            title="🔄 热更新完成",
            description="\n".join(log),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await ctx.send(embed=embed, ephemeral=True)

    # ──────────────── 指令：load ────────────────

    @commands.hybrid_command(name="load", description="[Dev] 加载一个新 Cog")
    @commands.is_owner()
    async def load_cmd(self, ctx, cog: str):
        await ctx.defer(ephemeral=True)
        ext = cog if cog.startswith("cogs.") else f"cogs.{cog}"
        try:
            await self.bot.load_extension(ext)
            await ctx.send(f"✨ `{ext}` 加载成功！", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ 加载失败：\n```\n{e}\n```", ephemeral=True)

    # ──────────────── 指令：unload ────────────────

    @commands.hybrid_command(name="unload", description="[Dev] 卸载一个 Cog（Dev 自身无法卸载）")
    @commands.is_owner()
    async def unload_cmd(self, ctx, cog: str):
        await ctx.defer(ephemeral=True)
        ext = cog if cog.startswith("cogs.") else f"cogs.{cog}"
        if ext == "cogs.dev":
            await ctx.send("⚠️ 不能卸载 Dev 自身！", ephemeral=True)
            return
        try:
            await self.bot.unload_extension(ext)
            await ctx.send(f"🗑 `{ext}` 已卸载。", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ 卸载失败：\n```\n{e}\n```", ephemeral=True)

    # ──────────────── 指令：extensions ────────────────

    @commands.hybrid_command(name="extensions", aliases=["exts"], description="[Dev] 查看所有扩展加载状态")
    @commands.is_owner()
    async def extensions_cmd(self, ctx):
        all_files = set(self._all_cog_exts())
        loaded = set(self.bot.extensions.keys())

        lines = []
        for ext in sorted(all_files | loaded):
            short = ext.replace("cogs.", "")
            if ext in loaded and ext in all_files:
                lines.append(f"🟢 `{short}` — 已加载")
            elif ext in loaded:
                lines.append(f"🟡 `{short}` — 已加载（文件已删除）")
            else:
                lines.append(f"🔴 `{short}` — 未加载")

        embed = discord.Embed(
            title="📦 扩展状态",
            description="\n".join(lines) or "（无）",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"共 {len(all_files)} 个 cog 文件")
        await ctx.send(embed=embed, ephemeral=True)

    # ──────────────── 指令：sync ────────────────

    @commands.hybrid_command(name="sync", description="[Dev] 同步斜杠指令树")
    @commands.is_owner()
    async def sync_cmd(self, ctx, scope: Literal["guild", "global", "clear_guild"] = "guild"):
        await ctx.defer(ephemeral=True)

        try:
            if scope == "guild":
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"⚡ 已同步 **{len(synced)}** 个指令到本服务器（即时生效）", ephemeral=True)

            elif scope == "global":
                synced = await self.bot.tree.sync()
                await ctx.send(f"🌎 已向全球推送 **{len(synced)}** 个指令（最长 1 小时生效）", ephemeral=True)

            elif scope == "clear_guild":
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send("🗑 已清除本服务器的斜杠指令缓存。", ephemeral=True)

        except Exception as e:
            await ctx.send(f"❌ 同步失败：\n```\n{e}\n```", ephemeral=True)

    # ──────────────── 指令：boteval ────────────────

    @commands.command(name="eval", hidden=True)   # 只保留前缀版本，更安全
    @commands.is_owner()
    async def boteval(self, ctx, *, code: str):
        """动态执行 Python 代码（仅 Owner，极度危险）"""
        # 去掉 markdown 代码块
        code = code.strip("`")
        if code.startswith("python\n") or code.startswith("py\n"):
            code = code.split("\n", 1)[1]

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "discord": discord,
            "commands": commands,
            "guild": ctx.guild,
            "channel": ctx.channel,
            "author": ctx.author,
        }

        stdout = StringIO()
        result = None
        error = None

        exec_code = f"async def _eval_body():\n{chr(10).join('    ' + l for l in code.splitlines())}"

        try:
            with contextlib.redirect_stdout(stdout):
                exec(compile(exec_code, "<eval>", "exec"), env)
                result = await env["_eval_body"]()
        except Exception:
            error = traceback.format_exc()

        output = stdout.getvalue()
        color = discord.Color.green() if not error else discord.Color.red()
        embed = discord.Embed(title="📟 Eval", color=color, timestamp=discord.utils.utcnow())

        if output:
            embed.add_field(name="stdout", value=f"```\n{output[:1000]}\n```", inline=False)
        if result is not None:
            embed.add_field(name="返回值", value=f"```py\n{repr(result)[:500]}\n```", inline=False)
        if error:
            embed.add_field(name="❌ 错误", value=f"```py\n{error[:1000]}\n```", inline=False)
        if not (output or result or error):
            embed.description = "✅ 执行完毕，无输出。"

        await ctx.send(embed=embed)

    # ──────────────── 错误处理 ────────────────

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("🚫 只有 Bot 拥有者可以使用此命令。", ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Dev(bot))