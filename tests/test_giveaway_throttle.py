import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest

if "_botlog_helper" not in sys.modules:
    _stub = ModuleType("_botlog_helper")

    async def _audit(*args, **kwargs):
        pass

    _stub.audit = _audit
    sys.modules["_botlog_helper"] = _stub

from cogs import giveaway  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "gw.db")
    monkeypatch.setattr(giveaway, "DB_PATH", path)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE giveaways (id INTEGER PRIMARY KEY, ended INTEGER DEFAULT 0)")
    con.execute("CREATE TABLE giveaway_entries (giveaway_id INTEGER, user_id INTEGER)")
    con.execute("INSERT INTO giveaways (id, ended) VALUES (1, 0), (2, 1)")
    con.executemany(
        "INSERT INTO giveaway_entries VALUES (?, ?)", [(1, 10), (1, 11), (1, 12), (2, 10)]
    )
    con.commit()
    con.close()
    return path


class _Message:
    def __init__(self, error=None):
        self.views = []
        self.error = error

    async def edit(self, view=None):
        if self.error:
            raise self.error
        self.views.append(view)


async def test_refresh_uses_current_count_and_exact_label(db):
    cog = giveaway.Giveaway(SimpleNamespace())
    msg = _Message()
    await cog._refresh_entry_label(msg, 1)
    assert [v.enter.label for v in msg.views] == ["🎉 参加抽奖! (3人)"]


async def test_refresh_skips_ended_giveaway(db):
    cog = giveaway.Giveaway(SimpleNamespace())
    msg = _Message()
    await cog._refresh_entry_label(msg, 2)
    assert msg.views == []


async def test_refresh_ignores_edit_errors(db):
    cog = giveaway.Giveaway(SimpleNamespace())
    for err in (
        giveaway.discord.NotFound(SimpleNamespace(status=404, reason="x"), "x"),
        giveaway.discord.Forbidden(SimpleNamespace(status=403, reason="x"), "x"),
        giveaway.discord.HTTPException(SimpleNamespace(status=500, reason="x"), "x"),
    ):
        await cog._refresh_entry_label(_Message(error=err), 1)  # 不抛异常


async def test_click_only_schedules_edit(db):
    """点击回调不直接编辑消息，而是交给 Debouncer；同一消息连点只留最后一次"""
    scheduled = []
    cog = SimpleNamespace(
        label_debouncer=SimpleNamespace(schedule=lambda key, f: scheduled.append((key, f))),
        _refresh_entry_label=None,
    )
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE giveaways ADD COLUMN message_id INTEGER DEFAULT 0")
    con.execute("ALTER TABLE giveaways ADD COLUMN restrict_role INTEGER DEFAULT 0")
    con.execute("UPDATE giveaways SET message_id = 555 WHERE id = 1")
    con.commit()
    con.close()

    sent = []

    class _Resp:
        async def send_message(self, text, ephemeral=False):
            sent.append(text)

    edits = []

    async def _edit(**kwargs):
        edits.append(kwargs)

    interaction = SimpleNamespace(
        message=SimpleNamespace(id=555, edit=_edit),
        user=SimpleNamespace(id=77),
        response=_Resp(),
        client=SimpleNamespace(get_cog=lambda name: cog if name == "Giveaway" else None),
    )
    view = giveaway.GiveawayEntryButton()
    await view.enter.callback(interaction)
    assert sent == ["✅ 你已成功参加抽奖！当前参与人数: 4"]
    assert edits == []
    assert [k for k, _ in scheduled] == [555]
