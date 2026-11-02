import asyncio

from guild_ids import collect_guild_ids


def _make_fetch(ids, page_size=200):
    """模拟 Discord：按 id 升序，after 之后最多返回 page_size 个。"""
    ids = sorted(ids)
    calls = []

    async def fetch_page(after):
        calls.append(after)
        rest = [i for i in ids if after is None or i > after]
        return [{"id": str(i)} for i in rest[:page_size]]

    return fetch_page, calls


def test_collects_all_pages():
    fetch, calls = _make_fetch(range(1, 451))
    result = asyncio.run(collect_guild_ids(fetch))
    assert result == set(range(1, 451))
    assert calls == [None, 200, 400]


def test_exact_multiple_of_page_size():
    fetch, calls = _make_fetch(range(1, 401))
    result = asyncio.run(collect_guild_ids(fetch))
    assert result == set(range(1, 401))
    assert len(calls) == 3


def test_single_short_page():
    fetch, calls = _make_fetch(range(1, 6))
    result = asyncio.run(collect_guild_ids(fetch))
    assert result == set(range(1, 6))
    assert len(calls) == 1


def test_empty_first_page():
    fetch, calls = _make_fetch([])
    assert asyncio.run(collect_guild_ids(fetch)) == set()
    assert len(calls) == 1


def test_stops_when_last_id_does_not_advance():
    calls = []

    async def stuck(after):
        calls.append(after)
        return [{"id": str(i)} for i in range(1, 201)]  # 永远返回同一整页

    result = asyncio.run(collect_guild_ids(stuck))
    assert result == set(range(1, 201))
    assert len(calls) == 2  # 第二次返回的最后 id 没有前进，立即停止
