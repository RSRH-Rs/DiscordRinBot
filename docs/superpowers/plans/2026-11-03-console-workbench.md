# 控制台改版二（工作台）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把控制台换成"一条侧栏 + 服务器切换器"的工作台布局，配色换成瓷白樱粉（白天）和夜幕（夜间），概览改成模块卡片，欢迎和自动审核两页改用标签页，并加上 Ctrl K 搜索设置。

**Architecture:** 后端和各模块脚本的数据读写都不动。改动集中在四处：一是 `console.css` 的 token 和组件样式；二是 `_console_base.html` 的外壳；三是 `server.html` 的页面结构（元素 id 不变）；四是几个前端脚本，包括 `console-core.js`、`dashboard-extras.js`、`overview.js`，以及新增的 `theme.js`、`server-switcher.js`、`command-palette.js`。

**Tech Stack:** Quart + Jinja2、原生 JS（无构建）、pytest、`node --test`。

**Spec:** `docs/superpowers/specs/2026-11-03-console-workbench-design.md`（每个任务都要对照它；本计划只写决定，不重复 spec 的细节）。外观参照 `docs/superpowers/specs/assets/2026-11-03-console-workbench-demo.html`。

## Global Constraints

- 颜色只用 spec §4.1 表里的值；两套配色的文字和底色组合都 ≥ 4.5:1，`--field-line` 和 `--field`、`--panel`、`--bg` 之间都 ≥ 3:1。
- 正文字体 `"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif`，14px，行高 1.6；Fredoka 600 只用在概览值班卡片标题（24px）。
- 字号：页面标题 22px/600，卡片标题 15px/600，设置项标题 14px/600，说明 12.5px。
- 不加载 CDN 脚本，图标只用 `website/static/icons.svg`；模板里不写 `style="`；JS 只在弹出层定位时写 inline style。
- 所有界面文案经 `tr('key')`，字典只有 `website/i18n/zh.json`。
- 尺寸：侧栏 252px；顶栏 56px；抽屉断点 `max-width: 859px`；预览移到表单上方 `max-width: 1079px`；内容区宽度为 `.page` 最宽 800px，`.page--wide`（概览、欢迎、领取身份组）最宽 1120px。
- 动效只有四种：保存条滑入、保存条抖动、开关切换、搜索跳转后的高亮；`prefers-reduced-motion` 时全部关闭（高亮改成不带动画的底色）。
- 现有表单控件的元素 id 一律不改；后端接口不改。
- 静态资源版本号统一为 `?v=20261103a`。
- 直接在 master 上提交，标题用 `feat:` / `fix:` / `style:` / `test:` / `docs:` 加小写祈使句；每个任务结束时下面三套测试全绿；推送前先问用户。
- 测试命令（在仓库根目录运行）：`python -m pytest -q`；`cd website && python -m pytest -q tests`；`node --test website/tests/*.test.cjs`。

## Review Focus

- **服务器很多、名字很长**：切换器弹出层不能超出屏幕，要在内部滚动，名字单行截断。→ Task 3 的 CSS 断言。
- **中文输入法正在输入时按 Ctrl K**：`isComposing` 为真时不打开搜索；在搜索框里打中文时，方向键和回车不能误跳转。→ Task 7 的测试。
- **深链接写错**：`#welcome/nope` 显示第一个标签，`#nope/x` 回到概览，两种情况都不报错。→ Task 4 的测试。
- **撤销或保存之后的标签小圆点**：修改撤销或保存成功后，所有标签上的小圆点都要消失。→ Task 4 的测试。
- **浏览器禁用存储**：`localStorage` 抛错时，外观切换按钮仍然可用，只是不记住选择，页面跟随系统。→ Task 2 的测试。

---

### Task 1: 配色 token 与夜间配色

**Files:**
- Modify: `website/static/css/console.css`（token 区和所有引用 token 的地方）
- Modify: `website/templates/_console_base.html`、`login_gate.html`、`error.html`（版本号）
- Test: `website/tests/test_console_contrast.py`、`website/tests/test_dashboard_templates.py`

