"""官网新页面：隐私政策、服务条款、404（之后还有指令大全和邀请权限）。

不读真的 config.py，也不连 Discord：路由模块用一个只有测试值的 config 加载，
页面用真模板渲染。
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest
from quart import Quart

WEBSITE = Path(__file__).resolve().parent.parent / "website"

_config = types.ModuleType("config")
_config.BOT_TOKEN = "test-only-not-a-real-token"
_config.OWNER_ID = 1
_spec = importlib.util.spec_from_file_location("site_pages_test_routes", WEBSITE / "routes.py")
routes = importlib.util.module_from_spec(_spec)
_previous = sys.modules.get("config")
sys.modules["config"] = _config
try:
    _spec.loader.exec_module(routes)
finally:
    if _previous is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = _previous


class FakeDiscord:
    @property
    async def authorized(self):
        return False


@pytest.fixture
def client():
    app = Quart(__name__, template_folder=str(WEBSITE / "templates"),
                static_folder=str(WEBSITE / "static"), static_url_path="/static")
    routes.setup_routes(app, FakeDiscord())
    app.before_serving_funcs.clear()
    app.after_serving_funcs.clear()
    return app.test_client()


def test_config_without_contact_email_still_loads():
    assert routes.CONTACT_EMAIL == ""


@pytest.mark.parametrize("path,expected", [
    ("/comands", "commands"), ("/privacy-policy", "privacy"), ("/TERMS/", "terms"),
    ("/permission", "permissions"), ("/xyz", None), ("/", None),
])
def test_suggest_page(path, expected):
    assert routes.suggest_page(path) == expected


async def test_privacy_and_terms_render(client):
    for path in ("/privacy", "/terms"):
        r = await client.get(path)
        html = await r.get_data(as_text=True)
        assert r.status_code == 200, path
        assert 'aria-current="page"' in html, path
        assert html.count('data-l="zh"') == html.count('data-l="en"'), path
        assert "css/legal.css" in html, path


async def test_privacy_sections_can_be_linked(client):
    html = await (await client.get("/privacy")).get_data(as_text=True)
    for anchor in ("keep", "read", "web", "others", "delete", "logs", "age", "changes", "contact"):
        assert f'id="{anchor}"' in html and f'href="#{anchor}"' in html, anchor
    assert html.count("<tr>") == 10  # 表头加九行


async def test_privacy_contact_falls_back_to_issues(client, monkeypatch):
    monkeypatch.setattr(routes, "CONTACT_EMAIL", "")
    html = await (await client.get("/privacy")).get_data(as_text=True)
    assert "mailto:" not in html and "DiscordRinBot/issues" in html
    assert "issue 是公开的" in html
    monkeypatch.setattr(routes, "CONTACT_EMAIL", "rin@example.com")
    html = await (await client.get("/privacy")).get_data(as_text=True)
    assert 'href="mailto:rin@example.com"' in html and "issue 是公开的" not in html


async def test_unknown_page_is_a_friendly_404(client):
    r = await client.get("/comands")
    html = await r.get_data(as_text=True)
    assert r.status_code == 404 and 'href="/commands"' in html
    assert html.count('data-l="zh"') == html.count('data-l="en"')
    assert "confused-480.webp" in html


async def test_404_escapes_and_shortens_the_path(client):
    r = await client.get("/<script>" + "x" * 300)
    html = await r.get_data(as_text=True)
    assert r.status_code == 404
    assert "<script>xxx" not in html and "x" * 81 not in html


async def test_api_misses_stay_json(client):
    r = await client.get("/api/nope")
    assert r.status_code == 404 and (await r.get_json()) == {"error": "not found"}


async def test_commands_page(client):
    import json
    import re
    r = await client.get("/commands")
    html = await r.get_data(as_text=True)
    assert r.status_code == 200
    assert html.count('data-l="zh"') == html.count('data-l="en"')
    assert html.count('role="option"') == 68
    assert re.findall(r'<section class="sec" id="g-(\w+)"', html) == [
        "Music", "Leveling", "Welcome", "Giveaway", "ReactionRoles", "Moderation", "AutoMod", "ServerLog", "General", "System"]
    row = re.search(r'<button[^>]*id="r-automod-whitelist-add".*?</button>', html, re.S).group(0)
    assert 'class="pre"' in row
    data = json.loads(re.search(r'<script type="application/json" id="commands-data">(.*?)</script>', html, re.S).group(1))
    assert len(data["commands"]) == 68 and len(data["groups"]) == 10 and "ban_members" in data["perm_labels"]
    automod = re.search(r'<section class="sec" id="g-AutoMod".*?</section>', html, re.S).group(0)
    intro = re.search(r'<div class="sec-head">.*?</div>', automod, re.S).group(0)
    assert intro.count("管理服务器") == 1 and 'class="perm"' not in automod
    moderation = re.search(r'<section class="sec" id="g-Moderation".*?</section>', html, re.S).group(0)
    assert 'class="perm"' in moderation
    nav = re.search(r'<nav class="nav".*?</nav>', html, re.S).group(0)
    assert re.search(r'<a href="/commands" class="nav-link" aria-current="page">', nav)
    assert 'class="has-side"' in html and 'data-spy="g-Music"' in html
