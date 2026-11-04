"""旧指令名的兼容：改了名的旧前缀名在解析前改写成新指令路径；删掉的设置指令指向控制台；迁移停用记录。

改写发生在机器人解析前缀指令之前，所以权限、停用、维护、冷却和报错都和直接用新指令一样。
"""
import re

PREFIX = "r!"
DASHBOARD = "https://rin-bot.com"

# 旧前缀名（含旧别名）→ 新指令路径；参数顺序不变
RENAMED = {
    "tempban": "ban",
    "warns": "warnings list",
    "delwarn": "warnings remove",
    "clearwarns": "warnings clear",
    "modlog": "case list",
    "saveq": "playlist save",
    "savequeue": "playlist save",
    "loadq": "playlist load",
    "loadqueue": "playlist load",
    "queues": "playlist list",
    "savedqueues": "playlist list",
    "qlist": "playlist list",
    "delqueue": "playlist delete",
    "delq": "playlist delete",
    "toggle": "commands toggle",
    "togglelist": "commands list",
    "welcome_setup": "welcome setup",
    "welcome_test": "welcome test",
    "automod_words": "automod words",
    "automod_whitelist": "automod whitelist",
    "automod_ignore": "automod ignore",
}

_WELCOME = ("welcome", "欢迎新成员")
_ROLES = ("roles", "领取身份组")
_AUTOMOD = ("automod", "自动审核")
_SERVERLOG = ("serverlog", "服务器事件日志")
_MODERATION = ("moderation", "管理模块")

# 删掉的设置指令（含旧别名、旧子指令路径）→ (控制台页面, 页面名)
REMOVED = {
    **{name: _WELCOME for name in (
        "welcome_message", "welcome_toggle", "welcome_image", "welcome_title", "welcome_icon",
        "welcome_thumbnail", "welcome_thumb", "welcome_card", "welcome_disable",
    )},
    **{name: _ROLES for name in ("rr_create", "rr_add", "rr_remove", "rr_list", "rr_exclusive", "rr_delete")},
    **{f"automod {sub}": _AUTOMOD for sub in ("enable", "disable", "toggle", "log", "mute_duration", "spam_config")},
    "serverlog": _SERVERLOG,
    "slog": _SERVERLOG,
    "modlog_channel": _MODERATION,
    "warn_config": _MODERATION,
}

_COMMAND = re.compile(r"(\S+)(\s.*)?", re.S)


def dashboard_url(guild_id: int, slug: str) -> str:
    return f"{DASHBOARD}/dashboard/server/{guild_id}#{slug}"


def rewrite(content: str) -> str:
    """r!旧名 … → r!新路径 …；只认紧跟前缀的完整指令名（区分大小写，和指令解析一致），其他原样返回。"""
    if not content.startswith(PREFIX):
        return content
    match = _COMMAND.fullmatch(content[len(PREFIX):])
    if not match or match.group(1) not in RENAMED:
        return content
    return PREFIX + RENAMED[match.group(1)] + (match.group(2) or "")


def migrate_disabled(names: set[str]) -> set[str]:
    """停用记录里的旧名换成新的顶层指令名；tempban（并进了 ban）和删掉的指令直接丢掉。"""
    result = set()
    for name in names:
        if name == "tempban" or name in REMOVED:
            continue
        result.add(RENAMED[name].split()[0] if name in RENAMED else name)
    return result
