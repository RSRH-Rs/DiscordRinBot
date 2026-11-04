"""最终的指令表：40 条顶层斜杠指令，删掉的不再出现，旧前缀名都能找到新指令。"""
import os

import discord
from discord.ext import commands

from command_tree import cog_classes, top_level_app_commands
from rincore import legacy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {
    "ban", "unban", "kick", "mute", "unmute", "warn", "purge", "slowmode", "lock", "unlock",
    "warnings", "case",
    "play", "search", "skip", "pause", "resume", "stop", "nowplaying", "queue",
    "remove", "clear", "shuffle", "loop", "volume", "move", "join", "playlist",
    "status", "roll", "avatar", "help", "rank", "leaderboard",
    "giveaway", "welcome", "automod", "commands", "roles", "serverlog",
}


def _bot():
    bot = commands.Bot(command_prefix="r!", intents=discord.Intents.none(), help_command=None)
    for cls in cog_classes():
        for cmd in cls.__cog_commands__:
            if cmd.parent is None:
                bot.add_command(cmd)
    return bot


def test_top_level_commands_are_the_40():
    names = {cmd.name for cmd in top_level_app_commands()}
    assert len(EXPECTED) == 40
    assert names == EXPECTED


def test_removed_commands_are_gone():
    bot = _bot()
    names = {cmd.name for cmd in top_level_app_commands()}
    for key in list(legacy.REMOVED) + list(legacy.RENAMED):
        assert bot.get_command(key) is None, key
        if " " not in key:
            assert key not in names, key


def test_renamed_targets_exist():
    bot = _bot()
    for old, new in legacy.RENAMED.items():
        assert bot.get_command(new) is not None, (old, new)


def test_homepage_uses_new_names():
    with open(os.path.join(ROOT, "website", "templates", "index.html"), encoding="utf-8") as f:
        html = f.read()
    for old in ("'/tempban'", "'/serverlog'"):
        assert old not in html
    assert "'/ban'" in html and "'/case'" in html
