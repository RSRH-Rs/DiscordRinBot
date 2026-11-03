# Console Flat-List Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every console page shares one left edge and a 680px flat-list column, the shell drops the desktop top bar and gains a row back to the homepage, and the homepage takes the console palette including night mode.

**Architecture:** Mostly template and stylesheet work on the existing Quart/Jinja console: `console.css` sections (shell → controls → pages → responsive) are rewritten in place, templates keep every form id, and two small JS seams are added (`Console.setTitles`, the brand-row draft guard). The homepage keeps its inline `<style>` but swaps its tokens for the console's and adds the same theme boot script.

**Tech Stack:** Quart + Jinja2 templates, one stylesheet `website/static/css/console.css`, vanilla JS (no build), `icons.svg` sprite, i18n in `website/i18n/zh.json`; tests with unittest/pytest and `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-03-console-flat-layout-design.md`

## Global Constraints

- Token values in `console.css` `:root`, `:root[data-theme="dark"]` and the system-dark block do not change.
- Form element ids do not change; `test_module_scripts_find_every_id_they_read` must stay green.
- No build tools, CDN scripts or frameworks; icons only from `static/icons.svg`; copy only in `website/i18n/zh.json` (homepage keeps its inline `t()` bilingual copy).
- Content column 680px; editor pages `minmax(0, 680px) 320px` with a 32px gap, max 1032px, side by side only at viewport ≥ 1200px.
- Content padding: `40px 48px` at ≥ 1080px, `32px` at 860–1079px, `24px 16px` below 860px.
- Console font sizes only 12, 13, 14, 16, 22px; exceptions: selectors starting `.preview`, `.fake`, and `.palette-input`.
- Top bar hidden at ≥ 860px; below 860px it is 52px tall with the menu button and `#topbar-title`.
- Write files with LF line endings (`newline='\n'`); working files may be CRLF.
- Commit titles: `feat:` / `fix:` / `style:` / `docs:` + lowercase imperative summary, with a body. Commit on master. Never commit `rinbot/cogs/netease.py`. Do not push.
- Test commands: root `python -m pytest -q`; `cd website && python -m pytest -q tests`; `node --test website/tests/*.test.cjs`.

## Review Focus

1. Leaving the server page from the new brand row while a page has unsaved edits — expect the same draft guard as switching servers (owned by Task 1).
2. Very long server, user and module names in the brand row, switcher, server rows and module rows at 375px — expect single-line ellipsis, never horizontal page scroll (owned by Tasks 1, 4, 5, checked in Task 7).
3. A sticky preview taller than the viewport (welcome card with a large image on a 1366×768 laptop) — expect the preview to scroll inside itself instead of being cut off (owned by Task 2).
4. Night mode on the homepage before scripts run — expect no white flash, because the boot script runs before styles (owned by Task 6).
5. A page whose list holds a single block row (textarea, upload) or an empty state — expect hairlines above and below and no stray double border (checked in Task 7).

---

### Task 1: Shell — brand row, no desktop top bar, quiet status dots

**Files:**
- Modify: `website/templates/_console_base.html`, `website/templates/server.html`, `website/templates/dashboard.html`, `website/templates/settings.html`
- Modify: `website/static/js/console-core.js`, `website/static/css/console.css`, `website/static/icons.svg`, `website/i18n/zh.json`
- Test: `website/tests/test_dashboard_templates.py`, `website/tests/console_core.test.cjs`

**Interfaces:**
- Produces: `a.brand-row[href="/"]` in every console page; `#topbar-title` (span, `aria-hidden="true"`) inside `.topbar`; `Console.setTitles(name: string) -> void` that writes `#page-title` and `#topbar-title` text when present and sets `document.title` via `tr('title.page', …)`; `[data-bot-status]` lives inside `#pg-overview .hero`; i18n keys `nav.homepage` = "主页", `nav.homepage_label` = "回到主页"; sprite symbol `i-home`.
- Consumes: existing `leaveClick`, `DashboardUI.confirmLeave`.

- [ ] **Step 1: Write the failing template tests**

