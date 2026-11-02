import asyncio

from rincore import throttle


async def test_debounce_coalesces():
    d = throttle.Debouncer(0.05)
    calls = []

    def make(i):
        async def run():
            calls.append(i)

        return run

    for i in range(10):
        d.schedule("k", lambda i=i: make(i)())
    await asyncio.sleep(0.1)
    assert calls == [9]


async def test_debounce_separate_keys():
    d = throttle.Debouncer(0.05)
    calls = []

    def make(i):
        async def run():
            calls.append(i)

        return run

    d.schedule("a", lambda: make("a")())
    d.schedule("b", lambda: make("b")())
    await asyncio.sleep(0.1)
    assert sorted(calls) == ["a", "b"]


async def test_debounce_window_is_not_extended_by_new_calls():
    # 持续有新调度时也必须在窗口结束时执行（节流，而不是无限推迟）
    d = throttle.Debouncer(0.1)
    calls = []

    async def run():
        calls.append(1)

    d.schedule("k", run)
    for _ in range(4):
        await asyncio.sleep(0.04)
        d.schedule("k", run)
    assert calls  # 约 0.16s 时已执行过一次
    await asyncio.sleep(0.15)  # 让最后一个窗口跑完，避免遗留挂起任务


async def test_debounce_schedules_again_after_run():
    d = throttle.Debouncer(0.03)
    calls = []

    async def run():
        calls.append(1)

    d.schedule("k", run)
    await asyncio.sleep(0.08)
    d.schedule("k", run)
    await asyncio.sleep(0.08)
    assert calls == [1, 1]


async def test_debounce_cancel_all_drops_pending():
    d = throttle.Debouncer(0.05)
    calls = []

    async def run():
        calls.append(1)

    d.schedule("k", run)
    d.cancel_all()
    await asyncio.sleep(0.1)
    assert calls == []


async def test_debounce_swallows_factory_errors():
    d = throttle.Debouncer(0.03)
    calls = []

    async def boom():
        raise RuntimeError("x")

    async def ok():
        calls.append(1)

    d.schedule("k", boom)
    await asyncio.sleep(0.08)
    d.schedule("k", ok)
    await asyncio.sleep(0.08)
    assert calls == [1]
