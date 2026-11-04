"""测试辅助：不启动机器人，直接从各 cog 类读出斜杠指令树。"""
import importlib
import inspect
import os

from discord.ext import commands

COGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rinbot", "cogs")
SKIP = {"netease.py"}  # 本地模块，不进仓库


def cog_classes():
    for name in sorted(os.listdir(COGS_DIR)):
        if not name.endswith(".py") or name.startswith("_") or name in SKIP:
            continue
        module = importlib.import_module(f"cogs.{name[:-3]}")
        for obj in vars(module).values():
            if inspect.isclass(obj) and issubclass(obj, commands.Cog) and obj.__module__ == module.__name__:
                yield obj


def top_level_app_commands(cog=None):
    """顶层斜杠指令（不含主人指令）；cog 给定时只取这个 cog 类的。"""
    from _perms import is_owner_only

    result = []
    for cls in cog_classes() if cog is None else [cog]:
        for cmd in cls.__cog_commands__:
            if cmd.parent is None and getattr(cmd, "app_command", None) is not None and not is_owner_only(cmd):
                result.append(cmd.app_command)
    return result


def walk(app_cmd):
    """指令自己和它下面所有的子组、子指令。"""
    yield app_cmd
    for child in getattr(app_cmd, "commands", []):
        yield from walk(child)
