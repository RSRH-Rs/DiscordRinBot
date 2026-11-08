from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest

from cogs import onboarding


def perms(view=True, send=True, embed=True):
    return SimpleNamespace(view_channel=view, send_messages=send, embed_links=embed)


def channel(cid, position=0, **p):
    ch = SimpleNamespace(id=cid, position=position, send=AsyncMock())
    ch.permissions_for = lambda member, _p=perms(**p): _p
    return ch


def guild(system=None, text=(), locale=discord.Locale.american_english, me=True):
    return SimpleNamespace(
        id=555, preferred_locale=locale, system_channel=system,
        text_channels=list(text), me=object() if me else None,
    )


def configured(result):
    mock = AsyncMock(side_effect=result) if isinstance(result, Exception) else AsyncMock(return_value=result)
    return patch.object(onboarding.guild_config, "has_config", mock)


def test_system_channel_first():
    sys_ch, other = channel(1, 5), channel(2, 0)
    assert onboarding.pick_channel(guild(sys_ch, [other, sys_ch])) is sys_ch


def test_falls_back_when_system_channel_cannot_embed():
    sys_ch, other = channel(1, 0, embed=False), channel(2, 3)
    assert onboarding.pick_channel(guild(sys_ch, [sys_ch, other])) is other


def test_falls_back_by_position():
    late, early = channel(1, 9), channel(2, 2)
    assert onboarding.pick_channel(guild(None, [late, early])) is early


def test_no_channel_returns_none():
    blocked = channel(1, 0, send=False)
    assert onboarding.pick_channel(guild(blocked, [blocked])) is None
    assert onboarding.pick_channel(guild(None, [channel(2)], me=False)) is None


@pytest.mark.asyncio
async def test_no_text_channels_does_not_raise():
    with configured(False):
        await onboarding.Onboarding(object()).on_guild_join(guild(None, []))


@pytest.mark.asyncio
async def test_skips_when_config_exists():
    ch = channel(1)
    with configured(True):
        await onboarding.Onboarding(object()).on_guild_join(guild(ch, [ch]))
    ch.send.assert_not_called()


@pytest.mark.asyncio
async def test_config_lookup_failure_is_swallowed():
    ch = channel(1)
    with configured(RuntimeError("db")):
        await onboarding.Onboarding(object()).on_guild_join(guild(ch, [ch]))
    ch.send.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", [discord.Locale.chinese, discord.Locale.taiwan_chinese])
async def test_chinese_locale(locale):
    embed, view = onboarding.build_greeting(guild(locale=locale))
    assert embed.title == "小凛来了"
    assert embed.description == "我能放歌、迎新、拦刷屏和记日志。打开控制台，想用哪个就开哪个。"
    assert view.children[0].label == "打开控制台"


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", [discord.Locale.american_english, discord.Locale.japanese])
async def test_english_for_other_locales(locale):
    embed, view = onboarding.build_greeting(guild(locale=locale))
    assert embed.title == "Rin is here"
    assert embed.description == ("I play music, welcome new members, stop spam and keep logs. "
                                 "Open the dashboard and turn on what you need.")
    assert view.children[0].label == "Open dashboard"


@pytest.mark.asyncio
async def test_button_links_to_this_server():
    _, view = onboarding.build_greeting(guild())
    assert view.children[0].url == "https://rin-bot.com/dashboard/server/555"
    assert view.timeout is None


@pytest.mark.asyncio
async def test_sends_without_mentions():
    ch = channel(1)
    with configured(False):
        await onboarding.Onboarding(object()).on_guild_join(guild(ch, [ch]))
    kw = ch.send.call_args.kwargs
    assert kw["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
    assert isinstance(kw["embed"], discord.Embed)
    assert isinstance(kw["view"], discord.ui.View)


@pytest.mark.asyncio
async def test_http_error_is_swallowed():
    ch = channel(1)
    ch.send = AsyncMock(side_effect=discord.HTTPException(SimpleNamespace(status=500, reason="x"), "boom"))
    with configured(False):
        await onboarding.Onboarding(object()).on_guild_join(guild(ch, [ch]))
    ch.send.assert_awaited_once()
