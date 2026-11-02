import sys
import time
from types import ModuleType, SimpleNamespace

import discord
import pytest

# 线上 cogs 目录在 sys.path 上；测试里用桩模块代替 _botlog_helper
if "_botlog_helper" not in sys.modules:
    _stub = ModuleType("_botlog_helper")

    async def _audit(*args, **kwargs):
        pass

    _stub.audit = _audit
    sys.modules["_botlog_helper"] = _stub

from cogs import automod  # noqa: E402


class _Partial:
    def __init__(self, channel, mid):
        self.channel, self.mid = channel, mid

    async def delete(self):
        self.channel.single_deleted.append(self.mid)
        if self.mid in self.channel.fail_single:
            raise discord.HTTPException(SimpleNamespace(status=404, reason="x"), "gone")


class _Channel:
    def __init__(self, cid, bulk_error=None, fail_single=()):
        self.id = cid
        self.bulk_error = bulk_error
        self.fail_single = set(fail_single)
        self.bulk_deleted = []
        self.single_deleted = []

    async def delete_messages(self, objs):
        if self.bulk_error:
            raise self.bulk_error
        self.bulk_deleted.append([o.id for o in objs])

    def get_partial_message(self, mid):
        return _Partial(self, mid)


def _http_error():
    return discord.HTTPException(SimpleNamespace(status=400, reason="x"), "bad")


def _cog():
    return automod.AutoMod(SimpleNamespace())


async def test_spam_bulk_deletes_per_channel():
    a, b = _Channel(1), _Channel(2)
    guild = SimpleNamespace(get_channel_or_thread=lambda cid: {2: b}.get(cid))
    entries = [(1.0, 1, 10), (2.0, 1, 11), (3.0, 2, 20), (4.0, 1, 12)]
    await _cog()._delete_spam_messages(guild, entries, a)
    assert a.bulk_deleted == [[10, 11, 12]]
    # 单条消息不走批量接口
    assert b.bulk_deleted == [] and b.single_deleted == [20]


async def test_spam_falls_back_to_single_deletes_and_ignores_failures():
    a = _Channel(1, bulk_error=_http_error(), fail_single={11})
    guild = SimpleNamespace(get_channel_or_thread=lambda cid: None)
    entries = [(1.0, 1, 10), (2.0, 1, 11), (3.0, 1, 12)]
    await _cog()._delete_spam_messages(guild, entries, a)
    assert a.single_deleted == [10, 11, 12]


async def test_spam_skips_unknown_channel():
    a = _Channel(1)
    guild = SimpleNamespace(get_channel_or_thread=lambda cid: None)
    await _cog()._delete_spam_messages(guild, [(1.0, 9, 10), (2.0, 9, 11)], a)
    assert a.bulk_deleted == [] and a.single_deleted == []


def test_prune_drops_stale_users_and_empty_guilds():
    cog = _cog()
    now = time.time()
    cog._msg_cache[1][100] = [(now - 120, 5, 6)]  # 过期
    cog._msg_cache[1][101] = [(now - 120, 5, 6), (now - 5, 5, 7)]  # 最近一条还新
    cog._msg_cache[2][200] = [(now - 300, 5, 8)]  # 整个服务器过期
    cog._msg_cache[3][300] = []  # 空记录
    cog._repeat_cache[1][100] = [("hi", now - 120)]
    cog._repeat_cache[1][101] = [("hi", now - 1)]
    cutoff = now - 60
    cog._prune_cache(cog._msg_cache, 0, cutoff)
    cog._prune_cache(cog._repeat_cache, 1, cutoff)
    assert list(cog._msg_cache) == [1] and list(cog._msg_cache[1]) == [101]
    assert list(cog._repeat_cache) == [1] and list(cog._repeat_cache[1]) == [101]


class _Msg:
    def __init__(self, content, channel, mid=1):
        self.content = content
        self.id = mid
        self.channel = channel
        self.author = SimpleNamespace(
            bot=False,
            id=7,
            mention="@u",
            roles=[],
            guild_permissions=SimpleNamespace(manage_messages=False),
        )
        self.guild = SimpleNamespace(id=1)
        self.deleted = False

    async def delete(self):
        self.deleted = True