```python
def test_every_console_page_links_home_from_the_sidebar(self):
    for name in ['dashboard.html','server.html','settings.html']:
        html,_=self.render(name)
        side=html[html.index('id="sideNav"'):html.index('id="switcher"')]
        self.assertRegex(side,r'<a class="brand-row" href="/" aria-label="回到主页"',name)

def test_no_crumbs_and_titles_live_in_content(self):
    for name in ['dashboard.html','server.html','settings.html']:
        html,_=self.render(name)
        self.assertNotIn('id="crumbs"',html,name)
        topbar=html[html.index('<header class="topbar">'):html.index('</header>')]
        self.assertIn('id="topbar-title"',topbar,name)
        self.assertNotIn('<h1',topbar,name)
    html,_=self.render('server.html')
    content=html[html.index('<div class="content'):]
    self.assertIn('<h1 class="sr-only" id="page-title">',content)
    ov=html[html.index('id="pg-overview"'):html.index('</section>',html.index('id="pg-overview"'))]
    self.assertIn('data-bot-status',ov)

def test_topbar_only_shows_while_the_sidebar_is_a_drawer(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertRegex(re.search(r'\n\.topbar\s*\{([^}]*)\}',css).group(1),r'display:\s*none')
    narrow=css[css.index('@media (max-width: 859px)'):]
    self.assertRegex(narrow,r'\.topbar\s*\{[^}]*display:\s*flex')

def test_only_warning_dots_show_in_the_sidebar(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertRegex(css,r'\.nav-dot:not\(\.nav-dot--warn\)\s*\{\s*display:\s*none;?\s*\}')
```

Delete `test_topbar_has_a_plain_background_before_color_mix`'s dependency on the old selector only if the regex no longer matches: the `.topbar` block keeps `background: var(--bg);` before `color-mix(` (the test stays).

- [ ] **Step 2: Write the failing JS tests in `console_core.test.cjs`**

```js
test('setTitles writes the hidden heading, the mobile bar and the tab title', () => {
    const nodes = {'page-title': {textContent: ''}, 'topbar-title': {textContent: ''}};
    const {Console} = core({nodes});
    Console.setTitles('自动审核');
    assert.equal(nodes['page-title'].textContent, '自动审核');
    assert.equal(nodes['topbar-title'].textContent, '自动审核');
});
test('setTitles works on pages without the hidden heading', () => {
    const {Console} = core();
    assert.doesNotThrow(() => Console.setTitles('我的服务器'));
});
test('the brand row is guarded by the draft check', () => { /* same shape as 'switcher links are guarded by the draft check', with a link whose closest('.brand-row') matches and dirty: true → preventDefault called */ });
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py` and `node --test website/tests/console_core.test.cjs`
Expected: the four new template tests and three JS tests FAIL (missing brand row, crumbs present, no `setTitles`).

- [ ] **Step 4: Implement**

- `_console_base.html`: first child of `.sidebar` is `<a class="brand-row" href="/" aria-label="{{ tr('nav.homepage_label') }}"><img src="…/images/rin/bot-avatar-96.webp" alt="" width="24" height="24"><span class="brand-name">小凛 RinBot</span><span class="brand-home">{{ icon('home', 14) }}{{ tr('nav.homepage') }}</span></a>`. The topbar holds the menu button and `<span class="topbar-title" id="topbar-title" aria-hidden="true">{% block topbar_title %}{% endblock %}</span>`; remove the `topbar` and `topbar_end` blocks.
- `server.html`: drop the crumbs/topbar blocks; put `<h1 class="sr-only" id="page-title">` as the first element of `{% block content %}`; move the `bot-status` span into `.hero` after `.hero-text`.
- `dashboard.html`, `settings.html`: their titles move into page heads in Task 5; for now set `{% block topbar_title %}` to the page name and render the old title text in an `<h1 class="sr-only">` at the top of content so headings never disappear.
- `console-core.js`: add `setTitles(name)` and call it from `show()` instead of the crumb code; extend `leaveClick` to match `.brand-row` (same guard, no href rewrite); export `setTitles` on `Console`.
- `console.css`: `.brand-row` (flex, gap 10px, padding 6px 8px, radius 8px, hover `--hover`; `.brand-name` Fredoka 16px/600; `.brand-home` margin-left auto, 12px, `--muted`); `.topbar { display: none; … }` keeping `background: var(--bg);` before the `color-mix(` line; in `@media (max-width: 859px)` `.topbar { display: flex; min-height: 52px; padding: 8px 16px; }`; `.topbar-title` 14px/600 ellipsis; `.nav-dot:not(.nav-dot--warn) { display: none; }`; delete `.crumbs*`, `.page-title`, `.topbar-text`.
- `icons.svg`: add `i-home` (house outline, 24×24, stroke like the others).
- `zh.json`: add `nav.homepage`, `nav.homepage_label`; remove `nav.crumbs` if no longer used.

