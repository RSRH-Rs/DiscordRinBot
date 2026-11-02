"""RinBot 共享时长解析与格式化（moderation 与 giveaway 共用）。"""
import re
from typing import Optional

_MULTIPLIERS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
MAX_SECONDS = 365 * 86400


def parse_duration(s: str) -> Optional[int]:
    """解析时长字符串，如 1h, 30m, 2d, 1d12h → 秒数；非法、单位重复或超过 365 天返回 None。"""
    s = s.strip().lower()
    if not re.fullmatch(r"(?:\d+[dhms])+", s):
        return None
    total = 0
    seen_units = set()
    for number, unit in re.findall(r"(\d+)([dhms])", s):
        if unit in seen_units:
            return None
        seen_units.add(unit)
        total += int(number) * _MULTIPLIERS[unit]
    return total if 0 < total <= MAX_SECONDS else None


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
