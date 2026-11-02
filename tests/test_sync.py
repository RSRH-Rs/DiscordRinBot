import asyncio
import os
import time

import pytest

from rincore import sync


async def test_notify_then_poll_dispatches_once(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher._init()  # 不启动后台循环，避免与手动 poll_once/prune 竞争
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
    await watcher._init()  # 不启动后台循环，避免与手动 poll_once/prune 竞争
    try:
        assert await watcher.poll_once() == 0
    finally:
        await watcher.stop()


async def test_failing_callback_does_not_block_others(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher._init()  # 不启动后台循环，避免与手动 poll_once/prune 竞争
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
    await watcher._init()  # 不启动后台循环，避免与手动 poll_once/prune 竞争
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
    await watcher._init()  # 不启动后台循环，避免与手动 poll_once/prune 竞争
    try:
        await sync.notify("global", 0, path=path)
        assert await watcher.prune(now=time.time() + 86401) == 1
        assert await watcher.prune(now=time.time() + 86401) == 0
    finally:
        await watcher.stop()


async def test_prune_keeps_recent_rows(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path)
    await watcher._init()  # 不启动后台循环，避免与手动 poll_once/prune 竞争
    try:
        await sync.notify("global", 0, path=path)
        assert await watcher.prune() == 0
    finally:
        await watcher.stop()


async def test_unknown_module_rejected(tmp_path):
    with pytest.raises(ValueError):
        await sync.notify("nope", 1, path=str(tmp_path / "sync.db"))


async def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


async def test_start_on_unusable_path_does_not_raise(tmp_path):
    bad = tmp_path / "sync.db"
    bad.mkdir()  # 目录无法作为 SQLite 库打开
    watcher = sync.ChangeWatcher(path=str(bad), interval=0.01)
    await watcher.start()  # 不应抛出
    await watcher.stop()


async def test_loop_survives_raising_iteration(tmp_path):
    path = str(tmp_path / "sync.db")
    watcher = sync.ChangeWatcher(path=path, interval=0.01)
    seen = []

    async def cb(guild_id):
        seen.append(guild_id)

    watcher.register("global", cb)
    real_poll = watcher.poll_once
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return await real_poll()

    # 回调收到后把轮询循环停在纯 await 上，stop() 的取消才不会落在 aiosqlite 调用中间
    # （否则遗留的 aiosqlite 工作线程会向已关闭的事件循环投递结果）
    parked = asyncio.Event()
    gate = asyncio.Event()

    async def parking():
        n = await flaky()
        if seen == [0]:
            parked.set()
            await gate.wait()
        return n

    watcher.poll_once = parking
    await watcher.start()
    try:
        await sync.notify("global", 0, path=path)
        await asyncio.wait_for(parked.wait(), 5)
        assert seen == [0]
        assert calls >= 2
    finally:
        await watcher.stop()


async def test_failed_init_retries_and_does_not_replay(tmp_path):
    path = tmp_path / "sync.db"
    path.mkdir()
    watcher = sync.ChangeWatcher(path=str(path), interval=0.01)
    seen = []

    async def cb(guild_id):
        seen.append(guild_id)

    watcher.register("automod", cb)

    # 收到回调后再多轮询几次确认没有回放，然后把循环停在纯 await 上，
    # 让 stop() 的取消不落在 aiosqlite 调用中间
    real_poll = watcher.poll_once
    parked = asyncio.Event()
    gate = asyncio.Event()
    polls_after = 0

    async def parking():
        nonlocal polls_after
        n = await real_poll()
        if seen == [2]:
            polls_after += 1
            if polls_after >= 3:
                parked.set()
                await gate.wait()
        return n

    watcher.poll_once = parking
    await watcher.start()  # 初始化失败
    try:
        # 在别处准备一个已有记录的库，再原子地换到目标路径
        staged = str(tmp_path / "staged.db")
        await sync.notify("automod", 1, path=staged)
        path.rmdir()
        os.replace(staged, str(path))

        assert await _wait_for(lambda: watcher._ready)
        await sync.notify("automod", 2, path=str(path))
        await asyncio.wait_for(parked.wait(), 5)
        assert seen == [2]  # 初始化前已存在的记录 (guild 1) 没有被回放
    finally:
        await watcher.stop()
