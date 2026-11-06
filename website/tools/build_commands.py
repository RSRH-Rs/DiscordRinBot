"""生成官网指令大全用的指令清单 website/data/commands.json。

用法：在仓库根目录运行 python website/tools/build_commands.py

不启动机器人，直接从 rinbot/cogs 下的 cog 类读出斜杠指令树（跳过主人指令和只在本地的
netease.py），只收叶子指令，再合并 rinbot/i18n/commands.zh.json 里的中文说明、参数名和例子。
改了指令以后要重新运行；tests/test_command_catalog.py 会检查文件有没有跟上。
"""
import importlib
import inspect
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RINBOT = ROOT / "rinbot"
COGS = RINBOT / "cogs"
WEBSITE = ROOT / "website"
DATA_PATH = WEBSITE / "data" / "commands.json"
ZH_TABLE = RINBOT / "i18n" / "commands.zh.json"
SKIP = {"netease.py"}
GROUP_OF_COG = {"CommandToggle": "System", "Help": "System"}

# 和 tests/conftest.py 一样：rinbot 放最前面，cogs 目录挂在最后（cog 里有 `from _perms import ...`）
for path, front in ((str(WEBSITE), True), (str(RINBOT), True), (str(COGS), False)):
    if path not in sys.path:
        sys.path.insert(0, path) if front else sys.path.append(path)


def _cog_classes():
    from discord.ext import commands

    for name in sorted(os.listdir(COGS)):
        if not name.endswith(".py") or name.startswith("_") or name in SKIP:
            continue
        module = importlib.import_module(f"cogs.{name[:-3]}")
        for obj in vars(module).values():
            if inspect.isclass(obj) and issubclass(obj, commands.Cog) and obj.__module__ == module.__name__:
                yield obj


def _leaves(app_cmd):
    from discord import app_commands

    if isinstance(app_cmd, app_commands.Group):
        for child in app_cmd.commands:
            yield from _leaves(child)
    else:
        yield app_cmd


def build_catalog() -> dict:
    """{"commands": [...]}，按 site_data.COMMAND_GROUPS 的顺序，同组内按 cog 文件和定义顺序。"""
    from _perms import is_owner_only
    import site_data

    zh_table = json.loads(ZH_TABLE.read_text(encoding="utf-8")).get("commands", {})
    order = [g["key"] for g in site_data.COMMAND_GROUPS]
    found = []
    for cls in _cog_classes():
        group = GROUP_OF_COG.get(cls.__name__, cls.__name__)
        for cmd in cls.__cog_commands__:
            top = getattr(cmd, "app_command", None)
            if cmd.parent is not None or top is None or is_owner_only(cmd):
                continue
            perms = [name for name, value in top.default_permissions or [] if value]
            for leaf in _leaves(top):
                name = leaf.qualified_name
                zh = zh_table.get(name, {})
                zh_params = zh.get("params", {})
                found.append({
                    "name": name,
                    "id": name.replace(" ", "-"),
                    "group": group,
                    "en": leaf.description,
                    "zh": zh.get("description", ""),
                    "perms": perms,
                    "params": [{
                        "name": p.name,
                        "required": p.required,
                        "en": p.description,
                        "zh": zh_params.get(p.name, {}).get("name", ""),
                        "zh_desc": zh_params.get(p.name, {}).get("description", ""),
                    } for p in leaf.parameters],
                    "examples": zh.get("examples", []),
                })
    found.sort(key=lambda c: order.index(c["group"]) if c["group"] in order else len(order))
    return {"commands": found}


def main():
    catalog = build_catalog()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(catalog['commands'])} commands to {DATA_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
