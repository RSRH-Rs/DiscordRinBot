# cogs/_inputs.py
# 指令参数的共用工具：时长转换器和补全、补全候选过滤、按客户端语言选中英文

from typing import Iterable

import discord
from discord import app_commands
from discord.ext import commands

from rincore import durations

ZH_LOCALES = {discord.Locale.chinese, discord.Locale.taiwan_chinese}
_OFF = {"0", "关闭", "off"}


class BadDuration(commands.BadArgument):
    """时长写法看不懂"""


class DurationTooLong(commands.BadArgument):
    def __init__(self, limit: int):
        super().__init__(f"duration longer than {limit} seconds")
        self.limit = limit


def is_zh(interaction) -> bool:
    return getattr(interaction, "locale", None) in ZH_LOCALES


def Duration(kind: str) -> type[commands.Converter]:
    """某条指令的时长参数：返回秒数；kind 是 durations.PRESETS 的键，常用值里有 0 时接受"关闭"。"""
    limit = durations.LIMITS[kind]
    allow_off = 0 in durations.PRESETS[kind]

    class _Duration(commands.Converter):
        async def convert(self, ctx, argument: str) -> int:
            text = argument.strip().lower()
            if allow_off and text in _OFF:
                return 0
            seconds = durations.parse_duration(text, limit=None)
            if seconds is None:
                raise BadDuration(argument)
            if seconds > limit:
                raise DurationTooLong(limit)
            return seconds

    _Duration.__name__ = f"Duration_{kind}"
    return _Duration


def duration_autocomplete(kind: str):
    """时长参数的补全：常用值、纯数字铺开、能解析的放第一个；文字按客户端语言显示。"""

    async def autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        pairs = durations.suggest(current, durations.PRESETS[kind], durations.LIMITS[kind], is_zh(interaction))
        return [app_commands.Choice(name=name, value=value) for name, value in pairs]

    return autocomplete


def choices(items: Iterable[tuple[str, object]], current: str, limit: int = 25) -> list[app_commands.Choice]:
    """按显示文字过滤候选（不区分大小写的包含匹配），保持原顺序，最多 limit 个。"""
    needle = (current or "").strip().lower()
    result = []
    for name, value in items:
        name = str(name)
        if needle and needle not in name.lower():
            continue
        result.append(app_commands.Choice(name=name[:100], value=value if isinstance(value, int) else str(value)))
        if len(result) >= limit:
            break
    return result
