"""网页发到 Discord 的消息用共用模板：系统日志级别、身份组面板默认标题、抽奖消息都来自 rincore.embeds。"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _source():
    with open(os.path.join(ROOT, "website", "routes.py"), encoding="utf-8") as f:
        return f.read()


def test_routes_drop_their_own_embed_styles():
    source = _source()
    for old in ("_AUDIT_LEVEL_META", "🏷 身份组选择", "中奖名额", "抽奖活动！"):
        assert old not in source, old


def test_routes_use_shared_builders():
    called = {
        node.func.id for node in ast.walk(ast.parse(_source()))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"build", "giveaway_running"} <= called