- [ ] **Step 5: Run all three suites**

Expected: all green. `test_every_tr_key_exists` and `test_icon_sprite_has_every_used_icon` pass.

- [ ] **Step 6: Commit**

```bash
git add website/templates website/static/js/console-core.js website/static/css/console.css website/static/icons.svg website/i18n/zh.json website/tests
git commit -m "feat: add a homepage row to the sidebar and drop the desktop top bar" -m "<body>"
```

### Task 2: Flat page skeleton — left edge, 680px column, flat lists, editor pages

**Files:**
- Modify: `website/static/css/console.css`, `website/templates/server.html`, `website/templates/_console_macros.html` (only if a class name in a macro changes)
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Produces: `.page` (max-width 680px, no auto margin); `.page--editor` (welcome, roles; max-width 1032px); `.editor` grid; `.list` flat; `.row` padding `14px 0`; `.master-hint` as a text line; content padding per Global Constraints; unsaved bar aligned to the column.
- Consumes: Task 1's shell (no top bar on desktop).

- [ ] **Step 1: Write the failing tests**

```python
def test_pages_share_one_left_edge(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    page=re.search(r'\n\.page\s*\{([^}]*)\}',css).group(1)
    self.assertIn('max-width: 680px',page); self.assertNotIn('auto',page)
    self.assertNotIn('.page--wide',css); self.assertNotIn('.content--page',css)
    self.assertIn('max-width: 1032px',re.search(r'\.page--editor\s*\{([^}]*)\}',css).group(1))
    self.assertIn('padding: 40px 48px',re.search(r'\n\.content\s*\{([^}]*)\}',css).group(1))

def test_editor_pages(self):
    html,_=self.render('server.html')
    self.assertEqual(sorted(re.findall(r'<section class="page page--editor" id="pg-([a-z]+)"',html)),['roles','welcome'])
    self.assertEqual(len(re.findall(r'<section class="page[" ]',html)),12)
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertIn('minmax(0, 680px) 320px',re.search(r'\n\.editor\s*\{([^}]*)\}',css).group(1))
    self.assertRegex(css[css.index('@media (max-width: 1199px)'):],r'\.editor\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)')

def test_sticky_preview_scrolls_inside_itself(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    body=re.search(r'\n\.editor-preview\s*\{([^}]*)\}',css).group(1)
    for part in ['position: sticky','max-height: calc(100dvh - 48px)','overflow-y: auto']:self.assertIn(part,body)

def test_lists_are_flat(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    lst=re.search(r'\n\.list\s*\{([^}]*)\}',css).group(1)
    for gone in ['background','border-radius','box-shadow']:self.assertNotIn(gone,lst)
    self.assertIn('border-block: 1px solid var(--line)',lst)
    self.assertIn('padding: 14px 0',re.search(r'\n\.row\s*\{([^}]*)\}',css).group(1))
    hint=re.search(r'\n\.master-hint\s*\{([^}]*)\}',css).group(1)
    self.assertNotIn('background',hint); self.assertIn('color: var(--warn)',hint)
```

Replace `test_wide_pages` with `test_editor_pages`. Replace the `test_server_grid_cards_are_at_least_260px` body only in Task 5.