class _TalkChannel(_Channel):
    mention = "#c"

    async def send(self, *args, **kwargs):
        pass


def _cog_with(**cfg):
    cog = _cog()
    base = {
        "guild_id": 1, "enabled": 1, "anti_spam": 0, "anti_badword": 0,
        "anti_link": 0, "anti_caps": 0, "anti_repeat": 0,
    }
    base.update(cfg)
    cog._config_cache[1] = base
    logged = []

    async def _log(guild, embed):
        logged.append(embed)

    cog._log_action = _log
    return cog, logged


async def test_caps_logs_action():
    cog, logged = _cog_with(anti_caps=1, caps_threshold=70, caps_min_length=10)
    msg = _Msg("STOP SHOUTING AT EVERYONE", _TalkChannel(5))
    await cog.on_message(msg)
    assert msg.deleted
    assert [e.title for e in logged] == ["📢 大写轰炸"]


async def test_link_without_scheme_blocked_unless_whitelisted():
    cog, logged = _cog_with(anti_link=1, link_whitelist='["example.com"]')
    blocked = _Msg("join discord.gg/abc", _TalkChannel(5))
    await cog.on_message(blocked)
    assert blocked.deleted and [e.title for e in logged] == ["🔗 链接过滤"]
    allowed = _Msg("see cdn.example.com/x", _TalkChannel(5))
    await cog.on_message(allowed)
    assert not allowed.deleted


async def test_badword_whole_word_only():
    cog, logged = _cog_with(anti_badword=1, badwords='["ass"]')
    ok = _Msg("this is class", _TalkChannel(5))
    await cog.on_message(ok)
    assert not ok.deleted
    bad = _Msg("you ASS", _TalkChannel(5))
    await cog.on_message(bad)
    assert bad.deleted and [e.title for e in logged] == ["🚫 违禁词"]


async def test_spam_trigger_deletes_window_messages():
    cog, logged = _cog_with(anti_spam=1, spam_threshold=3, spam_interval=5)
    muted = []

    async def _mute(member, reason, duration):
        muted.append(reason)

    cog._mute_user = _mute
    channel = _TalkChannel(5)
    for mid in (1, 2, 3):
        await cog.on_message(_Msg("hi", channel, mid))
    assert channel.bulk_deleted == [[1, 2, 3]]
    assert muted == ["刷屏"]
    assert cog._msg_cache[1][7] == []


async def test_spam_chunks_more_than_100_messages():
    a = _Channel(1)
    guild = SimpleNamespace(get_channel_or_thread=lambda cid: None)
    entries = [(1.0, 1, 1000 + i) for i in range(201)]
    await _cog()._delete_spam_messages(guild, entries, a)
    assert [len(b) for b in a.bulk_deleted] == [100, 100]
    assert a.single_deleted == [1200]  # 末尾只剩 1 条时逐条删除


async def test_spam_non_http_error_does_not_skip_remaining_channels():
    a = _Channel(1, bulk_error=ConnectionError("net"))
    b = _Channel(2)
    guild = SimpleNamespace(get_channel_or_thread=lambda cid: {2: b}.get(cid))
    entries = [(1.0, 1, 10), (2.0, 1, 11), (3.0, 2, 20), (4.0, 2, 21)]
    await _cog()._delete_spam_messages(guild, entries, a)
    assert b.bulk_deleted == [[20, 21]]


async def test_spam_cleanup_crash_still_mutes():
    cog, logged = _cog_with(anti_spam=1, spam_threshold=3, spam_interval=5)
    muted = []

    async def _mute(member, reason, duration):
        muted.append(reason)

    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    cog._mute_user = _mute
    cog._delete_spam_messages = _boom
    channel = _TalkChannel(5)
    for mid in (1, 2, 3):
        await cog.on_message(_Msg("hi", channel, mid))
    assert muted == ["刷屏"]
    assert [e.title for e in logged] == ["🚨 刷屏检测"]
