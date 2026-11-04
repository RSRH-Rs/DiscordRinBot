import json
import os
from datetime import datetime, timezone

import pytest

from rincore import cases, embeds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _total(e):
    parts = [e.get("title", ""), e.get("description", "")]
    parts += [f["name"] + f["value"] for f in e.get("fields", [])]
    parts += [e.get("footer", {}).get("text", ""), e.get("author", {}).get("name", "")]
    return sum(len(p) for p in parts)


def test_colors():
    assert embeds.COLORS == {
        "info": 0xEB8BAC,
        "success": 0x3BA55D,
        "warning": 0xF0B232,
        "error": 0xED4245,
        "log": 0x80848E,
    }


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        embeds.build("pink", "x")


def test_truncates_description():
    e = embeds.build("info", "t", "d" * 5000)
    assert len(e["description"]) == 4096 and e["description"].endswith("…")


def test_truncates_each_part():
    e = embeds.build(
        "info", "t" * 300, fields=[("n" * 300, "v" * 2000)], footer="f" * 3000, author="a" * 300
    )
    assert len(e["title"]) == 256 and e["title"].endswith("…")
    assert len(e["fields"][0]["name"]) == 256 and len(e["fields"][0]["value"]) == 1024
    assert len(e["footer"]["text"]) == 2048 and len(e["author"]["name"]) == 256


def test_keeps_25_fields_and_trims_description_to_6000():
    e = embeds.build("info", "t", "d" * 4000, fields=[(f"字段{i}", "v" * 100) for i in range(30)])
    assert len(e["fields"]) == 25
    assert e["fields"][-1]["name"] == "字段24"
    assert len(e["description"]) < 4000 and e["description"].endswith("…")
    assert _total(e) <= 6000


def test_drops_trailing_fields_over_6000():
    e = embeds.build("info", "t", "d" * 4000, fields=[(f"字段{i}", "v" * 1000) for i in range(25)])
    assert "description" not in e
    assert [f["name"] for f in e["fields"]] == [f"字段{i}" for i in range(len(e["fields"]))]
    assert _total(e) <= 6000


def test_skips_empty_fields_and_defaults_inline():
    e = embeds.build(
        "log", "t", fields=[("原因", ""), ("成员", None), ("", "x"), ("时长", "1 小时"), ("内容", "长", False)]
    )
    assert e["fields"] == [
        {"name": "时长", "value": "1 小时", "inline": True},
        {"name": "内容", "value": "长", "inline": False},
    ]


def test_omits_missing_parts():
    assert embeds.build("info", "t") == {"color": 0xEB8BAC, "title": "t"}


def test_footer_author_url_and_icons():
    e = embeds.build("info", "t", url="https://x", footer="f", footer_icon="https://f", author="a", author_icon="https://a")
    assert e["url"] == "https://x"
    assert e["footer"] == {"text": "f", "icon_url": "https://f"}
    assert e["author"] == {"name": "a", "icon_url": "https://a"}


def test_timestamp_only_when_given():
    assert "timestamp" not in embeds.build("info", "t")
    e = embeds.build("log", "t", timestamp=datetime(2026, 11, 4, tzinfo=timezone.utc))
    assert e["timestamp"].startswith("2026-11-04T")


EVENTS = {
    "success": "member_join member_unban member_timeout_end channel_create role_create unban unmute",
    "warning": "message_edit nick_change member_roles channel_update role_update guild_update member_timeout warn mute automod",
    "error": "message_delete message_bulk_delete member_kick member_ban channel_delete role_delete kick ban tempban purge",
    "log": "member_leave voice_join voice_leave voice_move emoji_update clearwarns",
}


def test_event_kinds():
    for kind, events in EVENTS.items():
        for event in events.split():
            assert embeds.event_kind(event) == kind, event
    with pytest.raises(KeyError):
        embeds.event_kind("nope")


def test_log_levels():
    assert embeds.LOG_LEVELS == {
        "error": ("error", "错误"),
        "warning": ("warning", "警告"),
        "config": ("success", "配置变更"),
        "info": ("log", "信息"),
    }


def test_giveaway_running():
    e = embeds.giveaway_running("Nitro", 2, 1800000000, host_id=5, role_id=7)
    assert e["color"] == 0xEB8BAC
    assert e["title"] == "抽奖：Nitro"
    assert [(f["name"], f["value"], f["inline"]) for f in e["fields"]] == [
        ("中奖人数", "2 人", True),
        ("结束时间", "<t:1800000000:R>（<t:1800000000:f>）", True),
        ("发起人", "<@5>", True),
        ("参加条件", "需要 <@&7>", True),
    ]
    assert e["footer"] == {"text": "点下方按钮参加"}
    bare = embeds.giveaway_running("Nitro", 1, 1800000000)
    assert [f["name"] for f in bare["fields"]] == ["中奖人数", "结束时间"]


def test_giveaway_long_prize_still_fits():
    e = embeds.giveaway_running("奖" * 300, 1, 1800000000)
    assert len(e["title"]) == 256 and e["title"].endswith("…")


def test_giveaway_ended():
    e = embeds.giveaway_ended("Nitro", 3, [1, 2])
    assert e["color"] == 0x3BA55D
    assert e["title"] == "抽奖结束：Nitro"
    assert e["fields"] == [{"name": "中奖者", "value": "<@1>、<@2>", "inline": False}]
    assert e["footer"] == {"text": "抽奖 #3"}
    empty = embeds.giveaway_ended("Nitro", 3, [])
    assert empty["color"] == 0x80848E
    assert empty["title"] == "抽奖结束：Nitro"
    assert empty["description"] == "没有符合条件的参加者。"
    assert "fields" not in empty
    assert empty["footer"] == {"text": "抽奖 #3"}


def test_action_names_match_dashboard():
    with open(os.path.join(ROOT, "website", "i18n", "zh.json"), encoding="utf-8") as f:
        assert cases.ACTION_NAMES == json.load(f)["moderation"]["action"]
