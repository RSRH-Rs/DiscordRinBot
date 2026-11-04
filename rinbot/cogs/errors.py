# cogs/errors.py
# 统一友好报错：把常见异常转成简洁、私密的提示，未知错误只记录并给出错误编号

import discord
from discord.ext import commands
from discord import app_commands
import math
import time
import traceback
import uuid

from _inputs import BadDuration, DurationTooLong
from _messages import Notice, send_moved, send_notice
from rincore.durations import label


def _root_exception(error) -> BaseException:
    """剥掉 CommandInvokeError / HybridCommandError 等包装，取最里层的真实异常"""
    while getattr(error, "original", None) is not None:
        error = error.original
    return error


# 权限英文名 -> Discord 简体中文客户端里的叫法
PERMISSION_NAMES = {
    "administrator": "管理员",
    "view_channel": "查看频道",
    "manage_channels": "管理频道",
    "manage_roles": "管理身份组",
    "manage_guild": "管理服务器",
    "kick_members": "踢出成员",
    "ban_members": "封禁成员",
    "moderate_members": "禁言成员",
    "manage_messages": "管理消息",
    "manage_nicknames": "管理昵称",
    "send_messages": "发送消息",
    "embed_links": "嵌入链接",
    "attach_files": "附加文件",
    "read_message_history": "阅读消息历史记录",
    "add_reactions": "添加反应",
    "use_external_emojis": "使用外部表情符号",
    "mention_everyone": "提及 @everyone、@here 和所有身份组",
    "connect": "连接",
    "speak": "说话",
}

UNEXPECTED = object()  # notice_for 的返回值：未知错误，需要上报并给出错误编号

_MENTION_HINT = "检查一下有没有打错，或者直接 @ 对方。"


def permission_list(perms) -> str:
    """["manage_messages", "embed_links"] -> 「管理消息」「嵌入链接」"""
    return "".join(f"「{PERMISSION_NAMES.get(p, p.replace('_', ' '))}」" for p in perms)


def usage(command, *, slash: bool) -> str:
    """指令用法行：必填 <名字>，可选 [名字]，不显示默认值。"""
    if hasattr(command, "clean_params"):
        params = [(name, p.required) for name, p in command.clean_params.items()]
    else:
        params = [(p.name, p.required) for p in command.parameters]
    parts = [f"<{name}>" if required else f"[{name}]" for name, required in params]
    return " ".join([f"{'/' if slash else 'r!'}{command.qualified_name}", *parts])


def _usage_line(command, slash):
    return f"用法：`{usage(command, slash=slash)}`" if command is not None else None


def notice_for(error, *, command=None, slash: bool = False, now: float | None = None):
    """把指令错误转成给用户看的提示；None=不回复；UNEXPECTED=未知错误，需要上报。"""
    if isinstance(error, commands.HybridCommandError):
        error = error.original
    if isinstance(error, commands.CommandNotFound):
        return None
    if isinstance(error, (commands.MissingPermissions, app_commands.MissingPermissions)):
        return Notice("error", "你没有权限使用这条指令", f"需要{permission_list(error.missing_permissions)}权限。")
    if isinstance(error, (commands.BotMissingPermissions, app_commands.BotMissingPermissions)):
        return Notice(
            "error",
            f"小凛缺少{permission_list(error.missing_permissions)}权限",
            "请服务器管理员在 服务器设置 → 身份组 里给小凛打开这个权限，再试一次。",
        )
    if isinstance(error, commands.MissingRequiredArgument):
        return Notice("error", f"缺少参数「{error.param.name}」", _usage_line(command, slash))
    if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
        ready = math.ceil((time.time() if now is None else now) + error.retry_after)
        return Notice("warning", "操作太快了", f"<t:{ready}:R>可以再用。")
    if isinstance(error, (commands.NoPrivateMessage, app_commands.NoPrivateMessage)):
        return Notice("error", "这条指令只能在服务器里用")
    if isinstance(error, commands.MemberNotFound):
        return Notice("error", "找不到这个成员", _MENTION_HINT)
    if isinstance(error, commands.UserNotFound):
        return Notice("error", "找不到这个用户", _MENTION_HINT)
    if isinstance(error, commands.RoleNotFound):
        return Notice("error", "找不到这个身份组", "检查一下名字有没有打错，或者直接 @ 这个身份组。")
    if isinstance(error, commands.ChannelNotFound):
        return Notice("error", "找不到这个频道", "检查一下名字有没有打错，或者直接 # 这个频道。")
    if isinstance(error, BadDuration):
        return Notice("error", "时长格式不对", "可以写 10m、1h30m、2d、1w，或者 10分钟、1小时、2天。")
    if isinstance(error, DurationTooLong):
        return Notice("error", "时长太长了", f"最长 {label(error.limit, zh=True)}。")
    if isinstance(error, (commands.BadArgument, commands.UserInputError)):
        # 其余 UserInputError（BadLiteralArgument/BadUnionArgument/TooManyArguments 等）
        return Notice("error", "参数格式不对", _usage_line(command, slash))
    if isinstance(error, commands.NotOwner):
        return Notice("error", "只有机器人主人能用这条指令")
    # 全局 check（黑名单/维护）会自行提示，这里静默避免重复
    if isinstance(error, (commands.CheckFailure, app_commands.CheckFailure)):
        return None
    return UNEXPECTED


def unexpected_notice(error_id: str) -> Notice:
    return Notice(
        "error",
        "这条指令没有执行成功",
        f"已自动记录，错误编号 `{error_id}`。稍后再试；一直出错的话，反馈时带上这个编号。",
    )


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
        if isinstance(error, commands.CommandNotFound):
            # 删掉的设置指令告诉用户去控制台；其他找不到的指令照旧不回复
            if ctx.invoked_with:
                await send_moved(ctx, ctx.invoked_with.lower())
            return
        notice = notice_for(error, command=ctx.command, slash=ctx.interaction is not None)
        if notice is None:
            return
        if notice is UNEXPECTED:
            error_id = await self._report(
                ctx.guild.id if ctx.guild else None,
                f"指令执行失败: /{ctx.command.qualified_name if ctx.command else '未知指令'}",
                _root_exception(error),
                **{
                    "用户": ctx.author.mention,
                    "频道": getattr(ctx.channel, "mention", "私信"),
                },
            )
            notice = unexpected_notice(error_id)
        await send_notice(ctx, notice)

    async def _on_app_error(self, interaction: discord.Interaction, error):
        notice = notice_for(error, command=interaction.command, slash=True)
        if notice is None:
            return
        if notice is UNEXPECTED:
            error_id = await self._report(
                interaction.guild.id if interaction.guild else None,
                f"Slash 指令执行失败: /{getattr(interaction.command, 'qualified_name', '未知指令')}",
                _root_exception(error),
                **{
                    "用户": interaction.user.mention,
                    "频道": getattr(interaction.channel, "mention", "私信"),
                },
            )
            notice = unexpected_notice(error_id)
        await send_notice(interaction, notice)


async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
