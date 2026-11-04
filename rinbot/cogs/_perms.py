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


def require(**perms):
    """成员需要这些权限：执行时检查，并让 Discord 默认对没有权限的成员隐藏。
    写在 @commands.hybrid_command / @组.command 下面；Discord 只认顶层指令的默认权限，指令组要加在组上。"""

    def decorator(func):
        func = commands.has_permissions(**perms)(func)
        return app_commands.default_permissions(**perms)(func)

    return decorator


def owner_only():
    """只限机器人主人：斜杠版只注册到开发服务器（未配置时不注册斜杠版，只留 r! 前缀版）。"""

    def decorator(func):
        func = commands.is_owner()(func)
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
