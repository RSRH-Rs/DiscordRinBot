"""RinBot 共用消息模板：生成 Discord embed 的 JSON（机器人与网站共用，不依赖 discord.py）。

五种消息各一个颜色；标题、正文、字段、页脚、作者行按 Discord 上限截断，超长以"…"结尾。
"""
from datetime import datetime
from typing import Iterable, Optional, Sequence

COLORS = {
    "info": 0xEB8BAC,  # 小凛粉：查询、列表、面板
    "success": 0x3BA55D,  # 完成绿
    "warning": 0xF0B232,  # 注意黄：冷却、维护、部分完成
    "error": 0xED4245,  # 失败红：报错、被拦下
    "log": 0x80848E,  # 日志灰：一般事件
}

TITLE_MAX, DESCRIPTION_MAX = 256, 4096
FIELD_NAME_MAX, FIELD_VALUE_MAX, FIELDS_MAX = 256, 1024, 25
FOOTER_MAX, AUTHOR_MAX, TOTAL_MAX = 2048, 256, 6000

# 日志按事件分色：新增/恢复=成功，修改/警告/限制=注意，删除/处罚=失败，其他=日志
_EVENTS = {
    "success": "member_join member_unban member_timeout_end channel_create role_create unban unmute",
    "warning": "message_edit nick_change member_roles channel_update role_update guild_update "
    "member_timeout warn mute automod",
    "error": "message_delete message_bulk_delete member_kick member_ban channel_delete role_delete "
    "kick ban tempban purge",
    "log": "member_leave voice_join voice_leave voice_move emoji_update clearwarns",
}
EVENT_KINDS = {event: kind for kind, events in _EVENTS.items() for event in events.split()}

# 系统日志级别 -> (消息种类, 中文名)
LOG_LEVELS = {
    "error": ("error", "错误"),
    "warning": ("warning", "警告"),
    "config": ("success", "配置变更"),
    "info": ("log", "信息"),
}


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def event_kind(event: str) -> str:
    """日志事件 -> 消息种类；未知事件抛 KeyError。"""
    return EVENT_KINDS[event]


def build(
    kind: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    fields: Iterable[tuple] = (),
    footer: Optional[str] = None,
    footer_icon: Optional[str] = None,
    author: Optional[str] = None,
    author_icon: Optional[str] = None,
    url: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> dict:
    """按模板生成 embed JSON。fields 每项为 (名称, 值) 或 (名称, 值, 是否并排)，名称或值为空的跳过。"""
    if kind not in COLORS:
        raise ValueError(f"unknown embed kind: {kind!r}")
    data: dict = {"color": COLORS[kind]}
    if title:
        data["title"] = _cut(str(title), TITLE_MAX)
    if url:
        data["url"] = url

    items = []
    for field in fields:
        name, value = field[0], field[1]
        inline = field[2] if len(field) > 2 else True
        if name is None or value is None or not str(name).strip() or not str(value).strip():
            continue
        items.append(
            {
                "name": _cut(str(name), FIELD_NAME_MAX),
                "value": _cut(str(value), FIELD_VALUE_MAX),
                "inline": bool(inline),
            }
        )
    items = items[:FIELDS_MAX]

    if footer:
        data["footer"] = {"text": _cut(str(footer), FOOTER_MAX)}
        if footer_icon:
            data["footer"]["icon_url"] = footer_icon
    if author:
        data["author"] = {"name": _cut(str(author), AUTHOR_MAX)}
        if author_icon:
            data["author"]["icon_url"] = author_icon
    if timestamp is not None:
        data["timestamp"] = timestamp.isoformat()

    # 总字数超过上限：先缩正文，正文缩完还超就从最后一个字段开始删
    fixed = len(data.get("title", "")) + len(data.get("footer", {}).get("text", ""))
    fixed += len(data.get("author", {}).get("name", ""))
    room = TOTAL_MAX - fixed - sum(len(f["name"]) + len(f["value"]) for f in items)
    if description and room > 1:
        data["description"] = _cut(str(description), min(DESCRIPTION_MAX, room))
    while items and fixed + sum(len(f["name"]) + len(f["value"]) for f in items) > TOTAL_MAX:
        items.pop()
    if items:
        data["fields"] = items
    return data


def giveaway_running(
    prize: str,
    winners: int,
    end_ts: int,
    *,
    host_id: Optional[int] = None,
    role_id: Optional[int] = None,
) -> dict:
    """进行中的抽奖消息（机器人 /giveaway start 与网页创建共用）。"""
    fields = [
        ("中奖人数", f"{winners} 人"),
        ("结束时间", f"<t:{end_ts}:R>（<t:{end_ts}:f>）"),
    ]
    if host_id:
        fields.append(("发起人", f"<@{host_id}>"))
    if role_id:
        fields.append(("参加条件", f"需要 <@&{role_id}>"))
    return build("info", f"抽奖：{prize}", fields=fields, footer="点下方按钮参加")


def giveaway_ended(prize: str, giveaway_id: int, winner_ids: Sequence[int]) -> dict:
    """开奖后的抽奖消息；没有中奖者时为日志色。"""
    if winner_ids:
        winners = "、".join(f"<@{uid}>" for uid in winner_ids)
        return build(
            "success",
            f"抽奖结束：{prize}",
            fields=[("中奖者", winners, False)],
            footer=f"抽奖 #{giveaway_id}",
        )
    return build("log", f"抽奖结束：{prize}", "没有符合条件的参加者。", footer=f"抽奖 #{giveaway_id}")
