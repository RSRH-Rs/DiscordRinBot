"""Bot 所在服务器 id 的分页收集（纯逻辑，不依赖 Quart / aiohttp，便于单元测试）。"""
from typing import Awaitable, Callable, List, Optional, Set


async def collect_guild_ids(
    fetch_page: Callable[[Optional[int]], Awaitable[List[dict]]],
    page_size: int = 200,
) -> Set[int]:
    """反复调用 fetch_page(after) 直到返回数 < page_size，返回全部 guild id。

    after 为上一页最后一个 id（首页为 None）。若整页的最后 id 没有前进则停止，避免死循环。
    """
    ids: Set[int] = set()
    after: Optional[int] = None
    while True:
        page = await fetch_page(after)
        ids.update(int(g["id"]) for g in page)
        if len(page) < page_size:
            break
        last = int(page[-1]["id"])
        if after is not None and last <= after:
            break
        after = last
    return ids
