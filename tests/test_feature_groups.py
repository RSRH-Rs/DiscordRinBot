import json
from types import SimpleNamespace

import discord

from command_tree import top_level_app_commands
from cogs.automod import AutoMod
from cogs.commandtoggle import CommandToggle
from cogs.reactionroles import ReactionRoles
from cogs.serverlog import ServerLog
from cogs.welcome import Welcome


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def _ctx(**extra):
    base = dict(
        guild=SimpleNamespace(id=5, get_channel=lambda cid: None), author=SimpleNamespace(id=1, mention="<@1>"),
        interaction=None, me=object(), send=_Recorder(),
        channel=SimpleNamespace(permissions_for=lambda m: SimpleNamespace(embed_links=True)),
    )
    base.update(extra)
    return SimpleNamespace(**base)


def _tops(cog):
    return {cmd.name: cmd for cmd in top_level_app_commands(cog)}


def test_welcome_group():
    tops = _tops(Welcome)
    assert set(tops) == {"welcome"}
    assert {c.name for c in tops["welcome"].commands} == {"setup", "test"}


def test_reaction_roles_and_serverlog_keep_their_listeners():
    # 指令组本身在 test_roles_serverlog_commands 里测
    for name in ("on_interaction", "on_raw_reaction_add", "on_raw_reaction_remove", "_rebuild_panel"):
        assert hasattr(ReactionRoles, name)
    for name in ("on_message_delete", "on_member_join", "on_voice_state_update", "_send"):
        assert hasattr(ServerLog, name)


def test_automod_shape():
    tops = _tops(AutoMod)
    assert set(tops) == {"automod"}
    children = {c.name: c for c in tops["automod"].commands}
    assert set(children) == {"status", "words", "whitelist", "ignore"}
    for group in ("words", "whitelist", "ignore"):
        assert {c.name for c in children[group].commands} == {"add", "remove", "list"}


async def test_automod_removed_subcommand_points_to_dashboard():
    cog = AutoMod.__new__(AutoMod)
    ctx = _ctx(invoked_subcommand=None, subcommand_passed="enable")
    await AutoMod.automod_group.callback(cog, ctx)
    (args, kwargs), = ctx.send.calls
    assert kwargs["embed"].title == "这项设置已移到控制台"
    assert kwargs["view"].children[0].url == "https://rin-bot.com/dashboard/server/5#automod"


async def test_word_autocomplete_lists_existing_words():
    cog = AutoMod.__new__(AutoMod)

    async def config(guild_id):
        return {"badwords": json.dumps(["坏词", "脏话"], ensure_ascii=False), "link_whitelist": json.dumps(["youtube.com"])}

    cog._get_config = config
    interaction = SimpleNamespace(guild=SimpleNamespace(id=5), locale=discord.Locale.chinese)
    assert [c.value for c in await cog._word_autocomplete(interaction, "")] == ["坏词", "脏话"]
    assert [c.value for c in await cog._word_autocomplete(interaction, "脏")] == ["脏话"]
    assert [c.value for c in await cog._domain_autocomplete(interaction, "")] == ["youtube.com"]


def test_commands_group():
    tops = _tops(CommandToggle)
    assert set(tops) == {"commands"}
    assert {c.name for c in tops["commands"].commands} == {"disable", "enable", "list"}
    toggle = CommandToggle.commands_group.get_command("toggle")
    assert toggle is not None and toggle.hidden and toggle.app_command is None


def _toggle_cog(disabled=None):
    cog = CommandToggle.__new__(CommandToggle)
    cog._disabled = disabled or {}
    cog.bot = SimpleNamespace(get_command=lambda name: object() if name in ("play", "help", "commands") else None)
    return cog


async def test_protected_commands_cannot_be_disabled():
    cog = _toggle_cog()
    for name in ("help", "commands"):
        ctx = _ctx()
        await CommandToggle.commands_disable.callback(cog, ctx, name)
        assert ctx.send.calls[0][1]["embed"].title == "这条指令不能停用"


async def test_unknown_command_is_explained():
    cog = _toggle_cog()
    ctx = _ctx()
    await CommandToggle.commands_disable.callback(cog, ctx, "nope")
    assert ctx.send.calls[0][1]["embed"].title == "找不到这条指令"


async def test_enable_autocomplete_lists_disabled_commands():
    cog = _toggle_cog({5: {"play", "roll"}})
    interaction = SimpleNamespace(guild=SimpleNamespace(id=5), locale=discord.Locale.chinese)
    assert sorted(c.value for c in await cog._enable_autocomplete(interaction, "")) == ["play", "roll"]
