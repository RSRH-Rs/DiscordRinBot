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


def _direct_guild_use(func) -> bool:
    """函数体直接依赖服务器：ctx.guild / ctx.voice_client / ctx.author.voice / ctx.author.guild_permissions"""
    for node in ast.walk(func):
        if not isinstance(node, ast.Attribute):
            continue
        if isinstance(node.value, ast.Name) and node.value.id == "ctx":
            if node.attr in ("guild", "voice_client"):
                return True
        if (
            node.attr in ("voice", "guild_permissions")
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "author"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "ctx"
        ):
            return True
    return False


def _self_helpers_called_with_ctx(func):
    """函数里形如 <对象>._xxx(ctx, ...) 的调用（如 self._ensure_voice / music._ensure_voice），返回被调用的方法名"""
    names = set()
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("_")
            and any(
                isinstance(a, ast.Name) and a.id == "ctx"
                for a in list(node.args) + [k.value for k in node.keywords]
            )
        ):
            names.add(node.func.attr)
    return names


def _guild_dependent(funcs) -> set[str]:
    """所有 cog 文件里的函数名集合：直接依赖服务器，或把 ctx 传给依赖服务器的 _helper（取不动点）"""
    by_name = {}
    for fn in funcs:
        by_name.setdefault(fn.name, []).append(fn)
    tainted = {n for n, fs in by_name.items() if any(_direct_guild_use(f) for f in fs)}
    changed = True
    while changed:
        changed = False
        for n, fs in by_name.items():
            if n in tainted:
                continue
            if any(_self_helpers_called_with_ctx(f) & tainted for f in fs):
                tainted.add(n)
                changed = True
    return tainted


def _parse_cogs():
    parsed = {}
    for fname in sorted(os.listdir(COGS_DIR)):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(COGS_DIR, fname), encoding="utf-8") as f:
            tree = ast.parse(f.read(), fname)
        parsed[fname] = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    return parsed


def test_guild_commands_are_guild_only():
    parsed = _parse_cogs()
    dependent = _guild_dependent([fn for funcs in parsed.values() for fn in funcs])
    missing = []
    for fname, funcs in parsed.items():
        if fname in EXCLUDED:
            continue
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
            if is_cmd and fn.name in dependent and "guild_only" not in names:
                missing.append(f"{fname}:{fn.name}")
    assert not missing, "缺少 guild_only 的指令: " + ", ".join(missing)


# 只通过辅助函数间接依赖服务器/语音状态的指令：显式列出，防止 AST 规则漏判
INDIRECT_GUILD_COMMANDS = {
    "music.py": {"play", "search", "pause", "resume", "join"},
    "moderation.py": {"slowmode"},
    "giveaway.py": {"giveaway_group"},
    "netease.py": {
        "netease_play", "netease_search", "netease_profile",
        "ne_play", "ne_search", "ne_profile",
    },
}


def test_indirect_guild_commands_carry_guild_only():
    missing = []
    for fname, wanted in INDIRECT_GUILD_COMMANDS.items():
        with open(os.path.join(COGS_DIR, fname), encoding="utf-8") as f:
            tree = ast.parse(f.read(), fname)
        found = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name in wanted:
                found.add(fn.name)
                if "guild_only" not in {_deco_name(d) for d in fn.decorator_list}:
                    missing.append(f"{fname}:{fn.name}")
        missing += [f"{fname}:{n}(不存在)" for n in wanted - found]
    assert not missing, "缺少 guild_only 的指令: " + ", ".join(missing)
