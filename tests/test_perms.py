import ast
import glob
import os
from types import SimpleNamespace

import discord
from discord.ext import commands

import _perms
from _perms import is_owner_only, owner_only, require, required_permissions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COGS = [
    p for p in glob.glob(os.path.join(ROOT, "rinbot", "cogs", "*.py"))
    if os.path.basename(p) not in ("netease.py", "_perms.py")
]
OWNER_COMMANDS = {"hot_update", "load", "unload", "extensions", "sync", "eval", "setstatus", "resetstatus", "setbio"}


def _tree(path):
    with open(path, encoding="utf-8") as f:
        return ast.parse(f.read())


def _call_name(deco):
    node = deco.func if isinstance(deco, ast.Call) else deco
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", None)


def _command_name(fn):
    for deco in fn.decorator_list:
        if isinstance(deco, ast.Call) and _call_name(deco) in ("hybrid_command", "hybrid_group", "command", "group"):
            for kw in deco.keywords:
                if kw.arg == "name":
                    return kw.value.value
    return None


def _require_perms(fn):
    for deco in fn.decorator_list:
        if isinstance(deco, ast.Call) and _call_name(deco) == "require":
            return {kw.arg for kw in deco.keywords}
    return None


def test_require_sets_check_and_default_permissions():
    @commands.hybrid_command(name="t")
    @require(kick_members=True)
    async def t(ctx):
        pass

    assert t.app_command.default_permissions == discord.Permissions(kick_members=True)
    assert len(t.checks) == 1
    assert required_permissions(t) == discord.Permissions(kick_members=True)


def test_required_permissions_of_subcommand_comes_from_group():
    @commands.hybrid_group(name="g")
    @require(manage_guild=True)
    async def g(ctx):
        pass

    @g.command(name="list")
    async def g_list(ctx):
        pass

    assert required_permissions(g_list) == discord.Permissions(manage_guild=True)


def test_required_permissions_none_for_open_commands():
    @commands.hybrid_command(name="roll")
    async def roll(ctx):
        pass

    assert required_permissions(roll) is None
    assert not is_owner_only(roll)


def test_owner_only_registers_in_dev_guild(monkeypatch):
    monkeypatch.setattr(_perms, "DEV_GUILD_ID", 123)

    @commands.hybrid_command(name="t")
    @owner_only()
    async def t(ctx):
        pass

    assert t.app_command._guild_ids == [123]
    assert is_owner_only(t)
    assert len(t.checks) == 1


def test_owner_only_without_dev_guild_has_no_slash(monkeypatch):
    monkeypatch.setattr(_perms, "DEV_GUILD_ID", 0)

    @commands.hybrid_command(name="t")
    @owner_only()
    async def t(ctx):
        pass

    assert t.app_command._guild_ids == []
    bot = commands.Bot(command_prefix="r!", intents=discord.Intents.none())
    bot.add_command(t)
    assert bot.tree.get_commands() == []
    assert bot.get_command("t") is t


def test_no_bare_permission_checks():
    bad = []
    for path in COGS:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Attribute) and node.attr in ("has_permissions", "is_owner"):
                bad.append((os.path.basename(path), node.lineno, node.attr))
    assert bad == []


def test_groups_cover_subcommand_permissions():
    bad = []
    for path in COGS:
        funcs = [n for n in ast.walk(_tree(path)) if isinstance(n, ast.AsyncFunctionDef)]
        groups = {
            f.name: f for f in funcs
            if any(isinstance(d, ast.Call) and _call_name(d) == "hybrid_group" for d in f.decorator_list)
        }
        for f in funcs:
            for d in f.decorator_list:
                node = d.func if isinstance(d, ast.Call) else d
                if not (isinstance(node, ast.Attribute) and node.attr == "command" and isinstance(node.value, ast.Name)):
                    continue
                group = groups.get(node.value.id)
                needed = _require_perms(f)
                if group is None or not needed:
                    continue
                if not needed <= (_require_perms(group) or set()):
                    bad.append((os.path.basename(path), group.name, f.name))
    assert bad == []


def test_owner_commands_use_owner_only():
    found = {}
    for path in COGS:
        for f in ast.walk(_tree(path)):
            if isinstance(f, ast.AsyncFunctionDef) and _command_name(f) in OWNER_COMMANDS:
                found[_command_name(f)] = any(
                    isinstance(d, ast.Call) and _call_name(d) == "owner_only" for d in f.decorator_list
                )
    assert found == {name: True for name in OWNER_COMMANDS}


def test_health_snapshot_skips_owner_commands():
    from cogs.health import Health

    @commands.hybrid_command(name="roll", description="掷骰子")
    async def roll(ctx):
        pass

    @commands.hybrid_command(name="setbio", description="改简介")
    @owner_only()
    async def setbio(ctx):
        pass

    bot = SimpleNamespace(commands=[roll, setbio])
    assert [c["name"] for c in Health(bot)._command_snapshot()] == ["roll"]
