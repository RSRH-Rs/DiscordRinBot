# Website Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** rin-bot.com gains five pages — `/commands`, `/permissions`, `/privacy`, `/terms` and a real 404 — on a shared site shell that the homepage moves onto without changing how it looks.

**Architecture:** The homepage's tokens, nav, footer, wide sidebar and language script move out of `index.html` into `_site_base.html` + `site.css` + `site.js`; every public page extends that base. Page data that both templates and tests need lives in `website/site_data.py`; the command list is generated offline from the cogs into `website/data/commands.json` and guarded by a drift test. Pages render fully on the server in both languages (`data-l` spans); small page scripts add search, selection and the live invite link.

**Tech Stack:** Quart + Jinja2, vanilla JS (no build, IIFE globals tested with `node:test` + `vm`), plain CSS files under `website/static/css/`, pytest/unittest.

**Spec:** `docs/superpowers/specs/2026-11-05-site-pages-design.md` (mockups: `docs/superpowers/specs/assets/2026-11-05-*-demo.html` — copy, group texts and permission reasons are taken from them verbatim).

## Global Constraints

- Bot code, console templates, `console.css` and databases are not touched.
- The homepage must render the same as before except the three links of spec §3.3 and the nav "指令" item; all existing homepage assertions keep their intent (only *where* they read CSS/JS from changes).
- Token values already on the homepage do not change; new tokens (Task 3) are added to all three palette blocks (light, `:root[data-theme="dark"]`, system dark) with identical dark values.
- Font sizes: `site.css` only 12, 14, 15, 16, 18px (the homepage chrome moved as is); `commands.css`, `permissions.css`, `legal.css` only 12.5, 14, 15, 16, 19, 24, 32, 40px.
- Pink (`--accent*`) only on clickable or selected things; ticked permission boxes use `--dc-name`; the search box `/` uses `--muted`.
- No CDN scripts, frameworks or build tools; only Fredoka from Google Fonts (already loaded).
- Both languages on every page via `t(zh, en)`; attribute text through the page's `#attr-i18n` JSON.
- Every page: no horizontal scroll at 375px; visible `:focus-visible`; `prefers-reduced-motion` turns off all transitions.
- Write files with LF line endings. Commit on master with `feat:` / `fix:` / `style:` / `docs:` + lowercase imperative summary and a body. Do not push. Never commit `rinbot/cogs/netease.py` or files another session left in the tree (e.g. `tests/test_guild_cleanup.py`) — `git add` only the paths a task names.
- Test commands: `python -m pytest -q` (root), `cd website && python -m pytest -q tests`, `node --test website/tests/*.test.cjs`.

## Review Focus

