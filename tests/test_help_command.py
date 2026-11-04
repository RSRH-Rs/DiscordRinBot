from types import SimpleNamespace

import discord

from cogs import help as help_cog
from cogs.general import General
from cogs.moderation import Moderation

BAN, KICK, ROLL = Moderation.ban, Moderation.kick, General.roll
CLEAR = Moderation.warnings_group.get_command("clear")


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def _bot():
    commands_by_path = {"ban": BAN, "kick": KICK, "roll": ROLL, "warnings clear": CLEAR}
    return SimpleNamespace(
        get_command=commands_by_path.get,
        walk_commands=lambda: iter(commands_by_path.values()),
        get_cog=lambda name: None,
        user=None,
    )


def _ctx(perms):
    return SimpleNamespace(
        guild=SimpleNamespace(id=1), author=SimpleNamespace(id=2, display_name="小明", guild_permissions=perms),
        interaction=object(), send=_Recorder(), me=object(),
        channel=SimpleNamespace(permissions_for=lambda m: SimpleNamespace(embed_links=True)),
    )


async def test_help_detail_card():
    cog = help_cog.Help(_bot())
    ctx = _ctx(discord.Permissions.all())
    await help_cog.Help.help.callback(cog, ctx, command="/ban")
    card = ctx.send.calls[0][1]["embed"]
    assert card.title == "/ban"
    assert card.description == "封禁一名成员，填了时长就是临时封禁"
    fields = {f.name: f.value for f in card.fields}
    assert fields["用法"] == "`/ban <成员> [时长] [清理天数] [原因]`"
    assert "/ban @小明 7d 刷屏" in fields["例子"]
    assert fields["需要的权限"] == "「封禁成员」"
    assert ctx.send.calls[0][1]["ephemeral"] is True


async def test_help_shows_a_subcommands_own_permissions():
    cog = help_cog.Help(_bot())
    ctx = _ctx(discord.Permissions.all())
    await help_cog.Help.help.callback(cog, ctx, command="warnings clear")
    fields = {f.name: f.value for f in ctx.send.calls[0][1]["embed"].fields}
    assert fields["需要的权限"] == "「管理消息」「管理服务器」"


async def test_help_unknown_or_hidden():
    cog = help_cog.Help(_bot())
    for command, perms in (("nope", discord.Permissions.all()), ("kick", discord.Permissions.none())):
        ctx = _ctx(perms)
        await help_cog.Help.help.callback(cog, ctx, command=command)
        assert ctx.send.calls[0][1]["embed"].title == "找不到这条指令"


async def test_help_autocomplete_respects_permissions():
    cog = help_cog.Help(_bot())
    member = SimpleNamespace(user=SimpleNamespace(guild_permissions=discord.Permissions.none()))
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=1), user=member.user, locale=discord.Locale.chinese,
    )
    values = [c.value for c in await cog._command_autocomplete(interaction, "")]
    assert "roll" in values and "kick" not in values
    manager = SimpleNamespace(guild=SimpleNamespace(id=1), user=SimpleNamespace(guild_permissions=discord.Permissions.all()), locale=discord.Locale.chinese)
    assert "warnings clear" in [c.value for c in await cog._command_autocomplete(manager, "warn")]


def test_usage_uses_chinese_parameter_names():
    assert help_cog.usage_zh(BAN) == "/ban <成员> [时长] [清理天数] [原因]"
