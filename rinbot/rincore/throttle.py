"""RinBot 节流/合并工具。"""
import asyncio
from collections.abc import Awaitable, Callable, Hashable


class Debouncer:
    """同一 key 在 delay 秒窗口内的多次调度只在窗口结束时执行最后一次的 factory。

    窗口从该 key 的第一次调度开始计时，之后的调度只替换 factory、不延长窗口，
    因此持续有调度时也最多每 delay 秒执行一次（不会被无限推迟）。
    """

    def __init__(self, delay: float):
        self.delay = delay
        self._factories: dict[Hashable, Callable[[], Awaitable[None]]] = {}
        self._tasks: dict[Hashable, asyncio.Task] = {}  # 持有引用，避免任务被垃圾回收

    def schedule(self, key: Hashable, coro_factory: Callable[[], Awaitable[None]]) -> None:
        self._factories[key] = coro_factory
        if key not in self._tasks:
            self._tasks[key] = asyncio.get_running_loop().create_task(self._run(key))

    async def _run(self, key: Hashable) -> None:
        await asyncio.sleep(self.delay)
        factory = self._factories.pop(key, None)
        self._tasks.pop(key, None)
        if factory is None:
            return
        try:
            await factory()
        except Exception as e:
            print(f"[Debouncer] {key!r}: {e}")

    def cancel(self, key: Hashable) -> None:
        """取消某个 key 尚未执行的调度（没有则忽略）。"""
        self._factories.pop(key, None)
        task = self._tasks.pop(key, None)
        if task is not None:
            task.cancel()

    def cancel_all(self) -> None:
        """取消所有尚未执行的调度（cog 卸载时调用）。"""
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        self._factories.clear()
