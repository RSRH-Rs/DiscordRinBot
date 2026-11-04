"""机器人解析前缀指令前，把改了名的旧指令名改写成新指令路径（规则在 legacy.py）。

单独放成一个 mixin，测试可以拿真实的 commands.Bot 来跑，不必启动 main.py。
"""
import copy

import discord
from discord.ext import commands

from rincore import legacy


class LegacyNamesMixin:
    async def get_context(self, origin, /, *, cls=commands.Context):
        # 斜杠指令走交互，不改；前缀消息改写后照常解析，所以权限、停用、维护、冷却和报错都照常生效。
        # 改的是消息的副本，自动审核等监听器读到的仍是原文
        old_name = None
        if not isinstance(origin, discord.Interaction):
            rewritten, old_name = legacy.rewrite_named(origin.content)
            if old_name:
                origin = copy.copy(origin)
                origin.content = rewritten
        ctx = await super().get_context(origin, cls=cls)
        ctx.rinbot_legacy = old_name  # 指令里需要知道用户打的是哪个旧名字（如 r!tempban 必须填时长）
        return ctx
