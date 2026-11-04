import ast
import asyncio
import os
from types import SimpleNamespace

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from command_tree import top_level_app_commands, walk
from rincore import command_i18n
from rincore.command_i18n import CommandTranslator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = {
    "commands": {
        "t": {
            "description": "测试指令",
            "params": {"member": {"name": "成员", "description": "要处理的成员"}},
            "examples": ["/t @小明"],
        },
        "pick": {"description": "选一个", "params": {"mode": {"name": "模式", "description": "选哪个"}}, "examples": ["/pick"]},
    },
    "choices": {"off": "关闭", "single": "单曲"},
}

# 已经整理过、必须完整翻译的顶层指令；后面的任务逐个加进来，最后一个任务改成全部
DONE: set[str] = {
    # Task 4
    "ban", "unban", "kick", "mute", "unmute", "warn", "purge", "slowmode", "lock", "unlock", "warnings",
    # Task 5
    "case",
    # Task 6
    "play", "search", "skip", "pause", "resume", "stop", "nowplaying", "queue",
    "remove", "clear", "shuffle", "loop", "volume", "move", "join", "playlist",
    # Task 7
    "giveaway", "status", "roll", "avatar", "help", "rank", "leaderboard",
    # Task 8
    "welcome", "automod", "commands",
}


@commands.hybrid_command(name="t", description="Test command")
async def _t(ctx, member: discord.Member):
    """member: The member to handle"""


@commands.hybrid_command(name="pick", description="Pick one")
@app_commands.choices(mode=[app_commands.Choice(name="Off", value="off"), app_commands.Choice(name="Single", value="single")])
async def _pick(ctx, mode: str):
    pass


def _payload(cmd, table=TABLE):
    tree = commands.Bot(command_prefix="r!", intents=discord.Intents.none()).tree
    return asyncio.run(cmd.app_command.get_translated_payload(tree, CommandTranslator(table=table)))


def test_translator_ignores_other_languages():
    translator = CommandTranslator(table=TABLE)
    context = app_commands.TranslationContext(
        location=app_commands.TranslationContextLocation.command_description, data=_t.app_command
    )
    for locale in (discord.Locale.american_english, discord.Locale.japanese):
        assert asyncio.run(translator.translate(app_commands.locale_str("Test command"), locale, context)) is None


def test_translator_fills_descriptions_params_and_choices():
    payload = _payload(_t)
    assert payload["description_localizations"] == {"zh-CN": "测试指令", "zh-TW": "测试指令"}
    assert not payload.get("name_localizations")
    option = payload["options"][0]
    assert option["name_localizations"] == {"zh-CN": "成员", "zh-TW": "成员"}
    assert option["description_localizations"]["zh-CN"] == "要处理的成员"
    pick = _payload(_pick)["options"][0]
    assert [c["name_localizations"]["zh-CN"] for c in pick["choices"]] == ["关闭", "单曲"]


def test_translator_missing_entry_returns_none():
    payload = _payload(_t, table={"commands": {}, "choices": {}})
    assert not payload.get("description_localizations")
    assert not payload["options"][0].get("name_localizations")


def test_snapshot_and_help_prefer_chinese(monkeypatch):
    from cogs import health, help as help_cog

    monkeypatch.setattr(command_i18n, "load", lambda path=None: TABLE)
    snapshot = health.Health(SimpleNamespace(commands=[_t, _pick]))._command_snapshot()
    assert {c["name"]: c["desc"] for c in snapshot} == {"t": "测试指令", "pick": "选一个"}
    assert help_cog._format_command(_t) == "**`/t`** — 测试指令"
    monkeypatch.setattr(command_i18n, "load", lambda path=None: {"commands": {}, "choices": {}})
    assert help_cog._format_command(_t) == "**`/t`** — Test command"


def _problems(top, table):
    problems = []
    for cmd in walk(top):
        path = cmd.qualified_name
        zh = command_i18n.zh_description(path, table)
        if not zh or not 1 <= len(zh) <= 100:
            problems.append((path, "description"))
        if not 1 <= len(cmd.description) <= 100 or cmd.description == "…":
            problems.append((path, "english description"))
        if isinstance(cmd, app_commands.Group):
            continue
        seen = set()
        for param in cmd.parameters:
            entry = command_i18n.zh_param(path, param.name, table) or {}
            name, desc = entry.get("name", ""), entry.get("description", "")
            if not 1 <= len(name) <= 32 or name in seen:
                problems.append((path, f"param {param.name} name"))
            seen.add(name)
            if not 1 <= len(desc) <= 100:
                problems.append((path, f"param {param.name} description"))
            if param.description in ("…", "") or len(param.description) > 100:
                problems.append((path, f"param {param.name} english description"))
            for choice in param.choices:
                if str(choice.value) not in table.get("choices", {}):
                    problems.append((path, f"choice {choice.value}"))
        if not command_i18n.examples(path, table):
            problems.append((path, "examples"))
    return problems


@pytest.mark.parametrize("name", sorted(DONE))
def test_every_command_is_translated(name):
    tops = {cmd.name: cmd for cmd in top_level_app_commands()}
    assert name in tops
    assert _problems(tops[name], command_i18n.load()) == []


def test_bot_installs_translator():
    with open(os.path.join(ROOT, "rinbot", "main.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    hook = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "setup_hook")
    calls = [ast.unparse(n) for n in ast.walk(hook) if isinstance(n, ast.Call)]
    assert "self.tree.set_translator(CommandTranslator())" in calls
