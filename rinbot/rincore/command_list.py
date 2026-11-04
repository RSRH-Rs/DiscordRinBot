"""机器人和控制台共用的指令清单：不能停用的指令，以及 health.json 缺失时控制台用的备用指令列表。"""
import json
import os

TABLE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "i18n", "commands.zh.json")

# 这些指令永远不能被停用（指令开关本身、帮助、开发和主人指令）
PROTECTED_COMMANDS = frozenset({
    "commands", "help",
    "hot_update", "sync", "load", "unload", "extensions", "eval", "setstatus", "resetstatus", "setbio",
})

# 38 条顶层斜杠指令和它们在控制台里的分组
COMMANDS = [
    *[(name, "Moderation") for name in (
        "ban", "unban", "kick", "mute", "unmute", "warn", "purge", "slowmode", "lock", "unlock", "warnings", "case",
    )],
    *[(name, "Music") for name in (
        "play", "search", "skip", "pause", "resume", "stop", "nowplaying", "queue",
        "remove", "clear", "shuffle", "loop", "volume", "move", "join", "playlist",
    )],
    *[(name, "General") for name in ("status", "roll", "avatar")],
    ("rank", "Leveling"), ("leaderboard", "Leveling"),
    ("giveaway", "Giveaway"), ("welcome", "Welcome"), ("automod", "AutoMod"),
    ("commands", "System"), ("help", "System"),
]


def registry() -> list[dict]:
    """备用指令列表 [{"name", "desc", "cog"}]，说明取翻译表里的中文。"""
    with open(TABLE_PATH, encoding="utf-8") as f:
        table = json.load(f).get("commands", {})
    return [{"name": name, "desc": table.get(name, {}).get("description", ""), "cog": cog} for name, cog in COMMANDS]