- [ ] **Step 2: Run to see them fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k "left_edge or editor or sticky or flat"`
Expected: 4 FAIL.

- [ ] **Step 3: Implement in `console.css` and `server.html`**

- `.content { padding: 40px 48px 140px; }`, at `max-width: 1079px` `padding: 32px 32px 140px`, at `max-width: 859px` `padding: 24px 16px 140px`.
- `.page { display: none; max-width: 680px; }`; `.page--editor { max-width: 1032px; }`; overview loses `page--wide` (plain `page`); welcome and roles use `page page--editor`.
- `.editor { display: grid; grid-template-columns: minmax(0, 680px) 320px; gap: 32px; align-items: start; }`; the preview column element (currently the element after `.editor-form` inside `.editor`) gets class `editor-preview` with `position: sticky; top: 24px; max-height: calc(100dvh - 48px); overflow-y: auto;`; `@media (max-width: 1199px) { .editor { grid-template-columns: minmax(0, 1fr); } .editor-preview { position: static; max-height: none; } }`.
- Page head: `.page-head` margin-bottom 24px; `.page-head h2` stays 22px/600; `.master-hint { margin: -16px 0 20px; color: var(--warn); font-size: 13px; }`.
- Tabs: `.tabs { gap: 24px; }`, `.tab { padding: 8px 0; }`.
- Sections: `.section { margin: 0 0 32px; }`, `.section-title` 16px/600, `.section-hint` 13px `--muted` `margin: 2px 0 0`, `.section-title + .list, .section-hint + .list { margin-top: 10px; }`.
- `.list { border-block: 1px solid var(--line); }` (nothing else); `.row { …; padding: 14px 0; border-top: 1px solid var(--line); }` with `.row:first-child { border-top: 0; }` kept; `.row-title` weight 500.
- Flatten the same way: `.lb-list`, `.lb-row` (padding `10px 0`), `.item-list` inside `.fold`, `.fold > summary` (no border box: a 16px/600 title row with the chevron, padding `8px 0`), and every other card-like block on module pages found with `grep -n "background: var(--panel)" static/css/console.css` except `.switcher-btn`, `.switcher-pop`, `.palette*`, `.unsaved-bar`, `.toast`, `.notice`, `.attention`, the preview, `.btn*` and form fields.
- Fields: every `.input`, `.select`, `.search-select`, `.num`, `textarea` background uses `var(--field)`.
- Unsaved bar: `left: calc(var(--side-w) + 48px); width: min(680px, calc(100vw - var(--side-w) - 96px)); transform-origin` unchanged; at ≤1079px use 32px; at ≤859px `left: 16px; right: 16px; width: auto`.
- Delete dead `.fold-hint`, `.fold-state`, `.page--wide`, `.content--page`.

- [ ] **Step 4: Run all three suites**

Expected: green (update `dashboard.html` / `settings.html` `content_class` usage so nothing references `content--page`).

- [ ] **Step 5: Commit**

`style: lay console pages out as one left-aligned flat column`

### Task 3: Five-step type scale

**Files:**
- Modify: `website/static/css/console.css`
- Test: `website/tests/test_console_contrast.py`

- [ ] **Step 1: Write the failing test**

```python
ALLOWED_SIZES={12,13,14,16,22}
EXEMPT=('.preview','.fake','.palette-input')
def test_console_uses_five_font_sizes(self):
    bad=[]
    for selector,body in re.findall(r'([^{}]+)\{([^{}]*)\}',self.css):
        sel=selector.strip().split('\n')[-1].strip()
        if sel.startswith(EXEMPT):continue
        for size in re.findall(r'font(?:-size)?:[^;]*?(\d+(?:\.\d+)?)px',body):
            if float(size) not in ALLOWED_SIZES:bad.append((sel,size))
    self.assertEqual(bad,[])
```

- [ ] **Step 2: Run it**

Run: `cd website && python -m pytest -q tests/test_console_contrast.py -k five`
Expected: FAIL listing the 10/12.5/15/17/18/19/20/24px uses.

- [ ] **Step 3: Map sizes**: 10 → 12, 12.5 → 13, 15 → 14 (or 16 where it is a heading such as `.brand-name`), 17/18/19/20 → 16, 24 → 22. Icons sized in px via `width/height` are not font sizes and stay.

- [ ] **Step 4: Run all three suites** — green.

- [ ] **Step 5: Commit** `style: reduce the console to five font sizes`

### Task 4: Overview as a flat module list

**Files:**
- Modify: `website/templates/server.html` (overview section), `website/static/js/modules/overview.js`, `website/static/css/console.css`
- Test: `website/tests/test_dashboard_templates.py`, `website/tests/overview.test.cjs`

**Interfaces:**
- Produces: `.mod-row[data-row]` ×11, each inside a `.list` under its group's `.section-title`; `.mod-row-link[data-mod]` covers icon + text; `[data-summary]` gets `title` equal to its text; `.hero` with an 88px image, `#ov-headline` (22px), `#ov-facts`, and `[data-bot-status]`.
- Consumes: overview.js `render`, `failed`, `retry`, `attention` unchanged in behaviour.

- [ ] **Step 1: Write the failing tests**

```python
def test_overview_cards(self):  # rename to test_overview_module_rows
    html,_=self.render('server.html')
    start=html.index('id="pg-overview"');ov=html[start:html.index('</section>',start)]
    self.assertEqual(ov.count('class="mod-row"'),11)
    self.assertEqual(len(re.findall(r'<div class="list">\s*<div class="mod-row"',ov)),3)
    self.assertNotIn('mod-card',ov); self.assertNotIn('mod-grid',ov)
    # keep the existing toggle / id / aria-busy assertions
```