**Interfaces:**
- Produces：spec §4.1 的 token 名称（`--bg --panel --side --line --field --field-line --text --muted --accent --accent-hover --on-accent --accent-soft --accent-text --ok --ok-soft --warn --warn-soft --bad --bad-soft --cur --hover --bar --bar-text --shadow-sm --shadow-pop`），后面所有任务都只用这些名字。
- 改名对照：`--rin`→`--accent`，`--rin-hover`→`--accent-hover`，`--chip-bg`→`--accent-soft`，`--chip-text`→`--accent-text`，`--ok-bg`→`--ok-soft`，`--warn-bg`→`--warn-soft`，`--bad-bg`→`--bad-soft`，`--focus`→`--accent`，`--chan`/`--rail`→`--side`，`--active`→`--hover`（悬停）或 `--cur`（当前项），`--side-text`→`--muted`，`--bar-reset`→`--bar-text`。

- [ ] **Step 1: 改写对比度测试**

`setUp` 读三个块：第一个 `:root {…}`（白天）、`:root[data-theme="dark"] {…}`（夜间），以及 `@media (prefers-color-scheme: dark)` 里的 `:root:not([data-theme="light"]) {…}`。

```python
PAIRS = [('text','bg'),('text','panel'),('text','side'),('text','cur'),('muted','bg'),('muted','panel'),('muted','side'),
         ('on-accent','accent'),('on-accent','accent-hover'),('accent-text','accent-soft'),('accent-text','panel'),
         ('ok','ok-soft'),('ok','panel'),('warn','warn-soft'),('bad','bad-soft'),('bar-text','bar'),('#FFFFFF','#4752C4')]
NON_TEXT = [('field-line','field'),('field-line','panel'),('field-line','bg')]

def test_both_palettes_meet_aa(self):           # 每组 ≥ 4.5，light 和 dark 各测一遍
def test_field_borders_meet_3_to_1(self):        # NON_TEXT 每组 ≥ 3.0，两套都测
def test_system_dark_matches_manual_dark(self):  # 媒体查询块和 data-theme 块的声明完全相同
def test_dark_defines_every_light_colour(self):  # 白天块里每个取值为 #hex 的 token，夜间块里也有
def test_every_var_used_is_defined(self):        # 文件里所有 var(--x) 的 x 都在白天块里定义
```

`test_reduced_motion_overrides_every_animated_selector` 和 `test_no_important` 保留不动。

- [ ] **Step 2: 运行测试，确认失败**

运行：`cd website && python -m pytest -q tests/test_console_contrast.py`
预期：FAIL，提示找不到 `:root[data-theme="dark"]` 块，以及 `accent` 等 token 不存在。

- [ ] **Step 3: 改写 token 区**

白天值写在 `:root`（`color-scheme: light`），夜间值写在 `:root[data-theme="dark"]` 和 `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} }` 两处，内容一样（`color-scheme: dark`）。按上面的对照表替换全文件的 token 引用。白天的 `--shadow-sm: 0 1px 2px rgba(24,24,27,.06), 0 1px 1px rgba(24,24,27,.04)`；夜间的 `--shadow-sm: none`；`--shadow-pop` 白天是 `0 12px 32px rgba(24,24,27,.16), 0 2px 6px rgba(24,24,27,.06)`，夜间是 `0 16px 40px rgba(0,0,0,.5)`。`:focus-visible` 统一用 `2px solid var(--accent)`，输入框聚焦时加 `box-shadow: 0 0 0 3px var(--accent-soft)`。字号按 Global Constraints 调整：`.page-title` 和 `.page-head h2` 22px/600，`.section-title` 和卡片标题 15px/600，`.row-title` 14px/600，`.row-hint` 12.5px。

- [ ] **Step 4: 版本号改成 `v=20261103a`**

三个模板里的 css 和 js 链接，以及 `test_dashboard_templates.py` 里 `v=20261102` 的断言，都改成 `v=20261103`。