1. A `/commands` link with an unknown or malformed hash (`#nope`, `#%zz`, `#ban%20`) — expect the first command selected and no exception (Task 6, `idFromHash` test).
2. Search text that looks like markup or regex (`<b>`, `(`, `\`, `/`) — expect a literal match and escaped output in highlights (Task 6, `highlight` test).
3. A 404 path containing HTML or 300 characters — expect it escaped and cut to 80 characters, and any `/api/...` miss to stay JSON (Task 5 tests).
4. An existing server `config.py` without `CONTACT_EMAIL` — expect the site to start and the privacy page to fall back to GitHub issues (Task 5 test).
5. `/permissions` with JavaScript off — expect unticking to still show the "取消后" note (CSS `:has`) and the invite button to carry the full default link (Task 7 test).

---

### Task 1: Site data module and the shared invite link

**Files:**
- Create: `website/site_data.py`
- Modify: `website/routes.py` (inside `setup_routes`), `website/templates/index.html:8` (drop `{% set invite_url %}`)
- Test: `tests/test_site_data.py`; modify `tests/test_homepage.py::render`

**Interfaces:**
- Produces (all in `site_data`):
  - `CLIENT_ID = 1352551616427069492`, `INVITE_PERMISSIONS = 1374694796438`
  - `invite_url(permissions: int = INVITE_PERMISSIONS) -> str` → `https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&permissions={permissions}&integration_type=0&scope=bot+applications.commands`
  - `PERMISSION_GROUPS: list[dict]` keys `key, zh, en`; keys in order `msg, voice, roles, mod, log`
  - `PERMISSIONS: list[dict]` keys `bit, group, zh, en, why_zh, why_en, lose_zh, lose_en` — 16 entries, values and order exactly as `GROUPS` in the permissions mockup
  - `NEVER: list[dict]` keys `bit, zh, en, why_zh, why_en` — Administrator (3), Manage Server (5), Mention @everyone (17), Manage Webhooks (29), texts from the mockup
  - `COMMAND_GROUPS: list[dict]` keys `key, zh, en, desc_zh, desc_en, dashboard, dashboard_zh, dashboard_en` — the ten groups of the commands mockup's `GROUPS`, `dashboard=None` for `General`
  - `PERM_LABELS: dict[str, tuple[str, str]]` for `manage_guild, kick_members, ban_members, moderate_members, manage_messages, manage_channels, manage_roles`
  - Jinja global `invite_url` (the default URL string), set in `setup_routes` via `app.jinja_env.globals["invite_url"] = site_data.invite_url()`

- [ ] **Step 1: Write the failing tests** in `tests/test_site_data.py`

```python
import site_data as sd

OLD = ("https://discord.com/oauth2/authorize?client_id=1352551616427069492"
       "&permissions=1374694796438&integration_type=0&scope=bot+applications.commands")

def test_permission_bits_add_up_to_the_invite():
    assert len(sd.PERMISSIONS) == 16
    assert sum(1 << p["bit"] for p in sd.PERMISSIONS) == sd.INVITE_PERMISSIONS
    assert len({p["bit"] for p in sd.PERMISSIONS}) == 16

def test_invite_url_is_unchanged():
    assert sd.invite_url() == OLD
    assert "permissions=6&" in sd.invite_url(6)

def test_never_bits_are_not_requested():
    assert [n["bit"] for n in sd.NEVER] == [3, 5, 17, 29]
    assert all(not sd.INVITE_PERMISSIONS >> n["bit"] & 1 for n in sd.NEVER)

def test_groups_are_complete():
    assert [g["key"] for g in sd.PERMISSION_GROUPS] == ["msg", "voice", "roles", "mod", "log"]
    assert {p["group"] for p in sd.PERMISSIONS} == {g["key"] for g in sd.PERMISSION_GROUPS}
    keys = [g["key"] for g in sd.COMMAND_GROUPS]
    assert len(keys) == 10 == len(set(keys)) and keys[0] == "Music" and keys[-1] == "System"
    for entry in sd.PERMISSIONS + sd.COMMAND_GROUPS:
        assert all(entry[k] for k in entry if k.endswith(("zh", "en")) and k not in ("dashboard_zh", "dashboard_en"))
```

Also change `tests/test_homepage.py::render` to set `env.globals["invite_url"] = site_data.invite_url()` (import `site_data`).

- [ ] **Step 2: Run to see them fail** — `python -m pytest -q tests/test_site_data.py` → `ModuleNotFoundError: site_data`.
- [ ] **Step 3: Implement `website/site_data.py`** with the values above, then set the Jinja global in `setup_routes` and delete line 8 of `index.html`.
- [ ] **Step 4: Run** `python -m pytest -q tests/test_site_data.py tests/test_homepage.py` → all pass (`test_invite_links_exact` proves the homepage link is unchanged).
- [ ] **Step 5: Commit** `feat: keep the invite link and site page data in one module` (add `website/site_data.py`, `website/routes.py`, `website/templates/index.html`, `tests/test_site_data.py`, `tests/test_homepage.py`).

---

### Task 2: Generated command catalog

**Files:**
- Create: `website/tools/build_commands.py`, `website/data/commands.json` (generated)
- Test: `tests/test_command_catalog.py`

**Interfaces:**
- Consumes: `site_data.COMMAND_GROUPS`, `site_data.PERM_LABELS`.
- Produces: `build_commands.build_catalog() -> dict` (`{"commands": [...]}`), `build_commands.DATA_PATH: pathlib.Path` (`website/data/commands.json`), `python website/tools/build_commands.py` rewrites the file. Each entry: `name, id, group, en, zh, perms, params[{name, required, en, zh, zh_desc}], examples` (spec §5.1, keys in that order).

- [ ] **Step 1: Write the failing tests**

```python
import importlib.util, json, pathlib
import site_data as sd

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_commands", ROOT / "website/tools/build_commands.py")
bc = importlib.util.module_from_spec(spec); spec.loader.exec_module(bc)

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
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_command_catalog.py` → fails (tool missing).
- [ ] **Step 3: Implement `build_catalog()`** — put `rinbot/` first and `rinbot/cogs/` last on `sys.path` (same order as `tests/conftest.py`), import each `rinbot/cogs/*.py` except `_*.py` and `netease.py`, take each Cog class's top-level app commands that `_perms.is_owner_only` rejects, walk `.commands` to leaf commands (skip `app_commands.Group`), `group = {"CommandToggle": "System", "Help": "System"}.get(cog, cog)`, `perms` = names of true flags in the top-level `default_permissions`, merge `rinbot/i18n/commands.zh.json` (`description`, `params[name].name/description`, `examples`). Order commands by `COMMAND_GROUPS` order, then cog definition order. `main()` writes `json.dumps(..., ensure_ascii=False, indent=2) + "\n"` with `newline="\n"`.
- [ ] **Step 4: Generate and run** `python website/tools/build_commands.py && python -m pytest -q tests/test_command_catalog.py` → pass.
- [ ] **Step 5: Commit** `feat: generate the public command list from the cogs` (tool, json, test).

---

### Task 3: Shared site shell (homepage looks the same)

**Files:**
- Create: `website/templates/_site_base.html`, `website/templates/_site_macros.html`, `website/static/css/site.css`, `website/static/js/site.js`
- Modify: `website/templates/index.html`
- Test: `tests/test_homepage.py`, `website/tests/test_homepage_theme.py`, create `website/tests/test_site_css.py`, `website/tests/site_shell.test.cjs`

**Interfaces:**
- Produces:
  - `_site_base.html` blocks `title`, `description`, `head` (page stylesheets), `side` (optional wide sidebar; empty by default), `content`, `scripts`; a page sets `{% set active_nav = 'home' | 'commands' | 'permissions' | 'privacy' | 'terms' | '' %}` before `{% extends %}`. The base contains the two boot scripts, theme-color metas, Fredoka link, favicon, `site.css`, `#nav`, `<main>`, footer and `site.js`, and takes `is_logged_in`.
  - `_site_macros.html`: `t(zh, en)`, `sticker(name, size, cls='')`, `rin_av()`, `demo_av(file)`, `chips(cmds)` moved unchanged from `index.html`.
  - Page attribute strings: `<script type="application/json" id="attr-i18n">{"zh": {...}, "en": {...}}</script>` with keys `title`, `description`, `toggle` and any `data-i18n-alt` / `data-i18n-aria` keys.
  - `site.js` global `RinSite = {setLang(lang), applyAttrs(lang)}`; `window.rinSetLang = RinSite.setLang` (homepage button keeps working); `setLang` stores `rinbot_lang`, updates `data-lang`/`lang`, calls `applyAttrs`, dispatches `document.dispatchEvent(new CustomEvent('rin:lang', {detail: {lang}}))`. It also runs the nav `.scrolled` line and the `[data-spy]` sidebar highlight (rootMargin `-45% 0px -50% 0px`).
  - `site.css` holds every token (homepage values) plus new ones in all three palette blocks: `--field #FFFFFF/#17171B`, `--field-line #8A8A93/#6A6A74`, `--warn #A15C00/#F5B94A`, `--warn-soft #FFF4E0/#33270F`, `--ok #1A7A43/#3DD68C`, `--row-hover #EFEFF2/#1F1F25`, `--mark #FFE7A3/#5A4512`, `--dc-input #EBEDEF/#383A40`, `--dc-slot #DFE1E5/#4E5058`; base `body { background: var(--bg) }` (the homepage keeps its grain/wash `body` rule inline), buttons, `.link`, nav, `.side`/rail/channels, footer, `data-l` rules, focus ring, the 600px nav rules.

- [ ] **Step 1: Move the homepage tests to the new sources first** (they must fail now):
  - `tests/test_homepage.py`: add a module fixture `styles` = rendered page + `site.css` text; `test_hidden_states_gated_by_js`, `test_reduced_motion_block_present`, `test_hero_title_and_lead_break_on_purpose` (CSS part), `test_sidebar_only_on_wide_screens`, `test_text_colors_meet_contrast` and `test_pink_text_uses_the_text_shade` read `styles` (inline `<style>` blocks plus `site.css`) instead of only `<style>` in the page. Add `test_page_extends_the_site_base`: `index.html` source starts with `{%- extends '_site_base.html'` and has no `<nav class="nav"`.
  - `website/tests/test_homepage_theme.py`: tokens come from `site.css` (`:root`, `:root[data-theme="dark"]`, system-dark block); boot-script checks read `_site_base.html` and compare against the `site.css` `<link>` instead of `<style>`; `test_no_old_palette_left` scans `index.html`, `_site_base.html` and `site.css`.
  - `website/tests/test_site_css.py`: both palettes meet 4.5:1 for `text/bg, muted/bg, text/panel, muted/panel, accent-text/bg, on-accent/accent, accent-text/accent-soft, warn/warn-soft, warn/bg, text/mark, text/row-hover, dc-name/dc-slot, dc-text/dc-input, dc-muted/dc-deep`; `field-line` vs `bg` ≥ 3:1; system dark equals manual dark; font sizes in `site.css` ⊆ {12, 14, 15, 16, 18}; the reduced-motion block disables `transition` and `animation`.
  - `website/tests/site_shell.test.cjs`: in a `vm` context with stub `document`/`localStorage`, `RinSite.setLang('en')` sets `data-lang="en"`, writes `rinbot_lang`, sets `document.title` from `#attr-i18n`, dispatches one `rin:lang` event with `detail.lang === 'en'`; with `localStorage` throwing it still switches.
- [ ] **Step 2: Run** the four files → the moved-source tests fail.
- [ ] **Step 3: Build the shell** — cut the shared CSS/markup/JS out of `index.html` into the four new files without changing values; `index.html` keeps only page CSS (`<style>` inside `{% block head %}`), page markup and its page script (stage/sticker observers and `/api/stats`), and supplies `#attr-i18n` with its current `ATTR_I18N` strings. The homepage sidebar channels go in `{% block side %}`.
- [ ] **Step 4: Run** `python -m pytest -q tests/test_homepage.py`, `cd website && python -m pytest -q tests/test_homepage_theme.py tests/test_site_css.py`, `node --test website/tests/site_shell.test.cjs` → pass. Then diff the rendered homepage text before/after (render with the test's `render()` and compare `re.sub(r'\s+', ' ', text_only)`) — identical.
- [ ] **Step 5: Commit** `style: move the homepage nav, footer and colours into a shared site shell`.

---

### Task 4: Site-wide links to the new pages

**Files:**
- Modify: `website/templates/_site_base.html`, `website/templates/index.html`, `website/static/css/site.css`
- Test: `tests/test_homepage.py`

**Interfaces:**
- Consumes: `active_nav` from Task 3.
- Produces: nav order brand, 中/EN, 指令 (`/commands`), 控制台, 邀请小凛, with `aria-current="page"` on the item matching `active_nav`; below 600px the brand text hides (avatar only). Footer links in order: 控制台, 邀请小凛, 指令大全, 邀请权限, 隐私政策, 服务条款, GitHub, 反馈问题. Homepage: "查看全部指令" next to the overview heading, "邀请前看看小凛要哪些权限" under the hero buttons, "不需要管理员权限" fact links to `/permissions`.

- [ ] **Step 1: Write failing tests** `test_nav_has_commands_between_language_and_dashboard` (order of hrefs/ids inside `#nav`: `lang-toggle`, `/commands`, `/dashboard`, invite), `test_footer_links_new_pages` (the eight hrefs in order), `test_homepage_points_to_commands_and_permissions` (overview section contains `href="/commands"`; hero contains `href="/permissions"`; the facts list item with 不需要管理员权限 is inside `<a href="/permissions"`).
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Add the links** in base and homepage (copy pairs: 指令/Commands, 查看全部指令/See all commands, 邀请前看看小凛要哪些权限/See what Rin asks for before inviting, 邀请权限/Invite permissions, 隐私政策/Privacy, 服务条款/Terms).
- [ ] **Step 4: Run** `python -m pytest -q tests/test_homepage.py` → pass; check 375px nav fits in the browser (avatar, 指令, EN, 控制台, 邀请小凛 on one line).
- [ ] **Step 5: Commit** `feat: link the commands, permissions and policy pages from every page`.

---

### Task 5: Privacy, terms and the 404 page

**Files:**
- Create: `website/templates/privacy.html`, `website/templates/terms.html`, `website/templates/not_found.html`, `website/static/css/legal.css`
- Modify: `website/routes.py`, `website/config.example.py` (add `CONTACT_EMAIL = ""` with a comment that it is shown on the privacy page)
- Test: create `tests/test_site_pages.py`; extend `website/tests/test_site_css.py`

**Interfaces:**
- Consumes: `_site_base.html`, `t()`.
- Produces in `routes.py`:
  - module level `CONTACT_EMAIL = getattr(config, "CONTACT_EMAIL", "")` (add `import config`; the test stub module has no such attribute)
  - module level `SITE_PAGES = ("commands", "permissions", "privacy", "terms", "dashboard")` and `suggest_page(path: str) -> str | None` = `difflib.get_close_matches(path.strip("/").lower(), SITE_PAGES, n=1, cutoff=0.6)` first item or `None`
  - inside `setup_routes`: `async def _site_page(template: str, **ctx)` rendering with `is_logged_in` (same try/except as `index`), routes `/privacy`, `/terms`, and `@app.errorhandler(404)` → `/api/` prefix: `jsonify({"error": "not found"}), 404`; else `not_found.html` with `path=request.path[:80]`, `suggestion=suggest_page(request.path)`, status 404
  - templates receive `contact_email`
- Copy: spec §7.2 (privacy, chinese draft in the legal mockup) and §7.3 (terms), both languages. Before writing §delete, check `git log` for the guild data cleanup work (another session): if it has landed, say data is deleted 30 days after Rin is removed instead of "not deleted automatically"; "最后更新" = the implementation date; section ids `keep, read, web, others, delete, logs, age, changes, contact`; when `contact_email` is empty, §delete and §contact link to `https://github.com/RSRH-Rs/DiscordRinBot/issues` and add "issue 是公开的，不要贴出别人的 ID" / "Issues are public — don't post other people's IDs". 404 copy per spec §8; suggestion line names the page (指令大全 / 邀请权限 / 隐私政策 / 服务条款 / 控制台).

- [ ] **Step 1: Write failing tests** in `tests/test_site_pages.py` (load `routes` with a stub `config` module the way `website/tests/test_bot_avatar.py` does; build `Quart(__name__)` + `routes.setup_routes(app, FakeDiscord())` with `authorized` returning False; clear `before_serving_funcs`):

```python
@pytest.mark.parametrize("path,expected", [("/comands", "commands"), ("/privacy-policy", "privacy"),
                                           ("/TERMS/", "terms"), ("/xyz", None), ("/", None)])
def test_suggest_page(path, expected):
    assert routes.suggest_page(path) == expected

async def test_privacy_and_terms_render(client):
    for path in ("/privacy", "/terms"):
        r = await client.get(path); html = await r.get_data(as_text=True)
        assert r.status_code == 200 and 'aria-current="page"' in html
        assert html.count('data-l="zh"') == html.count('data-l="en"')

async def test_privacy_contact_falls_back_to_issues(client, monkeypatch):
    monkeypatch.setattr(routes, "CONTACT_EMAIL", "")
    html = await (await client.get("/privacy")).get_data(as_text=True)
    assert "mailto:" not in html and "DiscordRinBot/issues" in html
    monkeypatch.setattr(routes, "CONTACT_EMAIL", "rin@example.com")
    assert 'href="mailto:rin@example.com"' in await (await client.get("/privacy")).get_data(as_text=True)

async def test_unknown_page_is_a_friendly_404(client):
    r = await client.get("/comands"); html = await r.get_data(as_text=True)
    assert r.status_code == 404 and 'href="/commands"' in html
    assert html.count('data-l="zh"') == html.count('data-l="en"')
    r = await client.get("/<script>" + "x" * 300)
    html = await r.get_data(as_text=True)
    assert r.status_code == 404 and "<script>xxx" not in html and "x" * 81 not in html

async def test_api_misses_stay_json(client):
    r = await client.get("/api/nope")
    assert r.status_code == 404 and (await r.get_json()) == {"error": "not found"}
```

Extend `test_site_css.py`: `legal.css` font sizes ⊆ {12.5, 14, 15, 16, 19, 24, 32, 40}; prose blocks `max-width: 38em`; `.data` table `760px`.
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement** routes, templates and `legal.css` per spec §7.1 and §8 (table stacks below 640px with "删除：/Removed:" prefix; 404 sticker `confused-480.webp` 180px, 120px on phones; no sidebar).
- [ ] **Step 4: Run** `python -m pytest -q tests/test_site_pages.py && cd website && python -m pytest -q tests` → pass.
- [ ] **Step 5: Commit** `feat: add privacy, terms and a 404 page that suggests the right address`.

---

### Task 6: Commands page

**Files:**
- Create: `website/templates/commands.html`, `website/static/css/commands.css`, `website/static/js/commands.js`
- Modify: `website/routes.py`
- Test: `tests/test_site_pages.py`, `website/tests/commands_page.test.cjs`, `website/tests/test_site_css.py`

**Interfaces:**
- Consumes: `website/data/commands.json` (Task 2), `site_data.COMMAND_GROUPS`, `site_data.PERM_LABELS`, `_site_page`, `RinSite` + `rin:lang` (Task 3).
- Produces:
  - `routes.COMMAND_CATALOG` loaded once in `setup_routes` from `website/data/commands.json`; route `/commands` passes `commands`, `groups`, `perm_labels` and embeds `{"commands", "groups", "perm_labels"}` in `<script type="application/json" id="commands-data">`.
  - Markup per spec §5.3: `#list[role=listbox]` > `section.sec#g-{key}[data-group]` > `.rows` > `button.row[role=option][id=r-{id}][data-id][aria-selected]`; subcommand names render as `<span class="pre">/automod</span> whitelist add`; the description cell is one line with ellipsis and the full text in `title`; text spans that search may highlight carry `data-hl` and keep their text in `data-text`; group-shared permission sentence vs per-row permission per spec; sidebar channels `a[href="#g-{key}"][data-spy="g-{key}"]` with a count `span.n` — while searching, channels with no match hide and counts show the matches.
  - `commands.js` global `RinCommands` pure helpers:
    - `normalize(q: string) -> string` (lowercase, trim, drop one leading `/`)
    - `matches(cmd, q: string) -> boolean` (name, zh, en, each param's name/zh/zh_desc/en)
    - `highlight(text: string, q: string) -> string` (escaped HTML, first match wrapped in `<mark>`)
    - `examplesFor(cmd, lang: 'zh'|'en') -> string[]` (en drops any containing `/[　-鿿＀-￯]/`)
    - `slotsFor(cmd, focus: number) -> {shown: object[], rest: number}` (required params, plus the focused param if optional; `rest` = optional count not shown)
    - `step(ids: string[], current: string|null, delta: 1|-1) -> string|null` (clamped, `null` for empty)
    - `idFromHash(hash: string, ids: string[]) -> string|null` (safe `decodeURIComponent`)
  - Behaviour per spec §5.4–5.5: detail panel / inline detail below 1080px, Discord box with hover/click focus, copy button + toast, dashboard link (`/dashboard`), `#id` via `history.replaceState`, keyboard (`/`, Enter, Esc, ↑↓), empty state with `confused-480.webp` 88px and four suggestion buttons, `role=status` count, re-render on `rin:lang`.

- [ ] **Step 1: Write failing tests**
  - `commands_page.test.cjs` (load `commands.js` in `vm` with `document.getElementById` returning `null` so no DOM wiring runs):

```js
const ban = {name:'ban', zh:'封禁一名成员', en:'Ban a member', params:[
  {name:'member', required:true, en:'The member', zh:'成员', zh_desc:'要封禁的成员'},
  {name:'duration', required:false, en:'How long', zh:'时长', zh_desc:'封禁多久'},
  {name:'reason', required:false, en:'Why', zh:'原因', zh_desc:'原因'}],
  examples:['/ban @小明 7d 刷屏', '/ban 123 spam']};
test('search is literal and ignores a leading slash', () => {
  assert.equal(C.matches(ban, '/BAN'), true);
  assert.equal(C.matches(ban, '时长'), true);
  assert.equal(C.matches(ban, '('), false);
});
test('highlight escapes markup', () => {
  assert.equal(C.highlight('<b>ban</b>', 'ban'), '&lt;b&gt;<mark>ban</mark>&lt;/b&gt;');
  assert.equal(C.highlight('a\\b', '\\'), 'a<mark>\\</mark>b');
});
test('english hides chinese examples', () => {
  assert.deepEqual(C.examplesFor(ban, 'en'), ['/ban 123 spam']);
  assert.equal(C.examplesFor(ban, 'zh').length, 2);
});
test('slots show required plus the focused optional', () => {
  assert.deepEqual(C.slotsFor(ban, 0).shown.map(p => p.name), ['member']);
  assert.equal(C.slotsFor(ban, 0).rest, 2);
  assert.deepEqual(C.slotsFor(ban, 2).shown.map(p => p.name), ['member', 'reason']);
  assert.equal(C.slotsFor(ban, 2).rest, 1);
});
test('arrow keys clamp and hashes are safe', () => {
  assert.equal(C.step(['a','b'], 'b', 1), 'b');
  assert.equal(C.step(['a','b'], null, 1), 'a');
  assert.equal(C.step([], 'a', -1), null);
  assert.equal(C.idFromHash('#ban', ['ban']), 'ban');
  for (const h of ['#nope', '#%zz', '', '#']) assert.equal(C.idFromHash(h, ['ban']), null);
});
```

  - `tests/test_site_pages.py::test_commands_page`: `/commands` → 200; `data-l="zh"` and `data-l="en"` counts equal; 68 `role="option"` rows; `/automod whitelist add` row contains `class="pre"`; ten `section` ids `g-Music` … `g-System`; `id="commands-data"` JSON parses and has 68 commands; AutoMod section mentions 管理服务器 once in its intro and no row in it has `class="perm"`; nav has `aria-current` on 指令.
  - `test_site_css.py`: `commands.css` font sizes ⊆ the page scale; `.search .slash` uses `var(--muted)`; the sticky panel has `max-height` and `overflow-y: auto`.
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement** route, template, CSS (spec §5.2 grid: `minmax(0, 1fr) 360px`, gap 48px, panel sticky `top: 88px`; rows on a shared `subgrid`; one column below 1080px) and `commands.js`.
- [ ] **Step 4: Run** `node --test website/tests/commands_page.test.cjs && python -m pytest -q tests/test_site_pages.py && cd website && python -m pytest -q tests/test_site_css.py` → pass.
- [ ] **Step 5: Commit** `feat: add a searchable commands page with a discord message box preview`.

---

### Task 7: Invite permissions page

**Files:**
- Create: `website/templates/permissions.html`, `website/static/css/permissions.css`, `website/static/js/permissions.js`
- Modify: `website/routes.py`
- Test: `tests/test_site_pages.py`, `website/tests/permissions_page.test.cjs`, `website/tests/test_site_css.py`

**Interfaces:**
- Consumes: `site_data.PERMISSION_GROUPS`, `PERMISSIONS`, `NEVER`, `invite_url`, `_site_page`.
- Produces:
  - route `/permissions`; markup per spec §6.2: `.auth` card with `label.perm > input[type=checkbox][data-bit][checked]`, `.why`, `.lose`; `aside.side` whose default content is the invite button `a.btn[href=invite_url]`; `section#role-order`; never-asked flat list.
  - `permissions.js` global `RinPermissions`:
    - `bitsFor(bits: number[]) -> bigint` (OR of `1n << BigInt(bit)`)
    - `inviteHref(base: string, bits: bigint) -> string` (`new URL(base)`, `searchParams.set('permissions', String(bits))`, returns `href`)
    - `missing(perms: object[], unticked: Set<number>) -> object[]` (input order kept)
  - CSS: ticked box `background: var(--dc-name)`; `.perm:has(input:not(:checked)) .lose { display: block }` and struck-through `.name` — no JS needed for the note.

- [ ] **Step 1: Write failing tests**
  - `permissions_page.test.cjs`:

```js
const all = [1,2,4,7,10,11,13,14,15,16,20,21,25,28,38,40];
test('bits match the live invite', () => {
  assert.equal(P.bitsFor(all), 1374694796438n);
  assert.equal(P.bitsFor(all.filter(b => b !== 1 && b !== 7)), 1374694796438n - 2n - 128n);
});
test('invite link only changes the permissions value', () => {
  const base = 'https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=1374694796438&integration_type=0&scope=bot+applications.commands';
  assert.equal(P.inviteHref(base, 1374694796438n), base);
  assert.match(P.inviteHref(base, 6n), /permissions=6&integration_type=0/);
});
test('missing keeps list order', () => {
  const perms = [{bit:10},{bit:1},{bit:7}];
  assert.deepEqual(P.missing(perms, new Set([7, 10])).map(p => p.bit), [10, 7]);
});
```

  - `tests/test_site_pages.py::test_permissions_page`: 200; `data-l` zh/en counts equal; 16 checked `data-bit` inputs whose bits equal `site_data.PERMISSIONS`; default `.side` invite href equals `site_data.invite_url()` (HTML-unescaped); `id="role-order"` present; the four never-asked names present in both languages.
  - `test_site_css.py`: `permissions.css` font sizes ⊆ page scale; contains `:has(input:not(:checked))`; `input:checked` rule uses `var(--dc-name)`, not `--accent`.
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement** route, template, CSS (grid `minmax(0, 640px) 360px`, gap 48px; one column below 1080px) and `permissions.js` (summary, "全部勾回", button text "按这里的勾选邀请小凛" when anything is unticked; re-render on `rin:lang`).
- [ ] **Step 4: Run** `node --test website/tests/permissions_page.test.cjs && python -m pytest -q tests/test_site_pages.py && cd website && python -m pytest -q tests/test_site_css.py` → pass.
- [ ] **Step 5: Commit** `feat: explain each invite permission and what breaks without it`.

---

### Task 8: Docs and full check in the browser

**Files:**
- Modify: `README.md`, `README.zh-CN.md`
- Not committed: the scratchpad preview script (add routes `/commands`, `/permissions`, `/privacy`, `/terms` and a 404 fallback that render the real templates with `invite_url` and `contact_email`)

- [ ] **Step 1: README** — list the five pages under the website section; replace the README invite link (currently `permissions=8`, i.e. Administrator) with `site_data.invite_url()`'s exact URL in both READMEs; update the test counts in the "Tests" commands block to the new totals.
- [ ] **Step 2: Run everything** — `python -m pytest -q`, `cd website && python -m pytest -q tests`, `node --test website/tests/*.test.cjs` → all green; record the totals.
- [ ] **Step 3: Browser pass** with the preview script, spec §9.3 list, plus: switch language while a command is selected and a search is active (panel, count and highlights follow the new language); `/permissions` with JavaScript disabled still shows the "取消后" note when unticking; screenshot each page at 1440 and 375.
- [ ] **Step 4: Fix anything found** (each fix its own `fix:` commit with a test where one can pin it).
- [ ] **Step 5: Commit** `docs: list the new website pages and use the real invite link in the readme`.
