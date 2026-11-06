"""官网首页（website/templates/index.html）与其贴纸资源的静态检查。"""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import site_data
from jinja2 import Environment, FileSystemLoader
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "website" / "static"
RIN_DIR = STATIC_DIR / "images" / "rin"

STICKERS = ["welcome", "music", "manage", "confused", "manage-blink", "confused-blink"]


@pytest.mark.parametrize("name", STICKERS)
@pytest.mark.parametrize("width", [480, 960])
def test_rin_assets_exist_and_sized(name, width):
    path = RIN_DIR / f"{name}-{width}.webp"
    assert path.is_file(), path
    with Image.open(path) as im:
        assert im.width == width
        assert im.mode == "RGBA"
    assert path.stat().st_size < 150 * 1024


def test_bot_avatar_small():
    path = RIN_DIR / "bot-avatar-96.webp"
    assert path.is_file()
    with Image.open(path) as im:
        assert im.width == 96


# ── 模板渲染 ──────────────────────────────────────────────

INVITE = (
    "https://discord.com/oauth2/authorize?client_id=1352551616427069492"
    "&permissions=1374694796438&integration_type=0&scope=bot+applications.commands"
)
GITHUB = "https://github.com/RSRH-Rs/DiscordRinBot"


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


def render(is_logged_in=False):
    env = Environment(loader=FileSystemLoader(str(ROOT / "website" / "templates")))
    env.globals["url_for"] = lambda endpoint, filename: "/static/" + filename
    env.globals["invite_url"] = site_data.invite_url()
    return env.get_template("index.html").render(is_logged_in=is_logged_in)


def tags(html):
    p = _Tags()
    p.feed(html)
    return p.tags


@pytest.fixture(scope="module")
def page():
    return render(False)


def test_invite_links_exact(page):
    invites = [a for t, a in tags(page) if t == "a" and "discord.com/oauth2" in a.get("href", "")]
    assert len(invites) >= 4
    for a in invites:
        assert a["href"] == INVITE
        assert a.get("target") == "_blank"
        assert "noopener" in a.get("rel", "")


def test_dashboard_and_github_links(page):
    hrefs = [a.get("href") for t, a in tags(page) if t == "a"]
    assert hrefs.count("/dashboard") >= 3
    assert GITHUB in hrefs
    assert GITHUB + "/issues" in hrefs


def test_login_copy_switches():
    out, inn = render(False), render(True)
    assert "登录控制台" in out and "Dashboard login" in out
    assert "进入控制台" in inn and "Open dashboard" in inn
    assert "进入控制台" not in out and "登录控制台" not in inn


def test_bilingual_pairs_balanced(page):
    zh = [a for _, a in tags(page) if a.get("data-l") == "zh"]
    en = [a for _, a in tags(page) if a.get("data-l") == "en"]
    assert len(zh) == len(en) > 20


def test_prepaint_script_in_head(page):
    head = page.split("</head>", 1)[0]
    assert "rinbot_lang" in head
    html_tag = next(a for t, a in tags(page) if t == "html")
    assert html_tag.get("data-lang") == "zh"


def test_no_heavy_deps(page):
    for needle in ("lucide", "Noto+Sans+SC", "rinbot_bg.jpg"):
        assert needle not in page


def test_static_refs_exist(page):
    refs = set(re.findall(r"/static/([^\s\"',)]+)", page))
    assert refs
    for ref in refs:
        assert (STATIC_DIR / ref).is_file(), ref


def test_scenes_present(page):
    ids = {a.get("id") for _, a in tags(page)}
    assert {"music", "welcome", "moderation", "dashboard"} <= ids
    sections = re.findall(r'<section[^>]*id="(music|welcome|moderation|dashboard)".*?</section>', page, re.S)
    assert len(sections) == 4
    for sid in ("music", "welcome", "moderation", "dashboard"):
        body = re.search(rf'<section[^>]*id="{sid}".*?</section>', page, re.S).group(0)
        assert 'class="panel' in body, sid
    assert page.count("manage-blink-") >= 1
    assert page.count("confused-blink-") >= 1


def test_hidden_states_gated_by_js(page):
    css = "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S))
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if re.search(r"opacity\s*:\s*0(?![.\d])", body):
            for sel in selector.split(","):
                assert sel.strip().startswith(("html.js", ".js")), sel.strip()


def test_reduced_motion_block_present(page):
    css = "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S))
    m = re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n    \}", css, re.S)
    assert m, "missing prefers-reduced-motion block"
    for cls in (".stk-blink", ".stk-bob", ".stk-sway"):
        assert cls in m.group(1), cls


