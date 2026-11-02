"""官网首页（website/templates/index.html）与其贴纸资源的静态检查。"""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
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
        assert 'class="scene-channel' in body, sid
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
