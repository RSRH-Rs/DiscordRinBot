"""官网指令大全的数据（website/data/commands.json）要和 cog 里的斜杠指令一致。"""
import importlib.util
import json
import pathlib

import site_data as sd

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_commands", ROOT / "website" / "tools" / "build_commands.py")
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)


def test_committed_catalog_matches_the_cogs():
    on_disk = json.loads(bc.DATA_PATH.read_text(encoding="utf-8"))
    assert on_disk == bc.build_catalog(), "run: python website/tools/build_commands.py"


def test_catalog_shape():
    cmds = bc.build_catalog()["commands"]
    assert len(cmds) == 68
    assert len({c["id"] for c in cmds}) == 68
    groups = {g["key"] for g in sd.COMMAND_GROUPS}
    for c in cmds:
        assert c["group"] in groups, c["name"]
        assert set(c["perms"]) <= set(sd.PERM_LABELS), c["name"]
        assert c["zh"] and c["en"], c["name"]
        assert c["id"] == c["name"].replace(" ", "-")
    names = {c["name"] for c in cmds}
    assert {"ban", "automod whitelist add", "help"} <= names and "netease" not in names
    ban = next(c for c in cmds if c["name"] == "ban")
    assert ban["perms"] == ["ban_members"] and [p["required"] for p in ban["params"]] == [True, False, False, False]


def test_commands_follow_group_order():
    order = [g["key"] for g in sd.COMMAND_GROUPS]
    seen = [c["group"] for c in bc.build_catalog()["commands"]]
    assert seen == sorted(seen, key=order.index)
