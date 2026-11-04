import asyncio
import re
from types import SimpleNamespace

from cogs import botlog
from cogs._botlog_helper import check_component
from cogs.globalsettings import Block

DEV = 111
OTHER = 222


def test_error_id_format():
    assert re.fullmatch(r"[0-9A-F]{8}", botlog.new_error_id())


def _make_cog(monkeypatch, dev_guild=DEV):
    monkeypatch.setattr(botlog, "DEV_GUILD_ID", dev_guild)
    cog = botlog.BotLog(SimpleNamespace())
    calls = []

    async def fake_log(guild_id, level, title, description="", **fields):
        calls.append((guild_id, level, title, description, fields))

    cog.log = fake_log
    return cog, calls


def _boom():
    try:
        raise ValueError("secret /srv/rinbot/x.py")
    except ValueError as e:
        return e


def test_report_sends_traceback_to_dev_guild_only(monkeypatch):
    cog, calls = _make_cog(monkeypatch)
    exc = _boom()
    eid = asyncio.run(cog.report_exception(OTHER, "指令执行失败: /x", exc, 用户="@u"))
    assert re.fullmatch(r"[0-9A-F]{8}", eid)
    by_guild = {c[0]: c for c in calls}
    assert set(by_guild) == {DEV, OTHER}
    dev = by_guild[DEV]
    assert dev[1] == "error" and "Traceback" in dev[3] and eid in dev[2]
    assert dev[4]["来源服务器"] == OTHER
    other = by_guild[OTHER]
    assert eid in other[2]
    flat = other[2] + other[3] + " ".join(str(v) for v in other[4].values())
    assert "Traceback" not in flat and "secret" not in flat and ".py" not in flat


def test_report_in_dev_guild_posts_once(monkeypatch):
    cog, calls = _make_cog(monkeypatch)
    asyncio.run(cog.report_exception(DEV, "t", _boom()))
    assert len(calls) == 1 and calls[0][0] == DEV and "Traceback" in calls[0][3]


def test_report_without_guild_goes_to_dev_only(monkeypatch):
    cog, calls = _make_cog(monkeypatch)
    asyncio.run(cog.report_exception(None, "t", _boom()))
    assert [c[0] for c in calls] == [DEV]


def test_report_never_raises_and_prints_traceback(monkeypatch, capsys):
    cog, _ = _make_cog(monkeypatch)

    async def broken(*a, **k):
        raise RuntimeError("send failed")

    cog.log = broken
    eid = asyncio.run(cog.report_exception(OTHER, "t", _boom()))
    out = capsys.readouterr().out
    assert eid in out and "Traceback" in out


def test_same_exception_gets_one_id_and_one_report(monkeypatch):
    cog, calls = _make_cog(monkeypatch)
    exc = _boom()
    a = asyncio.run(cog.report_exception(OTHER, "t", exc))
    n = len(calls)
    b = asyncio.run(cog.report_exception(OTHER, "t", exc))
    assert a == b and len(calls) == n


# ─── check_component ───


class _Resp:
    def __init__(self, done=False):
        self.done = done
        self.sent = []

    def is_done(self):
        return self.done

    async def send_message(self, *, embed, **kw):
        self.sent.append((embed.title, kw))


class _Follow:
    def __init__(self):
        self.sent = []

    async def send(self, *, embed, **kw):
        self.sent.append((embed.title, kw))


def _interaction(done=False):
    return SimpleNamespace(
        user=SimpleNamespace(id=5), response=_Resp(done), followup=_Follow()
    )


def _bot(reason, present=True):
    gs = SimpleNamespace(blocked_reason=lambda uid, cmd=None: reason)
    return SimpleNamespace(get_cog=lambda name: gs if present else None)


def test_check_component_fails_open_without_cog():
    i = _interaction()
    assert asyncio.run(check_component(_bot(None, present=False), i)) is True
    assert i.response.sent == []


def test_check_component_allows():
    assert asyncio.run(check_component(_bot(None), _interaction())) is True


def test_check_component_blacklist_message():
    i = _interaction()
    assert asyncio.run(check_component(_bot(Block("blacklist")), i)) is False
    assert i.response.sent == [("你现在不能使用这个功能", {"ephemeral": True})]


def test_check_component_maintenance_message_via_followup():
    i = _interaction(done=True)
    assert asyncio.run(check_component(_bot(Block("maintenance", "维护中")), i)) is False
    assert i.followup.sent == [("小凛正在维护", {"ephemeral": True})]


def test_check_component_disabled_message():
    i = _interaction()
    assert asyncio.run(check_component(_bot(Block("disabled")), i)) is False
    assert i.response.sent == [("这条指令已停用", {"ephemeral": True})]


def test_check_component_swallows_send_errors():
    i = _interaction()

    async def bad(*a, **k):
        raise RuntimeError("x")

    i.response.send_message = bad
    assert asyncio.run(check_component(_bot(Block("blacklist")), i)) is False
