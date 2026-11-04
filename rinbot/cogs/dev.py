import discord
from discord.ext import commands
import _perms
from _perms import owner_only
from _messages import embed
import os
import traceback
from typing import Literal, Optional
from io import StringIO
import contextlib

COGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_ENABLED = os.getenv("RINBOT_ENABLE_EVAL", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


async def sync_commands(tree, scope: str, guild, dev_guild_id: int) -> str:
    """同步斜杠指令树。开发服务器只注册了开发指令，清它的副本会把开发指令一起清掉，所以永远跳过。"""
    in_dev = guild is not None and dev_guild_id and guild.id == dev_guild_id
    if scope == "clear_guild":
        if guild is None:
            return "只能在服务器里清除指令缓存。"
        if in_dev:
            return "开发服务器的指令不能清掉，改用 global。"
        tree.clear_commands(guild=guild)
        await tree.sync(guild=guild)
        return "已清除本服务器的斜杠指令缓存。"

    prefix = ""
    if scope == "guild" and guild is not None and not in_dev:
        # 清掉本服务器残留的旧副本，避免和全局指令重复显示
        tree.clear_commands(guild=guild)
        await tree.sync(guild=guild)
        prefix = "已清理本服务器的旧指令，"
    synced = await tree.sync()
    result = f"{prefix}已同步 {len(synced)} 个全局指令"
    if dev_guild_id:
        dev_synced = await tree.sync(guild=discord.Object(dev_guild_id))
        result += f"，开发服务器 {len(dev_synced)} 个"
    return result


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
        return [f"cogs.{f[:-3]}" for f in os.listdir(COGS_DIR) if f.endswith(".py")]

    # ──────────────── 指令：hot_update ────────────────

    @commands.hybrid_command(
        name="hot_update", description="[Dev] 热更新代码并可选同步指令"
    )
    @owner_only()
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
            log.append(
                f"{'✅' if ok else '❌'} `{short}` {'重载成功' if ok else f'失败：{err}'}"
            )
        else:
            for ext in self._all_cog_exts():
                ok, err = await self._smart_reload(ext)
                short = ext.replace("cogs.", "")
                log.append(
                    f"{'✅' if ok else '❌'} `{short}` {'— ' + err if not ok else ''}"
                )

        # ── 2. 同步（可选）──
        try:
            if sync in ("guild", "global"):
                log.append(await sync_commands(self.bot.tree, sync, ctx.guild, _perms.DEV_GUILD_ID))
            else:
                log.append("⏩ 跳过指令同步")
        except Exception as e:
            log.append(f"❌ 同步失败：{e}")

        if any(entry.startswith("❌") for entry in log):
            card = embed("warning", "热更新完成，有模块失败", "\n".join(log))
        else:
            card = embed("success", "热更新完成", "\n".join(log))
        await ctx.send(embed=card, ephemeral=True)

    # ──────────────── 指令：load ────────────────

    @commands.hybrid_command(name="load", description="[Dev] 加载一个新 Cog")
    @owner_only()
    async def load_cmd(self, ctx, cog: str):
        await ctx.defer(ephemeral=True)
        ext = cog if cog.startswith("cogs.") else f"cogs.{cog}"
        try:
            await self.bot.load_extension(ext)
            await ctx.send(f"✨ `{ext}` 加载成功！", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ 加载失败：\n```\n{e}\n```", ephemeral=True)

    # ──────────────── 指令：unload ────────────────

    @commands.hybrid_command(
        name="unload", description="[Dev] 卸载一个 Cog（Dev 自身无法卸载）"
    )
    @owner_only()
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

    @commands.hybrid_command(
        name="extensions", aliases=["exts"], description="[Dev] 查看所有扩展加载状态"
    )
    @owner_only()
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

        card = embed("info", "扩展状态", "\n".join(lines) or "（无）", footer=f"共 {len(all_files)} 个 cog 文件")
        await ctx.send(embed=card, ephemeral=True)

    # ──────────────── 指令：sync ────────────────

    @commands.hybrid_command(name="sync", description="[Dev] 同步斜杠指令树")
    @owner_only()
    async def sync_cmd(
        self, ctx, scope: Literal["guild", "global", "clear_guild"] = "guild"
    ):
        await ctx.defer(ephemeral=True)

        try:
            result = await sync_commands(self.bot.tree, scope, ctx.guild, _perms.DEV_GUILD_ID)
            await ctx.send(result, ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ 同步失败：\n```\n{e}\n```", ephemeral=True)

    # ──────────────── 指令：boteval ────────────────

    @commands.command(name="eval", hidden=True)  # 只保留前缀版本，更安全
    @owner_only()
    async def boteval(self, ctx, *, code: str):
        """动态执行 Python 代码（仅 Owner，极度危险）"""
        if not EVAL_ENABLED:
            await ctx.send(
                "⛔ Eval 已在生产环境禁用；仅可通过 RINBOT_ENABLE_EVAL=1 临时开启。"
            )
            return
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
        fields = [
            ("stdout", f"```\n{output[:1000]}\n```" if output else None, False),
            ("返回值", f"```py\n{repr(result)[:500]}\n```" if result is not None else None, False),
            ("错误", f"```py\n{error[:1000]}\n```" if error else None, False),
        ]
        quiet = None if (output or result is not None or error) else "执行完毕，无输出。"
        card = embed("error" if error else "success", "执行出错" if error else "执行完成", quiet, fields=fields)
        await ctx.send(embed=card)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dev(bot))
