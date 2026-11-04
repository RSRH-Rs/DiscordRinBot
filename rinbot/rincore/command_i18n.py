"""指令的中文翻译：读 rinbot/i18n/commands.zh.json，并作为 discord.py 的翻译器在同步指令时交给 Discord。

指令名不翻（所有语言都打英文）；指令说明、参数名、参数说明、选项名在简体和繁体中文客户端显示同一份中文。
表的键是指令的完整路径（如 "warnings remove"），选项按值查（如 "off"）。
"""
import json
import os
from functools import lru_cache
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import TranslationContextLocation as Where

TABLE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "i18n", "commands.zh.json")
ZH_LOCALES = {discord.Locale.chinese, discord.Locale.taiwan_chinese}


@lru_cache(maxsize=None)
def load(path: str = TABLE_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _entry(path: str, table: Optional[dict]) -> dict:
    table = table if table is not None else load()
    return table.get("commands", {}).get(path, {})


def zh_description(path: str, table: Optional[dict] = None) -> Optional[str]:
    return _entry(path, table).get("description")


def zh_param(path: str, name: str, table: Optional[dict] = None) -> Optional[dict]:
    return _entry(path, table).get("params", {}).get(name)


def examples(path: str, table: Optional[dict] = None) -> list[str]:
    return list(_entry(path, table).get("examples", []))


class CommandTranslator(app_commands.Translator):
    """同步指令时给中文客户端提供翻译；查不到或不是中文时返回 None，Discord 就显示英文。"""

    def __init__(self, table: Optional[dict] = None):
        super().__init__()
        self._table = table

    def _current(self) -> dict:
        return self._table if self._table is not None else load()

    async def translate(self, string, locale, context) -> Optional[str]:
        if locale not in ZH_LOCALES:
            return None
        table = self._current()
        where, data = context.location, context.data
        if where in (Where.command_description, Where.group_description):
            return zh_description(data.qualified_name, table)
        if where in (Where.parameter_name, Where.parameter_description):
            entry = zh_param(data.command.qualified_name, data.name, table)
            if not entry:
                return None
            return entry.get("name" if where is Where.parameter_name else "description")
        if where is Where.choice_name:
            return table.get("choices", {}).get(str(data.value))
        return None
