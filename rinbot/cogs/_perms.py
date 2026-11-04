# cogs/_perms.py
# 指令权限的统一写法：执行时检查和 Discord 默认隐藏从同一处声明，避免两边对不上

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

try:
    from config import DEV_GUILD_ID
except ImportError:
    DEV_GUILD_ID = 0


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


def permission_list(perms) -> str:
    """["manage_messages", "embed_links"] -> 「管理消息」「嵌入链接」"""
    return "".join(f"「{PERMISSION_NAMES.get(p, p.replace('_', ' '))}」" for p in perms)


def require(**perms):
    """成员需要这些权限：执行时检查，并让 Discord 默认对没有权限的成员隐藏。
    写在 @commands.hybrid_command / @组.command 下面；Discord 只认顶层指令的默认权限，指令组要加在组上。"""

    def decorator(func):
        func = commands.has_permissions(**perms)(func)
        func.__rinbot_required__ = list(perms)  # /help 按写的顺序显示这条指令自己要的权限
        return app_commands.default_permissions(**perms)(func)

    return decorator


def owner_only():
    """只限机器人主人：斜杠版只注册到开发服务器（未配置时不注册斜杠版，只留 r! 前缀版）。"""

    def decorator(func):
        func = commands.is_owner()(func)
        # 开发服务器里也只让管理员看到（主人本人是管理员）
        func = app_commands.default_permissions(administrator=True)(func)
        func = (app_commands.guilds(DEV_GUILD_ID) if DEV_GUILD_ID else app_commands.guilds())(func)
        func.__rinbot_owner_only__ = True
        return func

    return decorator


def is_owner_only(command) -> bool:
    return bool(getattr(command.callback, "__rinbot_owner_only__", False))


def required_permissions(command) -> Optional[discord.Permissions]:
    """指令（子指令看所在的顶层组）的 Discord 默认权限；不需要权限时为 None。"""
    root = command.root_parent or command
    app = getattr(root, "app_command", None)
    return app.default_permissions if app is not None else None
