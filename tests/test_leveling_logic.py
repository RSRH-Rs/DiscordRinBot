import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs import leveling
from cogs.leveling import Leveling, due_role_ids, parse_rewards, prune_cooldowns

GID = 123
USER = 7


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


def test_parse_rewards_reads_pairs():
    assert parse_rewards('[{"level": 5, "role_id": "42"}]') == [(5, 42)]


@pytest.mark.parametrize(
    "raw", ["", None, "not json", "{}", '[{"level": "x"}]', '[{"role_id": "1"}]', "[1]"]
)
def test_parse_rewards_rejects_bad_content(raw):
    assert parse_rewards(raw) == []


@pytest.fixture
async def cog(monkeypatch, tmp_path):
    monkeypatch.setattr(leveling, "DB_PATH", str(tmp_path / "leveling.db"))
    instance = Leveling(SimpleNamespace(change_watcher=None))
    await instance.cog_load()
    return instance


def _db(query, *params):
    connection = sqlite3.connect(leveling.DB_PATH)
    try:
        with connection:
            return connection.execute(query, params).fetchall()
    finally:
        connection.close()


async def save_config(cog, enabled=1, mode="here", channel=0, rewards="[]", gid=GID):
    _db(
        "INSERT OR REPLACE INTO level_config VALUES (?, ?, ?, ?, ?)",
        gid, enabled, mode, channel, rewards,
    )
    await cog.reload_guild(gid)


def set_progress(cog, level=0, xp=None):
    """Store a member one message away from the next level unless xp is given."""
    if xp is None:
        xp = cog.get_total_xp_for_level(level + 1) - 1
    _db("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?)", GID, USER, xp, level)


def stored_user():
    rows = _db("SELECT xp, level FROM users WHERE guild_id=? AND user_id=?", GID, USER)
    return rows[0] if rows else None


@pytest.fixture
def chosen_channel():
    return SimpleNamespace(send=AsyncMock())


@pytest.fixture
def message(chosen_channel):
    guild = SimpleNamespace(
        id=GID,
        get_channel=MagicMock(return_value=chosen_channel),
    )
    author = SimpleNamespace(id=USER, bot=False, mention="<@7>")
    return SimpleNamespace(author=author, guild=guild, channel=SimpleNamespace(send=AsyncMock()))


async def test_unconfigured_guild_keeps_current_behaviour(cog, message):
    set_progress(cog)
    await cog.on_message(message)
    message.channel.send.assert_awaited_once_with("🎉 恭喜 **<@7>**！你升级到了 **Level 1**！✨")
    assert stored_user()[1] == 1


async def test_disabled_guild_gains_no_xp(cog, message):
    await save_config(cog, enabled=0)
    await cog.on_message(message)
    assert stored_user() is None
    assert cog.cooldowns == {}
    message.channel.send.assert_not_awaited()


async def test_notice_goes_to_chosen_channel(cog, message, chosen_channel):
    await save_config(cog, mode="channel", channel=77)
    set_progress(cog)
    await cog.on_message(message)
    message.guild.get_channel.assert_called_once_with(77)
    chosen_channel.send.assert_awaited_once()
    message.channel.send.assert_not_awaited()


async def test_missing_channel_sends_nothing_and_keeps_xp(cog, message, chosen_channel):
    await save_config(cog, mode="channel", channel=77)
    message.guild.get_channel.return_value = None
    set_progress(cog)
    await cog.on_message(message)
    chosen_channel.send.assert_not_awaited()
    message.channel.send.assert_not_awaited()
    assert stored_user()[1] == 1


async def test_notice_off_sends_nothing(cog, message, chosen_channel):
    await save_config(cog, mode="off")
    set_progress(cog)
    await cog.on_message(message)
    chosen_channel.send.assert_not_awaited()
    message.channel.send.assert_not_awaited()
    assert stored_user()[1] == 1


async def test_notice_failure_keeps_xp(cog, message):
    message.channel.send.side_effect = discord.HTTPException(
        SimpleNamespace(status=500, reason="boom"), "boom"
    )
    set_progress(cog)
    await cog.on_message(message)
    assert stored_user()[1] == 1


async def test_reload_guild_updates_and_clears_cache(cog):
    await save_config(cog, enabled=0, mode="off", rewards='[{"level": 5, "role_id": "42"}]')
    assert cog.get_config(GID) == {
        "enabled": False, "notify_mode": "off", "notify_channel": 0, "rewards": [(5, 42)],
    }
    _db("DELETE FROM level_config WHERE guild_id=?", GID)
    await cog.reload_guild(GID)
    assert cog.get_config(GID) == {
        "enabled": True, "notify_mode": "here", "notify_channel": 0, "rewards": [],
    }


async def test_config_survives_a_restart(cog, monkeypatch):
    await save_config(cog, mode="off")
    fresh = Leveling(SimpleNamespace(change_watcher=None))
    await fresh.cog_load()
    assert fresh.get_config(GID)["notify_mode"] == "off"


