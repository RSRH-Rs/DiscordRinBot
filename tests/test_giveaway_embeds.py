"""抽奖消息只由 rincore.embeds 的两个函数生成，机器人不再自己拼。"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _source():
    with open(os.path.join(ROOT, "rinbot", "cogs", "giveaway.py"), encoding="utf-8") as f:
        return f.read()


def test_bot_uses_shared_giveaway_builders():
    called = {
        node.func.id for node in ast.walk(ast.parse(_source()))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"giveaway_running", "giveaway_ended"} <= called


def test_bot_no_longer_builds_giveaway_text():
    source = _source()
    assert "中奖名额" not in source and "抽奖活动！" not in source