def test_reveal_setup_runs_before_fetch(page):
    # 揭示场景消息的观察器必须先于 fetch 建好，fetch 出错也不会让消息一直隐藏
    script = re.findall(r"<script>(.*?)</script>", page, re.S)[-1]
    assert script.index("IntersectionObserver") < script.index("fetch(")
    assert "window.fetch" in script


def _luminance(hex_color):
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (文字色, 底色)：页面底色、面板、宽屏侧栏和 Discord 对话框里实际出现的组合，日间夜间各查一遍
TEXT_PAIRS = [
    ("text", "bg"), ("muted", "bg"), ("text", "panel"), ("muted", "panel"), ("accent-text", "bg"),
    ("on-accent", "accent"), ("accent-text", "accent-soft"),
    ("text", "side"), ("muted", "side"), ("text", "cur"), ("muted", "hover"),
    ("dc-text", "dc-bg"), ("dc-muted", "dc-bg"), ("dc-muted", "dc-deep"), ("accent-text", "dc-bg"), ("dc-text", "dc-deep"),
    ("dc-gold", "dc-deep"),
]


def _palette(page, selector):
    body = re.search(re.escape(selector) + r"\s*\{(.*?)\}", page, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", body))


@pytest.mark.parametrize("selector", [":root", ':root[data-theme="dark"]'])
@pytest.mark.parametrize("fg,bg", TEXT_PAIRS)
def test_text_colors_meet_contrast(page, selector, fg, bg):
    tokens = _palette(page, selector)
    assert _contrast(tokens[fg], tokens[bg]) >= 4.5, (selector, fg, bg)


def test_pink_text_uses_the_text_shade(page):
    # 樱粉 --accent 只给按钮和装饰；当文字用时要换成对比度够的 --accent-text
    assert "var(--accent-text)" in re.search(r"\.motto\s*\{([^}]*)\}", page).group(1)


def test_overview_links_point_to_sections(page):
    # 功能一览里的每一项都要跳到页面上真实存在的场景
    overview = re.search(r'<section class="overview".*?</section>', page, re.S).group(0)
    targets = re.findall(r'<a href="#([\w-]+)"', overview)
    assert len(targets) == 8
    ids = {a.get("id") for _, a in tags(page)}
    for tid in targets:
        assert tid in ids, tid


def test_hero_title_and_lead_break_on_purpose(page):
    # 中文标题上下两行字数相同；介绍一句一行，不让浏览器在句中随意断开
    title = re.search(r'<h1 id="hero-title"><span data-l="zh">(.*?)</span>', page).group(1)
    lines = title.split("<br>")
    assert len(lines) == 2 and len(lines[0]) == len(lines[1]), lines
    lead = re.search(r'<p class="lead">(.*?)</p>', page).group(1)
    for lang in ("zh", "en"):
        block = re.search(rf'<span data-l="{lang}"[^>]*>(.*?</span>)</span>', lead).group(1)
        sentences = re.findall(r'<span class="s">(.*?)</span>', block)
        assert len(sentences) == 2, block
        assert "—" not in block, block
    css = "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S))
    assert re.search(r"\.lead \.s \{[^}]*display:\s*block[^}]*text-wrap:\s*balance", css)


def test_sidebar_channels_link_to_sections(page):
    # 宽屏左侧的频道列表就是导航：每个频道跳到页面上真实存在的区块，并参与滚动高亮
    side = re.search(r'<aside class="side".*?</aside>', page, re.S).group(0)
    spies = re.findall(r'<a href="#([\w-]+)" data-spy="([\w-]+)"', side)
    assert [h for h, _ in spies] == ["lobby", "music", "welcome", "moderation", "dashboard"]
    assert all(h == s for h, s in spies)
    ids = {a.get("id") for _, a in tags(page)}
    for h, _ in spies:
        assert h in ids, h


def test_sidebar_only_on_wide_screens(page):
    css = "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S))
    assert re.search(r"\.side \{[^}]*display:\s*none", css)
    wide = re.search(r"@media \(min-width: 1440px\) \{(.*?)\n    \}", css, re.S)
    assert wide and ".side" in wide.group(1) and "padding-left" in wide.group(1)


def test_modlog_shows_edit_and_join_records(page):
    section = re.search(r'<section[^>]*id="moderation".*?</section>', page, re.S).group(0)
    for needle in ("✏️ 消息被编辑", "🚪 成员加入", "Message edited", "Member joined"):
        assert needle in section, needle
