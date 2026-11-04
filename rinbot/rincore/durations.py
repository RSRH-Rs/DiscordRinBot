"""RinBot 共享时长解析与格式化（moderation、giveaway 和指令补全共用）。

写法：10m、1h30m、2d、1w，或者 10分钟、1小时30分钟、2天、1周；不区分大小写，单位之间可以有空格。
"""
import re
from typing import Optional, Sequence

_MULTIPLIERS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
_UNITS = {
    "s": "s", "秒": "s",
    "m": "m", "分钟": "m", "分": "m",
    "h": "h", "小时": "h", "时": "h",
    "d": "d", "天": "d", "日": "d",
    "w": "w", "周": "w", "星期": "w",
}
_UNIT_RE = r"(?:星期|分钟|小时|[smhdw秒分时天日周])"
_TOKEN = re.compile(rf"(\d+)\s*({_UNIT_RE})")
_WHOLE = re.compile(rf"(?:\s*\d+\s*{_UNIT_RE}\s*)+")
MAX_SECONDS = 365 * 86400

# 各指令的常用值和上限（秒）；常用值里的 0 表示"关闭"
PRESETS = {
    "mute": [600, 3600, 86400, 604800, 2419200],
    "ban": [86400, 604800, 2592000],
    "giveaway": [3600, 86400, 259200, 604800],
    "slowmode": [0, 5, 30, 60, 300, 3600],
}
LIMITS = {"mute": 2419200, "ban": 31536000, "giveaway": 31536000, "slowmode": 21600}

_ZH_NAMES = {"d": "天", "h": "小时", "m": "分钟", "s": "秒"}
_EN_NAMES = {"d": "day", "h": "hour", "m": "minute", "s": "second"}


def parse_duration(s: str, limit: Optional[int] = MAX_SECONDS) -> Optional[int]:
    """解析时长 → 秒数；非法、单位重复、为 0 或超过 limit（默认 365 天，None 不限）返回 None。"""
    s = s.strip().lower()
    if not s or not _WHOLE.fullmatch(s):
        return None
    total = 0
    seen_units = set()
    for number, unit in _TOKEN.findall(s):
        unit = _UNITS[unit]
        if unit in seen_units:
            return None
        seen_units.add(unit)
        total += int(number) * _MULTIPLIERS[unit]
    if total <= 0 or (limit is not None and total > limit):
        return None
    return total


def _parts(seconds: int) -> list[tuple[int, str]]:
    parts = []
    for unit in ("d", "h", "m", "s"):
        n, seconds = divmod(seconds, _MULTIPLIERS[unit])
        if n:
            parts.append((n, unit))
    return parts


def canonical(seconds: int) -> str:
    """规范写法，只用 d/h/m/s：5400 → 1h30m，604800 → 7d；0 → "0"。"""
    return "".join(f"{n}{unit}" for n, unit in _parts(seconds)) or "0"


def label(seconds: int, zh: bool) -> str:
    """给人看的时长：1 小时 30 分钟 / 1 hour 30 minutes；0 为关闭 / Off。"""
    if seconds == 0:
        return "关闭" if zh else "Off"
    if zh:
        return " ".join(f"{n} {_ZH_NAMES[unit]}" for n, unit in _parts(seconds))
    return " ".join(f"{n} {_EN_NAMES[unit]}{'' if n == 1 else 's'}" for n, unit in _parts(seconds))


def suggest(current: str, presets: Sequence[int], max_seconds: int, zh: bool) -> list[tuple[str, str]]:
    """补全候选 (显示文字, 值)：空输入给常用值；纯数字铺开成分钟/小时/天/周；能解析的放第一个再接常用值。"""
    text = (current or "").strip()
    if text.isdigit():
        n = int(text)
        candidates = [n * 60, n * 3600, n * 86400, n * 604800] if n else ([0] if 0 in presets else [])
    else:
        parsed = parse_duration(text, limit=None) if text else None
        candidates = ([parsed] if parsed else []) + list(presets)
    result, seen = [], set()
    for seconds in candidates:
        if seconds in seen or seconds > max_seconds or (seconds == 0 and 0 not in presets):
            continue
        seen.add(seconds)
        result.append((label(seconds, zh), canonical(seconds)))
        if len(result) >= 25:
            break
    return result


def format_duration(seconds: int) -> str:
    """秒数 → 中文时长文本（有天数时不显示秒）。"""
    parts = []
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        parts.append(f"{d}天")
    if h:
        parts.append(f"{h}小时")
    if m:
        parts.append(f"{m}分钟")
    if s and not d:
        parts.append(f"{s}秒")
    return " ".join(parts) or "0秒"