async def test_default_config_is_not_shared(cog):
    cog.get_config(GID)["rewards"].append((1, 1))
    assert cog.get_config(GID)["rewards"] == []


def test_due_role_ids():
    rewards = [(5, 1), (10, 2), (20, 3)]
    assert due_role_ids(rewards, 4, set()) == []
    assert due_role_ids(rewards, 5, set()) == [1]
    assert due_role_ids(rewards, 20, {1}) == [2, 3]
    assert due_role_ids(rewards, 20, {1, 2, 3}) == []


class FakeMember(discord.Member):
    id = USER
    bot = False
    mention = "<@7>"
    roles = property(lambda self: self.fake_roles)

    def __init__(self, role_ids=()):
        self.fake_roles = [SimpleNamespace(id=role_id) for role_id in role_ids]
        self.add_roles = AsyncMock()


class FakeRole:
    def __init__(self, role_id, position=1, managed=False):
        self.id = role_id
        self.position = position
        self.managed = managed

    def __lt__(self, other):
        return self.position < other.position


TOP_ROLE = FakeRole(99, position=10)


def member_message(message, *owned, roles=(), manage_roles=True):
    message.author = FakeMember(owned)
    message.author.guild = message.guild
    known = {role.id: role for role in roles}
    message.guild.get_role = known.get
    message.guild.me = SimpleNamespace(
        top_role=TOP_ROLE, guild_permissions=SimpleNamespace(manage_roles=manage_roles)
    )
    return message


def granted(message):
    message.author.add_roles.assert_awaited_once()
    return [role.id for role in message.author.add_roles.await_args.args]


def rewards_json(*pairs):
    return json.dumps([{"level": level, "role_id": str(role)} for level, role in pairs])


async def test_reward_granted_on_level_up(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11)))
    set_progress(cog)
    member_message(message, roles=[FakeRole(11)])
    await cog.on_message(message)
    assert granted(message) == [11]


async def test_backfill_without_level_up(cog, message):
    await save_config(cog, rewards=rewards_json((5, 11)))
    set_progress(cog, level=10, xp=cog.get_total_xp_for_level(10))
    member_message(message, roles=[FakeRole(11)])
    await cog.on_message(message)
    assert stored_user()[1] == 10
    assert granted(message) == [11]


async def test_rewards_are_cumulative(cog, message):
    await save_config(cog, rewards=rewards_json((5, 11), (10, 12), (20, 13)))
    set_progress(cog, level=20, xp=cog.get_total_xp_for_level(20))
    member_message(message, roles=[FakeRole(11), FakeRole(12), FakeRole(13)])
    await cog.on_message(message)
    assert granted(message) == [11, 12, 13]


async def test_no_missing_role_makes_no_call(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11)))
    set_progress(cog)
    member_message(message, 11, roles=[FakeRole(11)])
    await cog.on_message(message)
    message.author.add_roles.assert_not_awaited()


async def test_skips_when_bot_lacks_manage_roles(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11)))
    set_progress(cog)
    member_message(message, roles=[FakeRole(11)], manage_roles=False)
    await cog.on_message(message)
    message.author.add_roles.assert_not_awaited()


async def test_skips_role_above_bot_and_managed_role(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11), (1, 12), (1, 13), (1, 14)))
    set_progress(cog)
    roles = [FakeRole(11), FakeRole(12, position=10), FakeRole(13, position=20), FakeRole(14, managed=True)]
    member_message(message, roles=roles)
    await cog.on_message(message)
    assert granted(message) == [11]


async def test_only_ungrantable_roles_make_no_call(cog, message):
    await save_config(cog, rewards=rewards_json((1, 12)))
    set_progress(cog)
    member_message(message, roles=[FakeRole(12, position=20)])
    await cog.on_message(message)
    message.author.add_roles.assert_not_awaited()


async def test_skips_deleted_role(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11), (1, 12)))
    set_progress(cog)
    member_message(message, roles=[FakeRole(12)])
    await cog.on_message(message)
    assert granted(message) == [12]


async def test_rewards_skip_non_member_author(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11)))
    set_progress(cog)
    await cog.on_message(message)
    assert stored_user()[1] == 1


async def test_grant_failure_keeps_xp(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11)))
    set_progress(cog)
    member_message(message, roles=[FakeRole(11)])
    message.author.add_roles.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="no"), "no"
    )
    await cog.on_message(message)
    assert stored_user()[1] == 1


async def test_notice_failure_still_grants(cog, message):
    await save_config(cog, rewards=rewards_json((1, 11)))
    set_progress(cog)
    member_message(message, roles=[FakeRole(11)])
    message.channel.send.side_effect = discord.HTTPException(
        SimpleNamespace(status=500, reason="boom"), "boom"
    )
    await cog.on_message(message)
    assert granted(message) == [11]


async def test_disabled_guild_grants_nothing(cog, message):
    await save_config(cog, enabled=0, rewards=rewards_json((1, 11)))
    set_progress(cog)
    member_message(message, roles=[FakeRole(11)])
    await cog.on_message(message)
    message.author.add_roles.assert_not_awaited()
