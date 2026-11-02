# cogs/errors.py
# 统一友好报错：把常见异常转成简洁、私密(ephemeral)的提示，未知错误只记录不刷屏

import discord
from discord.ext import commands
from discord import app_commands
import traceback
import uuid


def _root_exception(error) -> BaseException:
    """剥掉 CommandInvokeError / HybridCommandError 等包装，取最里层的真实异常"""
    while getattr(error, "original", None) is not None:
        error = error.original
    return error


def _friendly(error) -> str | None:
    """返回给用户看的提示；None=保持静默；'__UNEXPECTED__'=未知错误需记录"""
    if isinstance(error, commands.CommandNotFound):
        return None
    if isinstance(
        error, (commands.MissingPermissions, app_commands.MissingPermissions)
    ):
        return "🚫 你没有权限使用这个指令。"
    if isinstance(
        error, (commands.BotMissingPermissions, app_commands.BotMissingPermissions)
    ):
        perms = "、".join(getattr(error, "missing_permissions", []) or [])
        return f"⚠️ 我缺少所需权限：{perms}" if perms else "⚠️ 我缺少所需权限。"
    if isinstance(error, commands.MissingRequiredArgument):
        return f"❓ 缺少参数：`{error.param.name}`。"
    if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
        return f"⏳ 冷却中，请 {error.retry_after:.1f} 秒后再试。"
    if isinstance(error, (commands.NoPrivateMessage, app_commands.NoPrivateMessage)):
        return "该指令只能在服务器里使用。"
    if isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
        return "找不到该用户。"
    if isinstance(error, commands.RoleNotFound):
        return "找不到该身份组。"
    if isinstance(error, commands.ChannelNotFound):
        return "找不到该频道。"
    if isinstance(error, (commands.BadArgument, commands.UserInputError)):
        # 其余 UserInputError（BadLiteralArgument/BadUnionArgument/TooManyArguments 等）；
        # 更具体的子类已在上面处理
        return "参数有误，请检查后重试。"
    # 全局 check（黑名单/维护）会自行提示，这里静默避免重复
    if isinstance(error, (commands.CheckFailure, app_commands.CheckFailure)):
        return None
    return "__UNEXPECTED__"


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._old_tree_error = None

    async def cog_load(self):
        self._old_tree_error = self.bot.tree.on_error
        self.bot.tree.on_error = self._on_app_error

    async def cog_unload(self):
        if self._old_tree_error:
            self.bot.tree.on_error = self._old_tree_error

    async def _report(self, guild_id, title, exc, **fields) -> str:
        """未知错误统一上报，返回错误编号；上报本身绝不抛出异常"""
        botlog = self.bot.get_cog("BotLog")
        if botlog:
            try:
                return await botlog.report_exception(guild_id, title, exc, **fields)
            except Exception:
                pass
        error_id = uuid.uuid4().hex[:8].upper()
        try:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        except Exception:
            tb = repr(exc)
        print(f"[error {error_id}] {title} (guild {guild_id})\n{tb}")
        return error_id

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if (ctx.command and ctx.command.has_error_handler()) or (
            ctx.cog and ctx.cog.has_error_handler()
        ):
            return
        msg = _friendly(error)
        if msg is None:
            return
        if msg == "__UNEXPECTED__":
            error_id = await self._report(
                ctx.guild.id if ctx.guild else None,
                f"指令执行失败: /{ctx.command.qualified_name if ctx.command else '未知指令'}",
                _root_exception(error),
                **{
                    "用户": ctx.author.mention,
                    "频道": getattr(ctx.channel, "mention", "私信"),
                },
            )
            msg = f"😵 出了点问题（错误编号 {error_id}），请稍后再试。"
        try:
            await ctx.send(msg, ephemeral=True)
        except Exception:
            pass

    async def _on_app_error(self, interaction: discord.Interaction, error):
        msg = _friendly(error)
        if msg is None:
            return
        if msg == "__UNEXPECTED__":
            error_id = await self._report(
                interaction.guild.id if interaction.guild else None,
                f"Slash 指令执行失败: /{getattr(interaction.command, 'qualified_name', '未知指令')}",
                _root_exception(error),
                **{
                    "用户": interaction.user.mention,
                    "频道": getattr(interaction.channel, "mention", "私信"),
                },
            )
            msg = f"😵 出了点问题（错误编号 {error_id}），请稍后再试。"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
