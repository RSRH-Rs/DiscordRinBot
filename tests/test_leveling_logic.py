from cogs.leveling import prune_cooldowns


def test_prune_noop_under_limit():
    cooldowns = {(1, i): 0.0 for i in range(10)}
    prune_cooldowns(cooldowns, now=1000.0, ttl=60)
    assert len(cooldowns) == 10


def test_prune_removes_stale_when_over_limit():
    cooldowns = {(1, i): 0.0 for i in range(5001)}
    cooldowns[(2, 1)] = 999.0
    prune_cooldowns(cooldowns, now=1000.0, ttl=60)
    assert cooldowns == {(2, 1): 999.0}


def test_prune_keeps_entries_within_ttl():
    cooldowns = {(1, i): 990.0 for i in range(5001)}
    prune_cooldowns(cooldowns, now=1000.0, ttl=60)
    assert len(cooldowns) == 5001
