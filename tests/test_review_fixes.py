"""Regression tests for the final review of the bot message foundation."""
import ast
import glob
import io
import os
import symtable
import builtins
from types import SimpleNamespace

import discord
from discord.ext import commands

import _perms
from _messages import Notice, embed, send_notice
from _perms import owner_only
from cogs import welcome

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COGS = [
    p for p in glob.glob(os.path.join(ROOT, "rinbot", "cogs", "*.py"))
    if os.path.basename(p) != "netease.py"
]


def _module_names(table):
    return {s.get_name() for s in table.get_symbols() if s.is_assigned() or s.is_imported()}


def _undefined(table, module_names, path):
    bad = []
    for child in table.get_children():
        if child.get_type() == "function":
            for sym in child.get_symbols():
                name = sym.get_name()
                if sym.is_referenced() and sym.is_global() and not sym.is_declared_global():
                    if name not in module_names and not hasattr(builtins, name):
                        bad.append((os.path.basename(path), child.get_name(), name))
        bad += _undefined(child, module_names, path)
    return bad


def test_cogs_reference_no_undefined_names():
    bad = []
    for path in COGS:
        with open(path, encoding="utf-8") as f:
            table = symtable.symtable(f.read(), path, "exec")
        bad += _undefined(table, _module_names(table) | {"__file__", "__name__"}, path)
    assert bad == []


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def _welcome_cog(monkeypatch):
    cog = welcome.Welcome.__new__(welcome.Welcome)

    async def config(guild_id):
        return {"enabled": 1, "welcome_channel": 9, "show_card": 1}

    async def render(member):
        return discord.File(io.BytesIO(b"png"), filename="welcome.png")

    async def no_roles(member, config):
        return None

    cog._get_config = config
    cog._render_card_file = render
    cog._assign_auto_roles = no_roles
    cog._custom_image_file = lambda config, kind: None
    cog._build_welcome_embed = lambda member, config: embed("info", description="欢迎")
    return cog


def _sent_card(call):
    args, kwargs = call
    e, files = kwargs["embed"], kwargs["files"]
    assert isinstance(e, discord.Embed)
    assert e.image.url == "attachment://welcome.png"
    assert [f.filename for f in files] == ["welcome.png"]


async def test_welcome_with_banner_still_sends(monkeypatch):
    cog = _welcome_cog(monkeypatch)
    channel = SimpleNamespace(send=_Recorder())
    guild = SimpleNamespace(id=1, get_channel=lambda cid: channel)
    member = SimpleNamespace(bot=False, pending=False, guild=guild)
    await welcome.Welcome.on_member_join(cog, member)
    _sent_card(channel.send.calls[0])


async def test_welcome_test_with_banner_still_sends(monkeypatch):
    cog = _welcome_cog(monkeypatch)

    async def defer():
        return None

    ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=object(), defer=defer, send=_Recorder())
    await welcome.Welcome.welcome_test.callback(cog, ctx)
    _sent_card(ctx.send.calls[0])


def test_no_cog_keeps_its_own_error_replies():
    defined = []
    for path in COGS:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        defined += [
            (os.path.basename(path), n.name) for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name in ("cog_command_error", "cog_app_command_error")
        ]
    assert defined == []


class _Original:
    def __init__(self, loading):
        self.flags = SimpleNamespace(loading=loading, ephemeral=False)
        self.deleted = False

    async def delete(self):
        self.deleted = True


def _deferred_interaction(loading=True, kind=discord.InteractionResponseType.deferred_channel_message):
    original = _Original(loading)

    async def fetch_original():
        return original

    return SimpleNamespace(
        response=SimpleNamespace(is_done=lambda: True, type=kind, send_message=_Recorder()),
        followup=SimpleNamespace(send=_Recorder()),
        original_response=fetch_original,
    ), original


async def test_private_notice_after_public_defer_clears_thinking_message():
    interaction, original = _deferred_interaction(loading=True)
    await send_notice(interaction, Notice("error", "这条指令没有执行成功"))
    assert original.deleted
    assert interaction.followup.send.calls[0][1]["ephemeral"] is True


async def test_private_notice_keeps_a_public_reply_already_sent():
    interaction, original = _deferred_interaction(loading=False)
    await send_notice(interaction, Notice("error", "这条指令没有执行成功"))
    assert not original.deleted


async def test_private_notice_after_message_reply_leaves_it_alone():
    interaction, original = _deferred_interaction(kind=discord.InteractionResponseType.channel_message)
    await send_notice(interaction, Notice("error", "x"))
    assert not original.deleted


async def test_hybrid_context_after_public_defer_clears_thinking_message():
    interaction, original = _deferred_interaction(loading=True)
    ctx = SimpleNamespace(interaction=interaction, guild=object(), send=_Recorder())
    await send_notice(ctx, Notice("error", "x"))
    assert original.deleted
    assert ctx.send.calls[0][1]["ephemeral"] is True


def test_owner_commands_hidden_from_dev_server_members(monkeypatch):
    monkeypatch.setattr(_perms, "DEV_GUILD_ID", 123)

    @commands.hybrid_command(name="t")
    @owner_only()
    async def t(ctx):
        pass

    assert t.app_command.default_permissions == discord.Permissions(administrator=True)
