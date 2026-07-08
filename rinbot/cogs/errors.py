# cogs/errors.py
# 统一友好报错：把常见异常转成简洁、私密(ephemeral)的提示，未知错误只记录不刷屏

import discord
from discord.ext import commands
from discord import app_commands


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
    if isinstance(error, commands.BadArgument):
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
            print(f"[error] {ctx.command}: {getattr(error, 'original', error)!r}")
            msg = "😵 出了点问题，已记录，请稍后再试。"
        try:
            await ctx.send(msg, ephemeral=True)
        except Exception:
            pass

    async def _on_app_error(self, interaction: discord.Interaction, error):
        msg = _friendly(error)
        if msg is None:
            return
        if msg == "__UNEXPECTED__":
            print(
                f"[app error] {getattr(interaction.command, 'name', None)}: {getattr(error, 'original', error)!r}"
            )
            msg = "😵 出了点问题，已记录，请稍后再试。"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