- [ ] **Step 5: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add website/static/css/console.css website/templates website/tests
git commit -m "style: switch console to porcelain light and night palettes"
```

### Task 2: 外观切换

**Files:**
- Create: `website/static/js/theme.js`
- Modify: `website/templates/_console_base.html`（`<head>` 初始化脚本、用户行按钮）、`login_gate.html`、`error.html`（只加初始化脚本）、`website/static/icons.svg`（`i-sun`、`i-moon`、`i-monitor`）、`website/i18n/zh.json`（`theme.label`、`theme.light`、`theme.system`、`theme.dark`）
- Test: `website/tests/theme.test.cjs`、`website/tests/test_dashboard_templates.py`

**Interfaces:**
- Produces：`window.Theme = {get(): '' | 'light' | 'dark', set(value: '' | 'light' | 'dark'): void}`，存储键为 `rin-theme`；按钮是 `button[data-theme-set="light" | "" | "dark"]`，用 `aria-pressed` 标出当前选择。
- 初始化脚本放在 `<head>` 的 stylesheet 之前，原样写成：
  `<script>try{var t=localStorage.getItem('rin-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}</script>`

- [ ] **Step 1: 写失败的测试**

`theme.test.cjs` 用 vm 加载 `theme.js`，桩出 `document.documentElement.dataset`、三个按钮和 `localStorage`：

```js
test('set("dark") writes the attribute, storage and pressed state', ...)       // dataset.theme==='dark'；存储里是 'dark'；dark 按钮 aria-pressed="true"，另两个是 "false"
test('set("") follows the system and clears storage', ...)                    // dataset 里没有 theme；存储里是 ''
test('blocked storage never breaks switching', ...)                           // getItem/setItem 都抛错；set('dark') 照样生效；get() 返回 ''
test('clicking a button switches theme', ...)                                 // 触发 light 按钮的 click → dataset.theme==='light'
```

`test_dashboard_templates.py`：

```python
def test_every_page_boots_theme_before_styles(self):  # 五个页面里 "localStorage.getItem('rin-theme')" 都出现在 console.css 链接之前
def test_console_pages_have_three_theme_buttons(self): # dashboard/server/settings 页里 data-theme-set="light"、""、"dark" 各一个
```

- [ ] **Step 2: 运行，确认失败**

运行：`node --test website/tests/theme.test.cjs`，以及 `cd website && python -m pytest -q tests/test_dashboard_templates.py -k theme`
预期：FAIL（`theme.js` 不存在，模板里没有按钮）。

- [ ] **Step 3: 实现**

`theme.js` 在 DOMContentLoaded 时给按钮绑定 click，并按 `get()` 的结果设好 `aria-pressed`；读写存储都包在 try/catch 里。三个按钮放进用户行（`.user-card` 改名 `.user-row`），按钮在名字和退出按钮之间，`role="group"` 加 `aria-label="{{ tr('theme.label') }}"`，每个按钮的 `title` 和 `aria-label` 用对应的 `tr`。

- [ ] **Step 4: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
git commit -am "feat: add light, system and night appearance switch"   # 新文件先 git add
```

### Task 3: 单侧栏与服务器切换器

**Files:**
- Create: `website/static/js/server-switcher.js`
- Modify: `website/templates/_console_base.html`（去掉 `.rail`；加切换器；`<body data-guild-name>`；面包屑）、`_console_macros.html`（加 `invite_url(guild_id=None)` 宏）、`dashboard.html`（邀请链接改用宏）、`server.html`（每个 `.page` 加 `data-group`）、`static/js/console-core.js`、`static/js/message-preview.js`、`static/js/modules/overview.js`（`loadInfo` 写入 `#switcher-sub`）、`static/css/console.css`（删掉 `.rail*`、`.nav-head`，加切换器和顶栏样式）、`icons.svg`（`i-chevrons-up-down`）、`zh.json`（`switcher.*`）
- Test: `website/tests/switcher.test.cjs`、`website/tests/console_core.test.cjs`、`website/tests/test_dashboard_templates.py`

**Interfaces:**
- Consumes：`DashboardUI.confirmLeave(roots)`、`DashboardExtras.matches(text, query)`。
- Produces：
  - 标记：`#switcher-btn`（`aria-expanded`）、`#switcher-pop`（`hidden`）、`#switcher-search`、`[data-switcher-item][data-name]`、`#switcher-empty`。
  - `window.ServerSwitcher = {open(): void, close(): void, filter(query: string): number}`，`filter` 返回可见条目数。Esc、点外面、点条目都会关闭。
  - `Console.leaveClick(event)` 取代 `railClick`，作用范围是 `#switcher-pop a`。有未保存修改时调用 `preventDefault`；链接带 `data-guild` 且当前在服务器页时，链接末尾追加 `#` 加 `router.current()`。
  - `document.body.dataset.guildName`：服务器页是服务器名，其他页是空字符串。`console-core.js` 里的 `document.title` 和 `message-preview.js` 里的两处 `.nav-head` 都改用它。
  - 面包屑：`#crumbs` 内依次是 `<a href="#overview" data-mod="overview">`、`#crumb-group`、`#crumb-current`；`show()` 从 `page.dataset.group` 填分组，概览页时隐藏后两段。
  - `invite_url(guild_id)`：现有邀请链接，有 `guild_id` 时加上 `&guild_id=<id>&disable_guild_select=true`。

- [ ] **Step 1: 写失败的测试**

```python
def test_shell_has_switcher_and_no_rail(self):         # 三个控制台页都有 id switcher-btn / switcher-pop；HTML 里没有 'rail-item'、'nav-head'
def test_switcher_lists_joined_before_invites(self):   # server.html：data-name="小凛 &lt;img src=x&gt;" 的条目出现在 id=456（未加入）之前；未加入的链接 permissions=1374694796438 且带 guild_id=456
def test_switcher_popover_scrolls_inside_viewport(self): # console.css 里 .switcher-pop 的规则含 max-height 和 overflow-y: auto；.switcher-name 含 text-overflow: ellipsis
def test_pages_carry_group_and_guild_name(self):        # server.html 每个 .page[data-slug] 都有 data-group；<body data-guild-name="小凛 &lt;img src=x&gt;">
```

`switcher.test.cjs`：

```js
test('filter hides non-matching servers and reports the count', ...)  // 三个条目，filter('gam') → 1；#switcher-empty 在 0 条时显示
test('Escape and outside click close the popover', ...)
```

`console_core.test.cjs`：把 `home rail item and breadcrumb are guarded too` 改成 `switcher links are guarded by the draft check`，断言对 `#switcher-pop a` 调用 `preventDefault`，且 `confirmLeave` 被调用一次。删掉旧的 rail 测试。

- [ ] **Step 2: 运行，确认失败**

预期：FAIL（还没有切换器，`leaveClick` 未定义）。

- [ ] **Step 3: 实现**

侧栏结构见 spec §5。切换器按钮显示服务器图标（没有图标时显示名字首字）、名字和 `{{ tr('switcher.members', n=...) }}`；成员数在模板里没有，就先显示 `tr('switcher.open')`，页面加载后由 `overview.js` 的 `loadInfo` 写入 `#switcher-sub`。在 `/dashboard` 和 `/dashboard/settings` 上，按钮显示 `tr('switcher.choose')`。弹出层分组和末尾两行见 spec §5。`.switcher-pop` 用 `max-height: min(420px, calc(100dvh - 120px)); overflow-y: auto`。`DashboardUI` 里抽屉用到的 `.sidebar` 和 `#sideNav` 继续保留。

- [ ] **Step 4: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
git commit -m "feat: replace server rail with a sidebar server switcher"
```

### Task 4: 标签页与 `#slug/tab` 路由

**Files:**
- Modify: `website/static/js/dashboard-extras.js`（`createHashRouter`）、`static/js/console-core.js`（`selectTab`、标签点击、小圆点）、`static/js/dashboard-ui.js`（`changedWithin`）、`templates/_console_macros.html`（`tabs`、`tab_panel`）、`static/css/console.css`（`.tabs`、`.tab`、`.tab-dot`、`.tab-panel[hidden]`）
- Test: `website/tests/dashboard_extras.test.cjs`、`console_core.test.cjs`、`dashboard_ui.test.cjs`

**Interfaces:**
- Produces：
  - `createHashRouter({ids, fallback, show, canLeave, showTab})` 返回 `{navigate(id, {tab=null, fromHistory=false, initial=false}) → boolean, current() → string, currentTab() → string|null}`。地址栏是 `#id` 或 `#id/tab`。`id` 不变、只换 `tab` 时不调用 `canLeave`，直接调用 `showTab(id, tab)`。`showTab` 返回实际显示的标签 id（没有标签的页面返回 `null`），路由用 `replaceState` 把地址栏改成和实际一致。
  - `Console.selectTab(slug: string, tab: string|null) → string|null`：在 `#pg-<slug>` 里切换 `[data-panel]` 的 `hidden` 和 `[data-tab]` 的 `aria-selected`、`tabindex`；未知的 `tab` 显示第一个标签。
  - `Console.go(slug, tab = null)`，转给 `router.navigate(slug, {tab})`。
  - `DashboardUI.changedWithin(id, container) → boolean`：只比较 `container` 里的字段和标签列表，比较对象是上次 `clean` 时记下的值。
  - 宏：`tabs(slug, items)`，`items` 是 `[(tab_id, label)]`，生成 `<div class="tabs" role="tablist">`，每项是 `<a class="tab" role="tab" id="tab-<slug>-<id>" href="#<slug>/<id>" data-tab="<id>" aria-controls="panel-<slug>-<id>">label<span class="tab-dot" hidden></span></a>`。`tab_panel(slug, tab_id)` 是 call 宏，生成 `<div class="tab-panel" role="tabpanel" id="panel-<slug>-<id>" data-panel="<id>" aria-labelledby="tab-<slug>-<id>">`。
  - 小圆点：收到 `dashboard:drafts-changed` 时，对当前页每个标签设置 `.tab-dot.hidden = !DashboardUI.changedWithin('pg-'+slug, panel)`。
  - 键盘：在标签栏里按左右方向键，焦点移到相邻标签。

- [ ] **Step 1: 写失败的测试**

`dashboard_extras.test.cjs`：

```js
test('#welcome/farewell opens the page on that tab', ...)            // show 收到 'welcome'；showTab 收到 ('welcome','farewell')；currentTab()==='farewell'
test('switching tabs never asks canLeave', ...)                      // canLeave 永远返回 false；navigate('welcome',{tab:'card'}) → true；最后一次写入是 ['pushState','#welcome/card']
test('leaving the page still asks canLeave', ...)                    // navigate('overview') → false；hash 仍是 '#welcome/card'
test('unknown tab and unknown page fall back without errors', ...)   // showTab 对 'nope' 返回 'message' → 地址栏被改成 '#welcome/message'；'#nope/x' → current()==='overview'
```

`dashboard_ui.test.cjs`：

```js
test('changedWithin only reports fields inside the container', ...)  // 两个面板各一个字段；改面板 A 的字段 → A 为 true、B 为 false
test('reset and clean clear every tab', ...)                         // 改字段后先 reset → false；再改、再 clean → false
```

`console_core.test.cjs`：

```js
test('selectTab shows one panel and marks its tab', ...)             // 三个面板；selectTab('welcome','card') → 只有 card 的 hidden=false，tab-card 的 aria-selected="true"；返回 'card'
```

- [ ] **Step 2: 运行，确认失败**

运行：`node --test website/tests/*.test.cjs`
预期：上面新增的用例 FAIL，原有用例仍然 PASS。

- [ ] **Step 3: 实现**

按上面的接口实现；`show()` 末尾调用 `selectTab(slug, router.currentTab())`。

- [ ] **Step 4: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
git commit -m "feat: add page tabs with #page/tab deep links"
```

### Task 5: 模块页结构：页头总开关、依赖提示、两个标签页、页面宽度

**Files:**
- Modify: `website/templates/_console_macros.html`（`page_head` 宏）、`templates/server.html`、`static/js/console-core.js`（`dependencies` 顺带更新提示）、`static/js/modules/welcome.js`（删掉更新 `[data-optional-status]` 的代码）、`static/css/console.css`（`.page-head`、`.master-hint`、`.page--wide`、卡片化的 `.list`）、`zh.json`（`common.master_hint`、`welcome.tab.*`、`automod.tab.*`）
- Test: `website/tests/test_dashboard_templates.py`、`console_core.test.cjs`，以及受影响的 `welcome_image_ui.test.cjs`

**Interfaces:**
- Consumes：Task 4 的 `tabs` 和 `tab_panel` 宏。
- Produces：
  - `page_head(title, intro, master=None)`：有 `master` 时右边放开关 `<label class="tog tog--head"><input type="checkbox" role="switch" id="<master>">…<span class="tog-on">{{ tr('common.enabled') }}</span><span class="tog-off">{{ tr('common.disabled') }}</span></label>`，下面跟 `<p class="master-hint" data-master-hint="<master>" hidden>{{ tr('common.master_hint') }}</p>`，提示文字是"先打开右上角的开关"。
  - `dependencies()` 在改变 `aria-disabled` 的同时，设置 `[data-master-hint="<id>"].hidden = source.checked`。
  - 四个总开关 `w-enabled`、`am-enabled`、`bl-enabled`、`sl-enabled` 从表单行移进 `page_head`；依赖它们的行保持 `data-depends-on` 不变。
  - 欢迎页的标签：`message` 欢迎消息（`w-ch`、`w-msg`）、`appearance` 图卡与外观（`w-title`、`w-thumb`、欢迎图片上传、`w-image`、`w-card`）、`farewell` 道别消息（`w-fch`、`w-fmsg`、道别图片上传）、`autoroles` 自动身份组（原折叠块里的全部内容）。预览留在 `.editor` 右栏，四个标签都能看到。
  - 自动审核的标签：`rules` 规则（`am-log`、反刷屏、大写、重复），`words` 违禁词，`links` 链接白名单。
  - `.page--wide` 加在 `pg-overview`、`pg-welcome`、`pg-roles` 上。

- [ ] **Step 1: 先加一个守护测试（应当直接通过）**

```python
def test_module_scripts_find_every_id_they_read(self):
    # 用正则从 static/js/modules/*.js 和 message-preview.js 里收集 el('x') / getElementById('x') 的 x，
    # 每个都必须在 server.html 渲染结果的 id 里；运行时由脚本自己创建的 id 写进测试里的 DYNAMIC 集合（第一次运行时把查到的结果列出来）。
```

运行后应当 PASS，这条测试用来锁住改版前的状态。

- [ ] **Step 2: 写失败的测试**

```python
def test_master_switches_live_in_page_heads(self):  # 四个总开关的 input 都在 .page-head 里，各自跟一个 data-master-hint
def test_welcome_and_automod_use_tabs(self):        # 有 panel-welcome-message/appearance/farewell/autoroles 和 panel-automod-rules/words/links；server.html 里不再有 'class="fold"'（除了 roles 的 sent-panels）
def test_wide_pages(self):                          # pg-overview、pg-welcome、pg-roles 带 page--wide，其他页面不带
```

`console_core.test.cjs`：

```js
test('master hint shows while the master switch is off', ...)  // source.checked=false → hint.hidden=false；改成 true → hint.hidden=true
```

- [ ] **Step 3: 运行，确认失败**

预期：上面新增的用例 FAIL，Step 1 的守护测试仍然 PASS。

- [ ] **Step 4: 改模板、宏、样式和 `dependencies`**

折叠块里的元素原样搬进对应的 `tab_panel`，元素 id 和 `data-*` 属性都不改。

- [ ] **Step 5: 运行三套测试，修好受影响的旧测试**

预期：全部 PASS，守护测试也 PASS。

- [ ] **Step 6: 提交**

```bash
git commit -m "feat: move master switches to page heads and split long pages into tabs"
```

### Task 6: 概览卡片、需要处理、加载和出错

**Files:**
- Modify: `website/templates/server.html`（`pg-overview`）、`static/js/modules/overview.js`、`static/css/console.css`（`.hero`、`.attention`、`.mod-grid`、`.mod-card`、骨架、出错块）、`zh.json`（`overview.attention_go`；出错和重试复用现有的 `common.load_failed`、`common.retry`）
- Test: `website/tests/overview.test.cjs`、`test_dashboard_templates.py`

**Interfaces:**
- Consumes：`Console.refreshModules()`、`console:modules` 和 `console:modules-failed` 两个事件，以及现有的 `summaryText`。
- Produces：
  - 标记：`#ov-attention`（`hidden`）、`#ov-modules`（初始 `aria-busy="true"`）、`#ov-error`（`hidden`）加 `#ov-retry`。每张卡片是 `.mod-card[data-row="<slug>"]`，里面是 `a.mod-card-link[data-mod]`、`[data-summary][data-blurb]`、`.sr-only[data-state]`，四个可开关的模块还有 `input[data-toggle]`，初始是 `disabled`。
  - `Overview.attention(modules, channels) → [{slug, text}]`：按 `modules` 的顺序，取 `summaryText` 结果里 `warn` 为真的模块，最多 3 个。
  - 只在快速开关请求进行中时给 `input.dataset.busy` 设 `'1'`，`render` 跳过这样的开关；首次 `render` 去掉所有开关的 `disabled`，并把 `#ov-modules` 的 `aria-busy` 设成 `"false"`。
  - 收到 `console:modules-failed` 时：如果还没有成功渲染过，隐藏 `#ov-modules`、显示 `#ov-error`；如果已经有数据，保持原样。点 `#ov-retry` 隐藏出错块并调用 `Console.refreshModules()`。
  - 卡片的图标块在模块开着时（不是可开关模块，或开关处于打开状态）加 `.is-on`。

- [ ] **Step 1: 写失败的测试**

```js
test('attention lists warned modules in order, at most three', ...)          // 四个 warn 模块和一个正常模块 → 返回前三个 warn 模块的 slug
test('attention skips modules when the channel list is unknown', ...)        // channels=null → []
test('switches stay disabled until the first render, then follow data', ...) // render 之后 disabled=false，checked 跟随 summary.enabled
test('a toggle in flight is not overwritten by render', ...)                 // dataset.busy='1' 的开关，render 后 checked 不变
test('first load failure shows retry; retry refreshes', ...)                 // 触发 failed → #ov-error.hidden=false；点重试 → refreshModules 被调用一次
```

```python
def test_overview_cards(self):  # pg-overview 里有 11 个 .mod-card，其中 4 个带 data-toggle 和 disabled
```

- [ ] **Step 2: 运行，确认失败**

- [ ] **Step 3: 实现**

值班卡片沿用现有的 `#ov-headline` 和 `#ov-facts`，改用 `.hero` 样式。卡片网格是 `repeat(auto-fill, minmax(230px, 1fr))`。需要处理那一行的链接带 `data-mod`，所以会走现有的离开拦截。

- [ ] **Step 4: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
git commit -m "feat: turn overview into module cards with attention notices"
```

### Task 7: 搜索设置（Ctrl K）

**Files:**
- Create: `website/static/js/command-palette.js`
- Modify: `website/templates/_console_base.html`（`{% block palette %}{% endblock %}` 放在 toast 之后；侧栏搜索按钮放在 `{% block side_search %}{% endblock %}` 里）、`templates/server.html`（填这两个块，引入脚本）、`static/css/console.css`（`.palette*`、`.search-btn`、`.is-flash`）、`icons.svg`（`i-search`）、`zh.json`（`palette.button`、`palette.placeholder`、`palette.empty`、`palette.label`）
- Test: `website/tests/command_palette.test.cjs`、`test_dashboard_templates.py`

**Interfaces:**
- Consumes：`Console.go(slug, tab)`（Task 4）、`DashboardExtras.matches`、页面上的 `data-title`、`data-group`、`[data-tab]`、`[data-panel]`、`.row-title`。
- Produces：
  - `window.CommandPalette = {collect(pages) → Entry[], filter(entries, query, limit = 12) → Entry[], open(), close(), jump(entry) → boolean}`，其中 `Entry = {label, where, slug, tab: string|null, row: Element|null}`。
  - `collect`：每个页面先放一条（`label` 是页面标题）；每个标签一条（"页面 › 标签"）；每个 `.row-title` 一条（"页面 › 行标题"，`tab` 取所在面板的 `data-panel`）。和已有条目文字相同的跳过。`where` 取 `page.dataset.group`，没有就用 `tr('nav.overview')`。
  - `filter`：查询为空时返回前 `limit` 条；否则按 `matches(label + ' ' + where, query)` 过滤。
  - 键盘：Ctrl K 或 ⌘K 打开和关闭，`e.isComposing` 为真时什么都不做；在搜索框里，上下键循环选择，回车调用 `jump`，Esc 关闭。正在输入法组合时，回车和方向键不处理。关闭后焦点回到打开前的元素。
  - `jump`：先关闭弹窗，再调用 `Console.go(slug, tab)`；返回 false（被未保存拦截）时就停下。有 `row` 时把 `row.closest('.row')` 滚动到中间，加 `.is-flash`，1000ms 后去掉。
  - 标记：`#palette`（`role="dialog"`、`aria-modal="true"`、`hidden`）、`#palette-input`（`aria-activedescendant`）、`#palette-list`（`role="listbox"`）、条目 `[role="option"][aria-selected]`、侧栏按钮 `#palette-btn`。

- [ ] **Step 1: 写失败的测试**

```js
test('collect builds page, tab and row entries without duplicates', ...)   // 桩出 automod 页：标签 words，里面行标题"违禁词列表"→ 有一条 {label:'自动审核 › 违禁词列表', slug:'automod', tab:'words'}
test('filter finds 违禁 and caps at the limit', ...)
test('Ctrl K during IME composition does nothing', ...)                    // keydown {key:'k', ctrlKey:true, isComposing:true} → 弹窗仍是 hidden
test('Enter during composition does not jump', ...)
test('jump navigates to the tab and flashes the row', ...)                 // Console.go 收到 ('automod','words')；该行有 is-flash；1000ms 后去掉（用假定时器）
test('jump stops when navigation is blocked', ...)                         // go 返回 false → 不滚动，不加 is-flash
```

```python
def test_palette_only_on_server_page(self):  # server.html 有 #palette 和 #palette-btn；dashboard.html、settings.html 没有
```

- [ ] **Step 2: 运行，确认失败**

- [ ] **Step 3: 实现**

弹窗外观参照试装实例：居中，距顶部 12vh，宽 `min(560px, 100%)`，`align-items: flex-start`。

- [ ] **Step 4: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
git commit -m "feat: add Ctrl K settings search"
```

### Task 8: 服务器列表、全局设置、登录页、错误页

**Files:**
- Modify: `website/templates/dashboard.html`、`settings.html`、`login_gate.html`、`error.html`、`static/css/console.css`（`.server-grid` 改用 `minmax(260px, 1fr)`，登录页示意图）
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Consumes：Task 3 的侧栏和 `invite_url` 宏。
- Produces：
  - `dashboard.html` 的菜单是"所有服务器"（当前页）加"全局设置"（不是 owner 时显示不可用徽标，沿用现有逻辑）。
  - `settings.html` 的菜单是"所有服务器"加上现有三个 `data-settings-tab`。
  - 登录页示意图：`.gate-backdrop` 里是 `.fake-side` 和 `.fake-main`，`.fake-main` 里有 `.fake-hero` 和 6 个 `.fake-card`；不再有 `.fake-rail` 和 `.fake-nav`。

- [ ] **Step 1: 写失败的测试**

把 `test_login_gate_sits_on_a_blurred_console_backdrop` 要求的部件改成 `['fake-side', 'fake-main', 'fake-card']`，并断言没有 `fake-rail`。

```python
def test_dashboard_and_settings_menus(self):  # dashboard.html 的菜单有 href="/dashboard" 且 aria-current="page"；settings.html 有 data-settings-tab="profile"、"runtime"、"admin"
```

- [ ] **Step 2: 运行，确认失败**

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
git commit -m "style: restyle server list, settings, login and error pages"
```

### Task 9: 本地预览逐页检查

**Files:**
- Modify：只改检查中发现问题的文件。
- 不进仓库的工具：本地假数据预览服务（会话临时目录里的 `preview.py`；没有的话就仿照 `test_dashboard_templates.render` 在仓库外写一个，模拟 `/api/guild/*`）。

- [ ] **Step 1: 启动预览**，用超长服务器名、超长频道名和 8 个服务器的假数据。
- [ ] **Step 2: 逐页检查**：服务器列表、概览、11 个模块页（欢迎页 4 个标签、自动审核 3 个标签）、全局设置三个分组、登录页、错误页。每页在 1440、1080、375 三种宽度和白天、夜间两种配色下看一遍。合格标准：页面不能左右滑动；长名字单行截断；焦点框看得见；保存条不遮住最后一行；切换器在 375 宽度下能完整显示。
- [ ] **Step 3: 交互检查**：在欢迎页改一处 → 标签出现小圆点 → 切换标签，修改还在 → 去别的模块会被拦 → 保存后小圆点消失；Ctrl K 搜"违禁"跳到对应位置；切换器搜索服务器；外观三个按钮的效果刷新后还在。
- [ ] **Step 4: 修复发现的问题**：每个修复先写一条能复现问题的测试；纯视觉问题在提交说明里写清楚是在哪个宽度、哪套配色下发现的。
- [ ] **Step 5: 运行三套测试**

预期：全部 PASS。

- [ ] **Step 6: 提交**

```bash
git commit -m "fix: polish workbench console after visual review"
```

之后：执行人走完 executing-plans 的整体审查和修复，再把本地预览交给用户试用；用户同意后，列出每一个要推送的提交（包括 `d3203f3` 和 `bd25382`），再推送 GitHub 和 prod。
