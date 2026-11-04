"""机器人发出的 embed 只经过共用模板：不自己写颜色、不直接拼 discord.Embed，标题和字段名不加 emoji。"""
import ast
import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 所有 cog（新加的自动受约束）；网易云模块不进仓库，_messages 本身负责转换
PENDING = {"netease.py", "_messages.py"}
MIGRATED = sorted(
    os.path.relpath(path, ROOT).replace(os.sep, "/")
    for path in glob.glob(os.path.join(ROOT, "rinbot", "cogs", "*.py"))
    if os.path.basename(path) not in PENDING
)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️]")
RAW_COLOUR = re.compile(r"discord\.Colou?r\.|colou?r\s*=\s*0x|[\"']colou?r[\"']\s*:\s*0x")


def _source(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def _literal_text(node):
    """字符串常量或 f-string 的常量部分；其他表达式返回 None。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    return None


def _embed_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "embed":
            yield node


@pytest.mark.parametrize("path", MIGRATED)
def test_no_raw_colours(path):
    assert RAW_COLOUR.findall(_source(path)) == []


@pytest.mark.parametrize("path", MIGRATED)
def test_no_direct_embed_building(path):
    bad = []
    for node in ast.walk(ast.parse(_source(path))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "Embed" and getattr(func.value, "id", None) == "discord":
            bad.append((node.lineno, "discord.Embed"))
        if isinstance(func, ast.Attribute) and func.attr in ("add_field", "set_footer", "set_author"):
            bad.append((node.lineno, func.attr))
    assert bad == []


@pytest.mark.parametrize("path", MIGRATED)
def test_titles_and_field_names_have_no_emoji(path):
    bad = []
    for call in _embed_calls(ast.parse(_source(path))):
        titles = call.args[1:2] + [kw.value for kw in call.keywords if kw.arg == "title"]
        for node in titles:
            text = _literal_text(node)
            if text and EMOJI.search(text):
                bad.append((call.lineno, text))
        for kw in call.keywords:
            if kw.arg == "fields" and isinstance(kw.value, ast.List):
                for item in kw.value.elts:
                    if isinstance(item, ast.Tuple) and item.elts:
                        text = _literal_text(item.elts[0])
                        if text and EMOJI.search(text):
                            bad.append((call.lineno, text))
    assert bad == []


@pytest.mark.parametrize("path", MIGRATED)
def test_embed_name_is_only_called(path):
    """embed 是模板函数：不能被赋值成局部变量，也不能当值传出去（漏改的 embed 变量会把函数本身发出去）。"""
    tree = ast.parse(_source(path))
    called = {id(call.func) for call in _embed_calls(tree)}
    bad = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "embed" and id(node) not in called
    ]
    assert bad == []