In `overview.test.cjs`, extend the render test that checks summaries: after render, `summaryNode.title === summaryNode.textContent`.

CSS check: `self.assertNotIn('.mod-card',css)`.

- [ ] **Step 2: Run to see them fail** — the renamed template test and the overview JS assertion FAIL.

- [ ] **Step 3: Implement**
- Markup per module: `<div class="mod-row" data-row="{{ slug }}"><a class="mod-row-link" href="#{{ slug }}" data-mod="{{ slug }}"><span class="mod-icon">…</span><span class="mod-text"><span class="mod-name">…</span><span class="mod-summary" data-summary data-blurb="…" title="…">…</span><span class="sr-only" data-state></span></span></a>{toggle if in toggle_slugs}<span class="mod-go">{{ icon('chevron-right') }}</span></div>` — every row gets the chevron; groups render `<h3 class="section-title">` + `<div class="list">`. Wrap each group in `<div class="section">`.
- Hero: no border/background; `img` 88×88 `object-fit: contain`; `#ov-headline` drops the `display` class; `.bot-status` sits at the right (`margin-left: auto`).
- `overview.js` render: set `node.title = node.textContent` after writing the summary.
- CSS: `.mod-row` flex, gap 14px, padding `12px 0`, border-top like `.row`; `.mod-row-link` flex 1, gap 14px; `.mod-summary` single line ellipsis; `.mod-row.is-on .mod-icon` keeps the accent-soft tile; delete `.mod-grid`, `.mod-card*`.

- [ ] **Step 4: Run all three suites** — green.

- [ ] **Step 5: Commit** `feat: list overview modules as flat rows`

### Task 5: Server list and settings page heads

**Files:**
- Modify: `website/templates/dashboard.html`, `website/templates/settings.html`, `website/static/css/console.css`, `website/static/js/console-core.js` (only if the server search selectors change), `website/i18n/zh.json`
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Produces: `dashboard.html` page head `<div class="page-head"><div class="page-head-text"><h1>{{ tr('nav.servers') }}</h1></div><a class="btn btn--primary" …invite…></div>`; server rows `.server-row` (joined: `<a class="server-row" href="/dashboard/server/{id}" data-guild-name data-guild-id>`; not joined: `<div class="server-row is-unjoined" data-guild-name data-guild-id>` with an invite button) inside `.list`; settings top page head `<h1>{{ tr('nav.settings') }}</h1><p>{{ tr('settings.subtitle') }}</p>`, panel heads become `<div class="panel-head"><h2 class="panel-title" id="settings-…-title" tabindex="-1">…</h2>[<p>intro</p>]</div>`.
- Consumes: `serverSearch()` filters `[data-guild-name]`; `#server-no-results`, `[data-server-group]`, `[data-count]` unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_server_list_and_settings_have_visible_page_heads(self):
    html,_=self.render('dashboard.html')
    self.assertRegex(html,r'<div class="page-head">\s*<div class="page-head-text">\s*<h1>')
    self.assertEqual(len(re.findall(r'class="server-row[ "]',html)),2)
    self.assertNotIn('server-card',html); self.assertNotIn('server-grid',html)
    html,_=self.render('settings.html')
    self.assertRegex(html,r'<h1>全局设置</h1>')
    self.assertEqual(len(re.findall(r'<h2 class="panel-title" id="settings-[a-z]+-title" tabindex="-1">',html)),3)

