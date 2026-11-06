"""首页英雄区的两个小组件：会轮播的大厅聊天、戳一下小凛。"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import site_data
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "website" / "static"
CSS = (STATIC_DIR / "css" / "home-widgets.css").read_text(encoding="utf-8")


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


def _tags(html):
    p = _Tags()
    p.feed(html)
    return p.tags


@pytest.fixture(scope="module")
def page():
    env = Environment(loader=FileSystemLoader(str(ROOT / "website" / "templates")))
    env.globals["url_for"] = lambda endpoint, filename: "/static/" + filename
    env.globals["invite_url"] = site_data.invite_url()
    return env.get_template("index.html").render(is_logged_in=False)


def _hero(page):
    return re.search(r'<section class="hero".*?</section>', page, re.S).group(0)


def _scenes(page):
    return re.findall(r'<template data-scene>(.*?)</template>', _hero(page), re.S)


def _bilingual(fragment):
    zh = fragment.count('data-l="zh"')
    return zh > 0 and zh == fragment.count('data-l="en"')


def test_widget_files_are_linked(page):
    head = page.split("</head>", 1)[0]
    assert '/static/css/home-widgets.css' in head
    srcs = [a.get("src") for t, a in _tags(page) if t == "script"]
    assert "/static/js/home-widgets.js" in srcs


def test_chat_has_scenes_with_rin_replies(page):
    scenes = _scenes(page)
    assert len(scenes) >= 3
    for scene in scenes:
        assert 'class="nm rin"' in scene
        assert _bilingual(scene)
    # 自动审核那段：广告先出现，再被小凛删掉
    assert sum("data-deleted" in s for s in scenes) == 1


def test_typing_line_and_pause_button(page):
    hero = _hero(page)
    typing = re.search(r'<div class="typing"[^>]*>.*?</div>', hero, re.S).group(0)
    assert 'aria-hidden="true"' in typing and _bilingual(typing)
    button = next(a for t, a in _tags(hero) if t == "button" and "chat-pause" in a.get("class", ""))
    assert button.get("type") == "button" and button.get("aria-pressed") == "false"
    pause = re.search(r'<button[^>]*chat-pause.*?</button>', hero, re.S).group(0)
    assert _bilingual(pause)


def test_sticker_is_a_poke_button(page):
    hero = _hero(page)
    button = next(a for t, a in _tags(hero) if t == "button" and "stk-poke" in a.get("class", ""))
    assert button.get("type") == "button"
    assert button.get("data-i18n-aria") == "poke" and button.get("aria-label")
    img = next(a for t, a in _tags(hero) if t == "img" and "data-poke-srcset" in a)
    assert "confused-480.webp" in img["data-poke-srcset"]
    assert "confused-960.webp" in img["data-poke-srcset"]
    # 逐字显示的那层不给读屏念，读屏只念整句（放在隐藏的 live 区域里）
    bubble = re.search(r'<p class="rin-say">(.*?)</p>', hero, re.S).group(1)
    shown = next(a for t, a in _tags(bubble) if "say-shown" in a.get("class", ""))
    spoken = next(a for t, a in _tags(bubble) if "say-sr" in a.get("class", ""))
    assert shown.get("aria-hidden") == "true"
    assert spoken.get("aria-live") == "polite"


def test_poke_aria_label_in_both_languages(page):
    data = json.loads(re.search(r'id="attr-i18n">(.*?)</script>', page, re.S).group(1))
    assert data["zh"]["poke"] and data["en"]["poke"]
    assert data["zh"]["poke"] != data["en"]["poke"]


def test_poke_lines(page):
    block = re.search(r'<template id="rin-lines">(.*?)</template>', _hero(page), re.S).group(1)
    lines = re.findall(r'<p data-line(?:="(\w+)")?>(.*?)</p>', block, re.S)
    plain = [body for kind, body in lines if not kind]
    assert len(plain) >= 5
    assert [kind for kind, _ in lines].count("angry") == 1
    for _, body in lines:
        assert _bilingual(body)
        assert "<b>" not in body  # 逐字打出来的台词只能是纯文字


def test_controls_hidden_without_js():
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    rules = dict((s.strip(), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", css))
    assert "display: none" in rules[".hero-chat .chat-pause"]
    assert "display: none" in rules[".hero-chat .typing"]


def test_widget_css_gates_hidden_states_and_reduces_motion():
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    plain = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", plain):
        if re.search(r"opacity\s*:\s*0(?![.\d])", body):
            for sel in selector.split(","):
                assert sel.strip().startswith(("html.js", ".js")), sel.strip()
    reduced = re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}", CSS, re.S)
    assert reduced and ".stk-poke.poked img" in reduced.group(1)
