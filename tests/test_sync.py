import time

import pytest

from rincore import sync


async def test_notify_then_poll_dispatches_once(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher.start()
    try:
        seen = []

        async def cb(guild_id):
            seen.append(guild_id)

        watcher.register("automod", cb)
        await sync.notify("automod", 1, path=path)
        await sync.notify("automod", 1, path=path)
        await sync.notify("automod", 2, path=path)

        assert await watcher.poll_once() == 2
        assert sorted(seen) == [1, 2]
        assert set(seen) == {1, 2}
        assert await watcher.poll_once() == 0
    finally:
        await watcher.stop()


async def test_watcher_starts_after_existing_rows(tmp_path):
    path = str(tmp_path / "sync.db")
    await sync.notify("automod", 1, path=path)
    watcher = sync.ChangeWatcher(path=path)
    await watcher.start()
    try:
        assert await watcher.poll_once() == 0
    finally:
        await watcher.stop()


async def test_failing_callback_does_not_block_others(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher.start()
    try:
        called = []

        async def bad(guild_id):
            raise RuntimeError("boom")

        async def good(guild_id):
            called.append(guild_id)

        watcher.register("automod", bad)
        watcher.register("serverlog", good)
        await sync.notify("automod", 1, path=path)
        await sync.notify("serverlog", 1, path=path)

        await watcher.poll_once()
        assert called == [1]
        assert await watcher.poll_once() == 0
    finally:
        await watcher.stop()


async def test_unregister_stops_dispatch(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher.start()
    try:
        called = []

        async def cb(guild_id):
            called.append(guild_id)

        watcher.register("welcome", cb)
        watcher.unregister("welcome", cb)
        await sync.notify("welcome", 5, path=path)
        await watcher.poll_once()
        assert called == []
    finally:
        await watcher.stop()


async def test_prune_removes_old_rows(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher.start()
    try:
        await sync.notify("global", 0, path=path)
        assert await watcher.prune(now=time.time() + 86401) == 1
        assert await watcher.prune(now=time.time() + 86401) == 0
    finally:
        await watcher.stop()


async def test_prune_keeps_recent_rows(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher.start()
    try:
        await sync.notify("global", 0, path=path)
        assert await watcher.prune() == 0
    finally:
        await watcher.stop()


async def test_unknown_module_rejected(tmp_path):
    with pytest.raises(ValueError):
        await sync.notify("nope", 1, path=str(tmp_path / "sync.db"))
