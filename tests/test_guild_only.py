import ast
import os

COGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rinbot", "cogs"
)
EXCLUDED = {"general.py", "help.py", "dev.py"}


def _deco_name(deco):
    """装饰器的末段名字：commands.guild_only() / guild_only / x.command(...) -> 'guild_only' / 'command'"""
    node = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _group_base(deco):
    """`@grp.command(...)` 里的 grp 名；不是这种形式返回 None"""
    node = deco.func if isinstance(deco, ast.Call) else deco
    if (
        isinstance(node, ast.Attribute)
        and node.attr in ("command", "group")
        and isinstance(node.value, ast.Name)
    ):
        return node.value.id
    return None


def _uses_ctx_guild(func) -> bool:
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "guild"
            and isinstance(node.value, ast.Name)
            and node.value.id == "ctx"
        ):
            return True
    return False


def test_guild_commands_are_guild_only():
    missing = []
    for fname in sorted(os.listdir(COGS_DIR)):
        if not fname.endswith(".py") or fname in EXCLUDED:
            continue
        with open(os.path.join(COGS_DIR, fname), encoding="utf-8") as f:
            tree = ast.parse(f.read(), fname)
        funcs = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        groups = {
            fn.name
            for fn in funcs
            if any(_deco_name(d) == "hybrid_group" for d in fn.decorator_list)
        }
        for fn in funcs:
            names = {_deco_name(d) for d in fn.decorator_list}
            is_cmd = bool(names & {"hybrid_command", "hybrid_group"}) or any(
                _group_base(d) in groups for d in fn.decorator_list
            )
            if is_cmd and _uses_ctx_guild(fn) and "guild_only" not in names:
                missing.append(f"{fname}:{fn.name}")
    assert not missing, "缺少 guild_only 的指令: " + ", ".join(missing)