def test_server_rows_truncate_long_names(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    body=re.search(r'\.server-name\s*\{([^}]*)\}',css).group(1)
    for part in ['text-overflow: ellipsis','white-space: nowrap','min-width: 0']:self.assertIn(part,body)
```

Delete `test_server_grid_cards_are_at_least_260px`. Keep `test_only_server_cards_carry_data_guild_name` but update its comment and allow `{'a','div'}`, the two row tags that carry it; assert the `body` never does.

- [ ] **Step 2: Run to see them fail.**

- [ ] **Step 3: Implement** markup above; CSS `.server-row` (flex, gap 12px, padding `12px 0`, border-top like `.row`, joined rows hover `--hover` on the name only), `.server-icon` 40px, `.server-name` ellipsis; remove the sr-only h1 fallback Task 1 added on these two pages; `.panel-head` margin `0 0 16px`, `.panel-title` 16px/600 (`.panel-head p` 13px muted); delete `.server-grid`, `.server-card*`.

- [ ] **Step 4: Run all three suites** — green.

- [ ] **Step 5: Commit** `style: give the server list and settings visible page heads and flat rows`

### Task 6: Homepage on the console palette with night mode

**Files:**
- Modify: `website/templates/index.html`
- Create: `website/tests/test_homepage_theme.py`

**Interfaces:**
- Consumes: the console token values (read from `console.css` in the test).
- Produces: homepage `:root` with the 11 shared tokens, `:root[data-theme="dark"]` and `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }` with the same dark values and the Discord dark set, the `rin-theme` boot script before `<style>`.

- [ ] **Step 1: Write the failing tests**

```python
SHARED=['bg','panel','side','line','text','muted','accent','accent-hover','on-accent','accent-soft','accent-text']
class HomepageThemeTests(unittest.TestCase):
    def setUp(self): # parse console.css and index.html with the block()/declarations() helpers from test_console_contrast
    def test_homepage_shares_console_tokens_in_both_palettes(self):
        for name in SHARED:
            self.assertEqual(self.home_light[name].strip().upper(),self.console_light[name].strip().upper(),name)
            self.assertEqual(self.home_dark[name].strip().upper(),self.console_dark[name].strip().upper(),name)
    def test_system_dark_matches_manual_dark(self):
        self.assertEqual(self.home_system_dark,self.home_dark)
    def test_theme_boots_before_styles(self):
        html=self.html
        self.assertLess(html.index("localStorage.getItem('rin-theme')"),html.index('<style>'))
    def test_no_old_palette_left(self):
        for old in ['#B0335A','#DCC3CD','#E7D4DC','#D9C1CB','#DFCAD3','#3A2433','--rin:','rgba(201, 63, 105']:
            self.assertNotIn(old,self.html)
    def test_discord_mock_text_meets_aa_in_both_palettes(self):
        for palette in [self.home_light,self.home_dark]:
            self.assertGreaterEqual(ratio(palette['dc-text'],palette['dc-bg']),4.5)
            self.assertGreaterEqual(ratio(palette['dc-muted'],palette['dc-bg']),4.5)
            self.assertGreaterEqual(ratio(palette['muted'],palette['side']),4.5)
```

- [ ] **Step 2: Run** `cd website && python -m pytest -q tests/test_homepage_theme.py` — FAIL.

- [ ] **Step 3: Implement** the token swap (`--rin` → `--accent`, `--on-rin` → `--on-accent`, `--chip-*` → `--accent-soft`/`--accent-text`, `--panel-line` → `--line`), the side rail/channel colours (`--hover`, `--side`, `--cur` + `--shadow-sm`, separators `--line`), the nav background fallback, the Discord dark set from the spec, accent-based glows (`color-mix(in srgb, var(--accent) 35%, transparent)` with a plain `rgba` fallback line before it), halved glow and grain opacity in dark, and the console teaser `.dash-mock` restyled to the flat look (light grey side `--side`, current item `--cur`, rows separated by `--line`, toggles `--accent`). Keep Fredoka, stickers, motion and all copy.

- [ ] **Step 4: Run all three suites** — green (including `test_homepage_tab_title_stays_short_in_both_languages`).

- [ ] **Step 5: Commit** `style: move the homepage onto the console palette with night mode`

### Task 7: Visual pass, cache bump

**Files:**
- Modify: whatever the pass finds; asset version `20261103a` → `20261103b` in every template that references it.

- [ ] **Step 1:** In the local preview (`dashboard-preview`, port 5078, restart after zh.json changes), run the overflow audit over the 12 pages and every tab at 1440, 1080 and 375 in both palettes: `document.documentElement.scrollWidth > innerWidth` must be false, and no element's right edge passes the viewport.
- [ ] **Step 2:** Screenshot overview, automod, welcome, roles, server list and settings at 1440 in both palettes; check the left edge is the same on every page, flat lists show single hairlines (Review Focus 5), long names ellipsize (Review Focus 2) and the sticky preview scrolls inside itself (Review Focus 3).
- [ ] **Step 3:** Homepage at 1536, 800 and 375 in both palettes (set `localStorage['rin-theme']`), including a reload in dark to confirm no flash.
- [ ] **Step 4:** Fix what the pass finds, each with a test where the defect is testable; bump the asset version; run all three suites.
- [ ] **Step 5: Commit** `fix: polish the flat console after visual review`
