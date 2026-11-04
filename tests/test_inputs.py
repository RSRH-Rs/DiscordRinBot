import asyncio
from types import SimpleNamespace

import discord
import pytest

from _inputs import BadDuration, Duration, DurationTooLong, choices, is_zh
from _messages import Notice
from cogs.errors import notice_for


def _convert(kind, text):
    return asyncio.run(Duration(kind)().convert(None, text))


def test_duration_converter():
    assert _convert("mute", "10m") == 600
    assert _convert("mute", "1小时") == 3600
    with pytest.raises(BadDuration):
        _convert("mute", "刷屏")
    with pytest.raises(DurationTooLong) as too_long:
        _convert("mute", "29d")
    assert too_long.value.limit == 2419200


def test_slowmode_accepts_off():
    for text in ("0", "关闭", "off", "OFF"):
        assert _convert("slowmode", text) == 0
    assert _convert("slowmode", "30s") == 30
    with pytest.raises(DurationTooLong):
        _convert("slowmode", "7h")
    with pytest.raises(BadDuration):
        _convert("mute", "0")


def test_choices_filters_and_caps():
    items = [(f"歌曲 {i}", i) for i in range(40)]
    got = choices(items, "")
    assert len(got) == 25 and got[0].name == "歌曲 0" and got[0].value == 0
    filtered = choices([("Nitro", "1"), ("nitro 年卡", "2"), ("皮肤", "3")], "NITRO")
    assert [c.value for c in filtered] == ["1", "2"]


def test_is_zh():
    assert is_zh(SimpleNamespace(locale=discord.Locale.chinese))
    assert is_zh(SimpleNamespace(locale=discord.Locale.taiwan_chinese))
    assert not is_zh(SimpleNamespace(locale=discord.Locale.american_english))


def test_duration_notices():
    assert notice_for(BadDuration("x")) == Notice(
        "error", "时长格式不对", "可以写 10m、1h30m、2d、1w，或者 10分钟、1小时、2天。"
    )
    assert notice_for(DurationTooLong(2419200)) == Notice("error", "时长太长了", "最长 28 天。")
