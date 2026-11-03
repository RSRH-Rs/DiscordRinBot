# 控制台改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把三个控制台页面换成和首页一致的 Discord 式外壳与统一样式，修掉溢出和排版问题，加上未保存提示条、概览模块清单和快捷开关。

**Architecture:** Jinja 基础模板 `_console_base.html` 提供服务器栏 + 功能列表 + 提示条；样式合并成一个 `console.css`；`server.js` 拆成 `console-core.js` 和每模块一个文件；文案从 `website/i18n/zh.json` 经 `tr()` 取用。后端只加 `summary`、一个只改 `enabled` 的接口、给模板传服务器栏数据。

**Tech Stack:** Quart + Jinja2、原生 JS（无构建）、SQLite（aiosqlite）、pytest、`node --test`。

**Spec:** `docs/superpowers/specs/2026-11-02-dashboard-redesign-design.md`（每个任务都要对照它；本计划只写决定，不重复 spec 的全部细节）

## Global Constraints

- 颜色只用 spec §4.1 表里的值；所有文字/底色组合 ≥ 4.5:1。
- 字体：Fredoka 500/600（Google Fonts，`display=swap`，preload 不阻塞）；正文 `"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif`。不加载 Nunito、Noto Sans SC。
- 字号 24 / 20 / 16 / 14 / 12.5，正文行高 1.6；不用全大写、不加字距。
- 不加载任何 CDN 脚本（`unpkg`、`@latest` 都不允许）。图标只用 `static/icons.svg`。
- 模板里不写 `style="`；JS 也不写 inline style，只有两种例外：弹出层定位（下拉框、emoji 选择器的 top/left/width）和 CSS 变量 `--x`。
- 所有界面文案经 `tr('key')`（Jinja 与 JS 同名），字典只有 `website/i18n/zh.json`；变量写 `{name}`。
- 断点：抽屉 `< 860px`；预览移到表单上方 `< 1100px`；内容列 `max-width: 760px`；服务器栏 72px，功能列表 232px。
- 动效只有提示条滑入、提示条抖动、抽屉滑出；`prefers-reduced-motion` 全关。
- 后端现有 GET/POST 接口的请求/返回格式不变。
- 提交直接在 master，标题 `feat:` / `fix:` / `style:` + 小写祈使句；每个任务结束时 `pytest` 和 `node --test website/tests/` 全绿；推送前先问用户。
- 静态资源版本号统一用 `?v=20261102a`（同一任务内再改则递增字母）。

## Review Focus

- **概览快捷开关 vs. 模块页草稿**：模块页有未保存改动时，概览里该模块的开关禁用并提示「这一页还有未保存的更改」；开关成功后把该模块标记为需重新加载（下次进入重新 GET）。→ Task 11 的测试。
- **Ctrl/⌘+S**：控制台页面上永远不弹浏览器「另存为」；输入法组合中（`isComposing`）不触发；没有改动或正在保存时什么都不做。→ Task 7 的测试。
- **超出预设/范围的旧时长**：库里存着 100000 秒（大于 max 86400）时显示为「自定义 1667 分钟」，不静默夹到 max；保存时才按 min/max 校验，原因写在提示条里。→ Task 13 的测试。
- **摘要里的频道已被删除**：`summary` 的频道 ID 在频道列表里找不到时显示「频道已删除」（warn 色），不显示裸 ID。→ Task 11 的测试。
- **有改动时按浏览器后退**：hash 改回当前页、提示条抖动，不弹 `window.confirm`。→ Task 7 的测试。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `website/i18n/zh.json` | 全部中文文案，按 `nav.*`、`common.*`、`toast.*`、`<模块>.*`、`cogs.*` 分层 |
| `website/i18n.py` | 读字典；`tr()`；`console_strings()` |
| `website/main.py` | 注册 Jinja 全局 `tr`、`console_strings` |
| `website/routes.py` | `manageable_guilds()`、`_guild_module_summary()`、`/modules/<slug>/enabled`、页面路由传 `guilds` |
| `website/templates/_console_base.html` | head、服务器栏、功能列表 block、顶栏、提示条、toast、字符串 JSON、脚本 |
| `website/templates/_console_macros.html` | `icon(name)`、`row(...)` 等小宏 |
| `website/templates/{dashboard,server,settings}.html` | 继承基础模板，只放各自内容 |
| `website/static/css/console.css` | 变量 → 基础 → 外壳 → 控件 → 页面 → 响应式 |
| `website/static/icons.svg` | lucide 图标 `<symbol id="i-…">` |
| `website/static/js/dashboard-ui.js` | 草稿生命周期 + 提示条 + 抽屉（保留现有导出） |
| `website/static/js/dashboard-extras.js` | 路由、可搜索下拉（保留） |
| `website/static/js/console-core.js` | `Console`：api、toast、tr、缓存、模块注册与路由、时长控件、依赖禁用 |
| `website/static/js/modules/*.js` | 每模块一个：`overview`、`welcome`、`roles`、`music`、`automod`、`moderation`、`giveaway`、`leveling`、`utility`、`botlog`、`serverlog` |
| `website/static/js/message-preview.js` | Discord 预览（改为不写 inline style、用新断点） |
| `website/tests/test_i18n.py`、`test_console_contrast.py`、`test_dashboard_status.py`、`test_dashboard_templates.py` | Python 测试 |
| `website/tests/dashboard_ui.test.cjs`、`console_core.test.cjs`、`overview.test.cjs` 等 | node 测试 |

删除：`static/css/{dashboard,dashboard-ui,server,dashboard-extras}.css`、`static/js/server.js`、`static/js/dashboard.js`（在 Task 15 确认无引用后删除）。

---

### Task 1: 文案字典与 `tr()`

**Files:**
- Create: `website/i18n/zh.json`、`website/i18n.py`
- Modify: `website/main.py`
- Test: `website/tests/test_i18n.py`

**Interfaces:**
- Produces: `i18n.tr(key: str, **vars) -> str`；`i18n.console_strings() -> dict[str, str]`（扁平的 `"a.b": "文本"`）；Jinja 全局 `tr`、`console_strings`。
- 字典先放外壳与通用键：`nav.servers`、`nav.overview`、`nav.group.community`/`safety`/`tools`、`nav.owner_only`、`nav.settings`、`nav.logout`、`nav.invite`、`status.online`/`offline`/`stale`/`unknown`/`not_joined`、`bar.unsaved`、`bar.reset`、`bar.save`、`bar.blocked`（「先保存或重置哦」）、`toast.saved`、`common.retry`、`common.load_failed`。后续任务往里加自己的键。

- [ ] **Step 1: 写失败测试** `test_i18n.py`：
  - `test_tr_returns_value`：`tr('bar.save') == '保存'`
  - `test_tr_interpolates`：字典里加 `common.count` = `'{n} 个'`，`tr('common.count', n=3) == '3 个'`
  - `test_missing_key_returns_key`：`tr('nope.key') == 'nope.key'`，并用 `assertLogs('rinbot.i18n', 'WARNING')` 断言有警告
  - `test_dictionary_is_flat_strings`：`console_strings()` 每个值都是非空 `str`，键匹配 `^[a-z_]+(\.[A-Za-z_]+)+$`
- [ ] **Step 2:** `pytest website/tests/test_i18n.py -v` → FAIL（模块不存在）
- [ ] **Step 3:** 实现 `i18n.py`：用 `json` 读同目录 `i18n/zh.json`，嵌套对象拍平成点分键，模块级缓存；logger 名 `rinbot.i18n`。`main.py`：`app.jinja_env.globals.update(tr=i18n.tr, console_strings=i18n.console_strings)`。
- [ ] **Step 4:** 测试 PASS；`pytest` 全量 PASS
- [ ] **Step 5:** `git commit -m "feat: add console string dictionary and tr helper"`

### Task 2: 服务器栏数据

**Files:**
- Modify: `website/routes.py`（`has_manage_permission` 附近加函数；`dashboard`、`global_settings`、`server_settings` 三个路由）
- Test: `website/tests/test_dashboard_status.py`

**Interfaces:**
- Produces: `manageable_guilds(all_guilds, bot_guild_ids: set[int]) -> list`，返回有管理权限的 guild 对象，每个带 `bot_joined: bool`，顺序：已加入在前，组内保持 Discord 返回的顺序。
- 模板变量：三个页面都收到 `guilds`（`manageable_guilds` 的结果）；`server.html` 额外收到 `guild`（不变）；`settings.html` 额外收到 `is_owner=True`。

- [ ] **Step 1: 写失败测试** `test_manageable_guilds_filters_and_orders`：用 `SimpleNamespace` 构造 4 个 guild：`id='1', permissions=0x20`（未加入）、`id='2', owner=True, permissions=0`（已加入）、`id='3', permissions=0x8`（未加入）、`id='4', permissions=0`（无权限），`bot_guild_ids={2}`；断言 id 顺序 `['2','1','3']`、`bot_joined` 依次为 `[True, False, False]`。
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现函数；`dashboard` 改用它；`server_settings` 与 `global_settings` 额外 `await fetch_bot_guild_ids()` 并传 `guilds`。
- [ ] **Step 4:** PASS；全量 PASS
- [ ] **Step 5:** `git commit -m "feat: pass manageable guilds to every console page"`

### Task 3: `/modules` 的 `summary`

**Files:**
- Modify: `website/routes.py`（`_guild_module_config` 旁新增；`api_guild_modules`）
- Test: `website/tests/test_dashboard_status.py`

**Interfaces:**
- Produces: `async _guild_module_summary(slug: str, gid: int) -> dict | None`，只读模式打开 SQLite（同 `_guild_module_config` 的 `?mode=ro` URI），DB 不存在、没有行、出错都返回 `None`。字段（全为 int）：
  - `welcome`：`welcome_channel`、`farewell_channel`、`auto_roles_count`（逗号分隔非空项数）
  - `automod`：`log_channel`、`rules_on`（`anti_spam, anti_badword, anti_link, anti_caps, anti_repeat` 中为真的个数）
  - `moderation`：`log_channel`、`mute_at`、`kick_at`、`ban_at`（对应 `warn_*_threshold`）
  - `music`：`notify_channel`、`dj_role`
  - `botlog` / `serverlog`：`channel_id`
  - `roles`：`panels`（`rr_panels` 中该 guild 行数；没有行时返回 `{"panels": 0}` 而不是 `None`）
  - `giveaway`：`active`（`giveaways` 中该 guild `ended=0` 行数；同上返回 0）
  - 其他 slug：`None`
- `/api/guild/<gid>/modules` 每个模块多一个 `summary` 键；用 `asyncio.gather` 和 `config_state` 并行。

- [ ] **Step 1: 写失败测试**
  - `test_summary_welcome`：建 `welcome_config(guild_id, welcome_channel, farewell_channel, auto_roles)`，插入 `(123, 777, 0, '1,2,')` → `{'welcome_channel':777,'farewell_channel':0,'auto_roles_count':2}`；gid 999 → `None`
  - `test_summary_automod_counts_rules`：五个规则列 `1,0,1,0,1` → `rules_on == 3`
  - `test_summary_counts_panels_and_active_giveaways`：rr_panels 两行、giveaways 一行 ended=0 一行 ended=1 → `{'panels':2}`、`{'active':1}`；DB 存在但无行 → `{'panels':0}`
  - `test_summary_missing_db_and_broken_db_are_none`：不存在路径、`b'not a database'` 文件 → `None`，且不创建文件
  - `test_modules_endpoint_includes_summary`：patch `check_guild_access`、`_guild_module_config`、`_guild_module_summary`（返回 `{'x':1}`）→ 每个模块有 `summary == {'x':1}`
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现（一个 `specs` 表映射 slug → (DB 常量名, SQL, 行转 dict 的函数)；DB 常量在调用时读取，测试才能 patch）。
- [ ] **Step 4:** PASS；全量 PASS
- [ ] **Step 5:** `git commit -m "feat: add per-module config summary to the modules api"`

### Task 4: 只改 `enabled` 的开关接口

**Files:**
- Modify: `website/routes.py`
- Test: `website/tests/test_dashboard_status.py`

**Interfaces:**
- Produces: `POST /api/guild/<gid>/modules/<slug>/enabled`，body `{"enabled": bool}`。
  - `slug` 只能是 `welcome`→`DB_WELCOME.welcome_config`、`automod`→`DB_AUTOMOD.automod_config`、`botlog`→`DB_BOTLOG.botlog_config`、`serverlog`→`DB_SERVERLOG.serverlog_config`；其他 404 `{"error": ...}`。
  - 未授权 401；`enabled` 不是 `bool` 400。
  - `INSERT OR IGNORE INTO <table> (guild_id) VALUES (?)` 后 `UPDATE <table> SET enabled=? WHERE guild_id=?`。
  - 然后 `await _notify_bot(slug, g)`，`audit(g, tr('audit.module_toggled', module=…, state=…), 操作者=actor)`。
  - 返回 `{"ok": true, "config_state": await _guild_module_config(slug, g)}`。
- 字典加 `audit.module_toggled`（「{module}已{state}」）、`common.enabled`（「开启」）、`common.disabled`（「关闭」）。

- [ ] **Step 1: 写失败测试**
  - `test_toggle_only_changes_enabled`：先在临时 `welcome.db` 写一行完整配置（`welcome_msg='自定义'`、`welcome_channel=777`、`enabled=1`），patch `check_guild_access`→True、`_notify_bot`/`audit`/`_resolve_actor` 为 mock，POST `{'enabled': False}` → 200，`config_state=='disabled'`，读回 `welcome_msg=='自定义'`、`welcome_channel==777`、`enabled==0`；`_notify_bot` 被以 `('welcome', 123)` 调用
  - `test_toggle_creates_row_when_missing`：空表 → 插入后 `enabled==1`，其他列为表默认值
  - `test_toggle_rejects`：未授权 401；`slug='music'` 404；body `{'enabled': 'yes'}` 和 `[]` 都 400
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现（表名来自白名单 dict，不拼接用户输入）。
- [ ] **Step 4:** PASS；全量 PASS
- [ ] **Step 5:** `git commit -m "feat: add an enabled-only module toggle endpoint"`

### Task 5: 图标集

**Files:**
- Create: `website/static/icons.svg`、`website/tools/make_icon_sprite.py`
- Test: `website/tests/test_dashboard_templates.py`（新用例）

**Interfaces:**
- Produces: `<symbol id="i-<name>" viewBox="0 0 24 24">`，name 用 lucide 原名：`layout-grid settings music smile-plus tags shield-check gavel gift trophy sliders-horizontal scroll-text history wrench user hash link message-circle info plus x chevron-right check triangle-alert log-out menu`。symbol 内保留 lucide 的 `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`。
- 文件头注释写 lucide 版本号和 ISC 许可。

- [ ] **Step 1: 先问用户**：「需要下载 `lucide-static@<版本>`（npm，ISC，约 X MB）来取这 25 个图标的 SVG，可以吗？」得到同意再继续。版本选一个发布至少两周的固定版本。下载放进 scratchpad 的新空目录。
- [ ] **Step 2:** 写 `make_icon_sprite.py <lucide-static 目录>`：读 `icons/<name>.svg`，取内部元素，输出 sprite；提交脚本（不提交下载的包）。
- [ ] **Step 3: 写测试** `test_icon_sprite_has_every_used_icon`：解析 `icons.svg` 的 symbol id；正则扫描 `templates/*.html` 和 `static/js/**/*.js` 中的 `icon('name')` / `#i-name` 用法，断言每个都存在。
- [ ] **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat: add a local svg icon sprite"`

### Task 6: `console.css` 基础层与对比度测试

**Files:**
- Create: `website/static/css/console.css`、`website/tests/test_console_contrast.py`

**Interfaces:**
- Produces: `:root` 变量名（后续任务只用这些）：`--bg --panel --line --text --muted --rin --rin-hover --chip-bg --chip-text --rail --chan --active --side-text --ok --ok-bg --warn --warn-bg --bad --bad-bg --bar --bar-text --bar-reset --focus`(`#9B3F57`) `--font-display --font-body --rail-w`(72px) `--nav-w`(232px) `--content-w`(760px)。
- 类名约定（BEM 风格，单类选择器）：`.shell .rail .rail-item .rail-sep .nav .nav-group .nav-item .nav-dot(--on/--off/--warn/--unknown) .user-card .topbar .crumbs .page .page-head .section .section-title .list .row .row-text .row-title .row-hint .row-control .tog .btn(--primary/--secondary/--text/--danger) .select .input .textarea .num .seg .note(--warn/--bad) .chip .unsaved-bar(.is-open .is-shaking) .toast(--ok/--bad) .skeleton .empty .drawer-backdrop`。
- 本任务只写到「外壳 + 控件」层；页面层由各页面任务追加到文件末尾对应的分段注释下。

- [ ] **Step 1: 写失败测试** `test_console_contrast.py`：从 `console.css` 的 `:root` 解析 `--name: #hex`；对这些组合断言 ≥ 4.5：`text/bg text/panel muted/bg muted/panel #FFFFFF/rin chip-text/chip-bg side-text/chan side-text/rail text/active ok/ok-bg warn/warn-bg bad/bad-bg bar-text/bar bar-reset/bar #FFFFFF/rin-hover`。另断言 `console.css` 不含 `!important`。
- [ ] **Step 2:** 运行 → FAIL（文件不存在）
- [ ] **Step 3:** 写 `console.css` 的变量、基础（盒模型、字体栈、焦点框 `outline: 2px solid var(--focus); outline-offset: 2px`、`[hidden]{display:none}`、reduced-motion）、外壳网格（`grid-template-columns: var(--rail-w) var(--nav-w) minmax(0,1fr)`，`< 860px` 时 rail+nav 变成固定定位抽屉）、全部控件。行：`.row{display:flex;gap:16px}` `.row-text{flex:1;min-width:0;overflow-wrap:anywhere}`，`< 860px` 时 `flex-direction:column` 且控件 `width:100%`。
- [ ] **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "style: add console stylesheet tokens, shell and controls"`

### Task 7: 基础模板、提示条与草稿生命周期

**Files:**
- Create: `website/templates/_console_base.html`、`website/templates/_console_macros.html`
- Modify: `website/static/js/dashboard-ui.js`、`website/static/js/dashboard-extras.js`（`createHashRouter` 的 `canLeave` 不变，调用方改用新 `confirmLeave`）
- Test: `website/tests/dashboard_ui.test.cjs`、`website/tests/dashboard_extras.test.cjs`

**Interfaces:**
- Consumes: `tr`、`console_strings`（Task 1）、`guilds`（Task 2）、`icons.svg`（Task 5）、`console.css`（Task 6）。
- 基础模板 blocks：`title`、`nav`（功能列表内容）、`topbar`（页面名、面包屑）、`content`、`scripts`。变量：`active_guild_id`（服务器栏选中项，可为 `None`）、`user`、`guilds`。服务器栏 `<a class="rail-item" href="/dashboard/server/{{id}}" data-guild="{{id}}" aria-label="{{name}}" title="{{name}}">`；没图标时显示 `name[:1]`。字符串：`<script type="application/json" id="console-strings">{{ console_strings()|tojson }}</script>`。提示条 `<div class="unsaved-bar" id="unsaved-bar" role="region" aria-label="{{ tr('bar.unsaved') }}" hidden>` 含文字、`#unsaved-reset`、`#unsaved-save`、`#unsaved-error`（错误文字）。
- 宏：`icon(name, size=16)` → `<svg class="icon" width height aria-hidden="true"><use href="{{ url_for('static', filename='icons.svg') }}#i-{{name}}"/></svg>`；`row(title, hint=None, for_id=None)` 用 `caller()` 放控件。
- `DashboardUI` 保留全部现有导出，新增/修改：
  - `onSave(id, fn: () => Promise<void>)`：给页面根注册保存函数。
  - `reset(id)`：按 `snapshot` 里记录的值把输入恢复（按元素 key 回填 `value`/`checked`，`[data-tags]` 容器用记录的数组重建标签），然后对每个改动的元素派发 `input` 和 `change`。
  - `save()`：对当前活动的脏根调用其 `onSave`，包在 `saving()` 里；失败时把 `e.message` 写进 `#unsaved-error`，提示条保持打开。
  - `shake()`：给提示条加 `is-shaking`，`animationend` 后移除；同时把文字换成 `tr('bar.blocked')` 2 秒。
  - `confirmLeave(roots)`：有正在保存的 → `false`；有脏的 → `shake()` 并返回 `false`；否则 `true`。不再调用 `window.confirm`。
  - 提示条：任一带 `data-draft` 且未标 `data-draft-inline` 的根变脏 → 显示（加 `is-open`），全部干净 → 隐藏。保存期间「重置」「保存」都 `disabled`。
  - 键盘：`keydown` 上 `(ctrlKey||metaKey) && key.toLowerCase()==='s'` 时总是 `preventDefault()`；`!e.isComposing` 且有脏根且没有在保存时调用 `save()`。
  - 抽屉：`toggleSidebar/closeSidebar` 改为作用于 `.shell` 上的 `is-drawer-open`，按钮 `#menuBtn`，遮罩 `.drawer-backdrop`；其余行为不变。
- 字典加 `bar.*` 已有、`bar.save_failed`（「没保存上：{reason}」）。

- [ ] **Step 1: 写失败测试**（在 `dashboard_ui.test.cjs` 现有 fixture 上扩展）
  - `reset restores saved values and fires change`：注册根 → 改一个 checkbox 和一个 text → `reset` → 值回到初值，`change` 被派发，`dirty()` 为 false
  - `bar opens when dirty and closes when changed back`
  - `confirmLeave shakes instead of confirming`：`window.confirm` 设为抛错的函数；脏根时返回 false 且提示条有 `is-shaking`
  - `ctrl+s prevents default always and saves only when dirty`：干净时 `preventDefault` 被调用、`onSave` 未调用；脏时调用一次；`isComposing:true` 时未调用
  - `reset and save are disabled while saving`
  - `save failure keeps bar open with reason`
  - `dashboard_extras.test.cjs` 新增 `back navigation while dirty rewrites hash and does not confirm`：`canLeave` 返回 false 时 hashchange 后 `history.replaceState` 写回当前 id
- [ ] **Step 2:** `node --test website/tests/` → 新用例 FAIL
- [ ] **Step 3:** 实现 `dashboard-ui.js` 改动与两个模板文件；`console.css` 追加提示条/抽屉动效（`@keyframes bar-shake`，reduced-motion 下不动）。
- [ ] **Step 4:** node 测试 PASS；`pytest` PASS
- [ ] **Step 5:** `git commit -m "feat: add console base template and unsaved changes bar"`

### Task 8: `console-core.js`

**Files:**
- Create: `website/static/js/console-core.js`
- Test: `website/tests/console_core.test.cjs`

**Interfaces:**
- Produces 全局 `window.Console`：
  - `tr(key: string, vars?: object) -> string`（读 `#console-strings`；缺键返回键名并 `console.warn`）
  - `api(path, method='GET', body=null) -> Promise<any>`（`/api/guild/${GID}` 前缀；错误抛 `Error(err.error || tr('common.request_failed',{status}))`）；`apiGlobal(path, …)`
  - `toast(message: string, kind: 'info'|'ok'|'bad'='info')`
  - `escapeHtml(s)`；`channels() / roles() -> Promise<Array<{id,name}>>`（缓存 + 并发去重，同现有 `getCh/getRoles`）；`channelName(id, channels) -> string|null`
  - `module({slug, load?: () => Promise<void>, save?: () => Promise<void>, isLoaded?: () => boolean, invalidate?: () => void})`：登记模块；`load` 包在 `DashboardUI.loading` + `guardedLoader` 语义里（加载一次、失败可重试、不覆盖草稿）；`save` 交给 `DashboardUI.onSave('pg-'+slug, …)`。
  - `invalidate(slug)`：让下次进入重新加载（页面不脏时立即清 loaded 标志）。
  - `go(slug)` / 路由：用 `DashboardExtras.createHashRouter`，ids 为所有 `.page[data-slug]`；`show` 切换 `.page.is-active`、更新 `aria-current`、`document.title = tr('title.page',{page, guild})`、顶栏页面名与面包屑、关抽屉、滚到顶、调用模块 `load`。
  - 服务器栏点击：有脏根时 `preventDefault` + `DashboardUI.shake()`；否则把 `href` 改成 `…#<当前 slug>` 再跳。
  - `duration.split(seconds:number) -> {preset: 60|300|3600|86400|null, amount:number, unit:'minute'|'hour'|'day'}`；`duration.join(amount, unit) -> number`；`duration.mount(el)`：把 `<div class="seg" data-duration data-for="am-mute">` 渲染成分段按钮 + 自定义（数字 + 单位 select），双向同步到隐藏的 `<input type="number" id="am-mute">`（保留原 id，collect 逻辑不变），同步时派发 `input`。
  - `dependencies(root)`：对 `[data-depends-on]` 元素，按引用的 checkbox 是否勾选设置 `aria-disabled` 与内部控件 `disabled`；监听 `change`。
  - 加载中：`.page[aria-busy=true]` 下的 `.list` 与 `.section` 由 CSS 显示骨架底纹（`.skeleton` 动画），不另写占位 markup。
  - 30 秒状态轮询（`document.hidden` 时跳过），数据没变时不重绘（沿用 `_modulesSignature` 思路），返回数据通过 `document` 事件 `console:modules` 分发 `{bot_state, modules}`。
- 字典加 `common.request_failed`、`title.page`、`duration.minute/hour/day/custom` 与四个预设标签。

- [ ] **Step 1: 写失败测试** `console_core.test.cjs`（vm + 最小 DOM，同现有测试风格）：
  - `duration.split`，规则：命中四个预设之一则 `preset` 为该值；否则取能整除的最大单位（天 > 小时 > 分钟），都不能整除时用分钟并四舍五入。断言：`300 → {preset:300, amount:5, unit:'minute'}`；`5400 → {preset:null, amount:90, unit:'minute'}`；`7200 → {preset:null, amount:2, unit:'hour'}`；`100000 → {preset:null, amount:1667, unit:'minute'}`；`join(3,'hour') === 10800`
  - `tr falls back to key and interpolates`
  - `api throws server error message`（stub `fetch` 返回 `{ok:false,status:500,json:()=>({error:'坏了'})}`）
  - `channels() dedupes concurrent requests`（两次并发调用只 fetch 一次）
  - `rail click while dirty is blocked`
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现 `console-core.js`（从 `server.js` 搬 api/toast/缓存/路由/轮询，按上面接口改名）。
- [ ] **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat: add shared console core script"`

### Task 9: 服务器列表页

**Files:**
- Modify: `website/templates/dashboard.html`、`website/static/css/console.css`（「页面：服务器列表」分段）、`website/i18n/zh.json`
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Consumes: 基础模板、`guilds`、`is_owner`；搜索沿用 `dashboard.js` 的逻辑，搬进 `console-core.js` 的 `Console.serverSearch()`（`#server-search`、`#server-search-result`、`#server-no-results`、`[data-guild-name]`、`[data-guild-id]` 这些 id/属性保持不变）。
- 邀请链接保持现在的 URL 和 `permissions=1374694796438`（现有测试断言它）。
- 「小凛未加入」分组的 `<section>` 加 `id="not-joined"`，服务器栏的「＋」链接到 `/dashboard#not-joined`。

- [ ] **Step 1: 更新测试**：`render()` 给 env 加 `tr`/`console_strings` 全局与 `guilds`；`test_invites_do_not_request_administrator_and_match_homepage` 保持通过；新增 `test_dashboard_lists_joined_first_and_escapes_names`（已加入卡片在未加入之前、`小凛 &lt;img src=x&gt;` 出现且未转义的 `<img src=x>` 不出现）。
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 重写 `dashboard.html`：继承基础模板；`nav` block 是「我的服务器」「全局设置」（非主人显示 `nav.owner_only`）；两组网格 `minmax(240px,1fr)`；整卡可点（已加入）；空状态用 `confused-480.webp`。
- [ ] **Step 4:** PASS；浏览器在预览里 1440 和 375 看一眼没有溢出
- [ ] **Step 5:** `git commit -m "feat: move the server list onto the new console shell"`

### Task 10: 全局设置页

**Files:**
- Modify: `website/templates/settings.html`、`website/static/js/dashboard-extras.js`（`setupSettings` 改为读功能列表里的 `[data-settings-tab]`）、`console.css`（「页面：全局设置」分段，吸收原 `<style>` 块）
- Test: `website/tests/test_dashboard_templates.py`、`website/tests/avatar_ui.test.cjs`

**Interfaces:**
- 三个分区链接放进 `nav` block，保留 `data-settings-tab` 与 `.tab-draft`；面板 `data-settings-panel` 与 `data-draft` 的 id 不变（`test_settings_groups_preserve_all_independent_drafts` 必须继续通过）。
- 所有 `data-draft` 根加 `data-draft-inline`（它们自带按钮，不驱动提示条）。
- 内联 `<script>` 逻辑不变，只把文案换成 `Console.tr`；`avatar_ui.test.cjs` 按需要给 vm 上下文补 `Console` 桩。

- [ ] **Step 1:** 先跑现有 settings 相关测试作为基线（应 PASS）
- [ ] **Step 2:** 改模板与样式；`<style>` 块移进 `console.css`
- [ ] **Step 3:** 测试 PASS；预览里切三个分区、头像上传按钮可用
- [ ] **Step 4:** `git commit -m "feat: move global settings onto the new console shell"`

### Task 11: 概览

**Files:**
- Create: `website/static/js/modules/overview.js`、`website/tests/overview.test.cjs`
- Modify: `website/templates/server.html`（先写外壳、功能列表和 `#overview` 页；其他模块页的旧 markup 原样搬入 `content`，后续任务逐个重写）、`console.css`（「页面：概览」）、`zh.json`

**Interfaces:**
- Consumes: `console:modules` 事件、`Console.channels()`、`/api/guild/<gid>/info`、`POST /modules/<slug>/enabled`（Task 4）、`DashboardUI.dirty`。
- Produces（导出到 `window.Overview` 便于测试）：
  - `summaryText(slug, summary, channels) -> {text: string, warn: boolean} | null`：规则——频道字段为 0 → 对应提示（`welcome` 两个频道都为 0 且 `auto_roles_count` 为 0 → `{text: tr('overview.welcome.unset'), warn:true}`；`botlog/serverlog` `channel_id` 0 → `tr('overview.log.unset')` warn）；频道 ID 在列表里找不到 → `tr('overview.channel_deleted')` warn；`automod` → `tr('overview.automod.rules',{n})`；`roles` → `tr('overview.roles.panels',{n})`；`giveaway` → `tr('overview.giveaway.active',{n})`；`moderation`/`music` 按 spec 拼频道名；`summary` 为 `null` → `null`（调用方显示模块简介）。
  - `TOGGLE_SLUGS = ['welcome','automod','botlog','serverlog']`
  - `toggle(slug, enabled)`：页面 `pg-<slug>` 脏时不发请求，开关恢复并 `toast(tr('overview.toggle_blocked'))`；否则开关 `aria-busy` + disabled → POST → 成功 `Console.invalidate(slug)` 并用返回的 `config_state` 更新状态点；失败恢复原状态并 toast 原因。
- 页面结构：值班卡片（`manage-480.webp`，`width/height` 写明）+ `info` 数据一行（读不到的项不渲染）+ 三组 `.list`。功能列表三组静态写在模板里，状态点由 `console:modules` 更新（`.nav-dot--on/--off/--warn/--unknown`，`warn` 对应 `unconfigured`）。
- 字典加 `overview.*`、`nav.module.<slug>`（模块显示名，含 `botlog`「机器人运行日志」、`serverlog`「服务器事件日志」）、`module.<slug>.desc`。

- [ ] **Step 1: 写失败测试** `overview.test.cjs`：
  - `summaryText` 的 7 种情况，含 `channel_deleted`（`summary.channel_id=5`，频道列表没有 5 → warn）和 `null`
  - `toggle is blocked while the module page is dirty`（`DashboardUI.dirty` 桩返回 true → 不调用 fetch，checkbox 恢复）
  - `toggle failure restores the switch`（fetch 返回 500）
  - `toggle success invalidates the module`
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现模板、`overview.js`、样式；`server.html` 引入 `console-core.js`、`overview.js`，旧 `server.js` 暂时仍引入以驱动未迁移页面（重复的函数以 `console-core` 为准，冲突处在 `server.js` 里删掉）。
- [ ] **Step 4:** PASS；预览 1440/375 检查概览，`scrollWidth <= clientWidth`
- [ ] **Step 5:** `git commit -m "feat: redesign the server overview with module status list"`

### Task 12: 欢迎、领取身份组、音乐

**Files:**
- Create: `website/static/js/modules/{welcome,roles,music}.js`
- Modify: `server.html`（三个页）、`message-preview.js`、`server.js`（删掉已搬走的函数）、`console.css`、`zh.json`
- Test: `website/tests/welcome_image_ui.test.cjs`（改为读 `modules/welcome.js`）、`dashboard_extras.test.cjs`（预览相关）、`test_dashboard_templates.py`

**Interfaces:**
- 每个文件调用 `Console.module({slug, load, save, isLoaded})`；表单元素 id 全部保持现有值（`w-*`、`rr-*`、`mu-*`），POST body 不变。
- 欢迎页：总开关 `#w-enabled`，其余行 `data-depends-on="w-enabled"`；三个 `<details>` 折叠区保留 `data-optional-status`。
- `message-preview.js`：不再移动 `.cfg-section`，改为模板里直接写 `.editor` 网格（`.editor-form` + `.editor-preview`），`< 1100px` 由 CSS `order` 把预览放到表单上方；`<details>` 默认展开状态仍按 `min-width:1100px`。去掉所有 `style` 写入。
- emoji 选择器（`#emoji-picker` 与 `openEmojiPicker` 等函数）搬进 `roles.js`，markup 去掉 inline style，用 `hidden` 控制显示。
- 身份组面板：每行 `.rr-row` 用 CSS grid `44px minmax(0,1fr) 36px`；删除按钮用 `icon('x')`；`addRoleRow` 不写 inline style。离开拦截：表单有内容时 `pg-roles` 视为脏（保留 `data-draft`）。
- `welcome_image_ui.test.cjs` 读取路径改为 `static/js/modules/welcome.js`，切片标记改为文件里的 `/* ── end validation ── */` 注释（在验证函数后加这行）。

- [ ] **Step 1:** 更新测试的读取路径与模板断言（`test_role_editor_follows_message_then_roles_then_destination` 保持通过）；运行 → FAIL
- [ ] **Step 2:** 实现三页与 JS
- [ ] **Step 3:** PASS；预览里：改欢迎文案 → 提示条出现 → 重置 → 恢复；预览随输入更新；375 下预览在表单上方
- [ ] **Step 4:** `git commit -m "feat: rebuild welcome, role panel and music pages"`

### Task 13: 自动审核、管理模块

**Files:**
- Create: `website/static/js/modules/{automod,moderation}.js`、`website/tests/automod_ui.test.cjs`
- Modify: `server.html`、`server.js`、`console.css`、`zh.json`

**Interfaces:**
- 自动审核：总开关 `#am-enabled`；规则行 `data-depends-on="am-enabled"`；阈值/违禁词/白名单再依赖各自的子开关（`am-spam`、`am-bw`、`am-link`、`am-caps`、`am-repeat`）。禁言时长 `#am-mute` 变成隐藏 number + `<div class="seg" data-duration data-for="am-mute" data-min="60" data-max="86400">`。标签列表容器加 `data-tags`。
- 管理模块：处罚表格三行（禁言 `#mod-mt` + 时长 `#mod-md` 用 duration 控件 `data-min="60" data-max="86400"`；踢出 `#mod-kt`；封禁 `#mod-bt`），说明写 `tr('moderation.zero_off')`。最近记录：动作标签 `.chip--<action>`，颜色在 CSS 里定义且满足对比度（加进 Task 6 测试的组合列表）。
- 超范围值：duration 控件显示换算值；保存时若隐藏 input 的值超出 `data-min/max`，`save` 抛 `Error(tr('duration.out_of_range',{min,max}))`，提示条显示该原因。

- [ ] **Step 1: 写失败测试** `automod_ui.test.cjs`：
  - `out-of-range stored duration shows as custom and blocks save`：load 返回 `mute_duration: 100000` → 自定义被选中、数值 1667 分钟；`save()` reject，消息含「86400」
  - `master switch disables dependent rows`：`am-enabled` 取消勾选 → 依赖行 `aria-disabled="true"`、内部 input `disabled`
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现
- [ ] **Step 4:** PASS；预览里操作一遍，375 宽无溢出
- [ ] **Step 5:** `git commit -m "feat: rebuild automod and moderation pages"`

### Task 14: 抽奖、等级、指令管理、两种日志、通用工具

**Files:**
- Create: `website/static/js/modules/{giveaway,leveling,utility,botlog,serverlog}.js`
- Modify: `server.html`、`console.css`、`zh.json`
- Test: `website/tests/test_dashboard_templates.py`、`website/tests/utility_ui.test.cjs`

**Interfaces:**
- 抽奖：表单 `.form-grid`（`repeat(auto-fit, minmax(240px,1fr))`）；结束时间快捷 `.seg` 预设 1 小时 / 1 天 / 1 周 / 自定义，写入 `#gw-end`（`datetime-local`，本地时区）。
- 等级：前三名 `.lb-row--top`；名字单行截断。
- 指令管理：分组 `<details open>`；组名 `tr('cogs.'+cog)`，字典里有 `cogs.Music/Moderation/Leveling/Help/General/Giveaway/Welcome/ReactionRoles/AutoMod/BotLog/ServerLog/CommandToggle/MusicConfig/BotConfig/GlobalSettings`，缺失时显示原名（`Console.tr` 返回键名时改用原 cog 名）；批量开关规则不变。
- 两种日志：总开关 + `data-depends-on`；「发送测试日志」为 `.btn--secondary`。
- 通用工具：`.cmd-grid`（`repeat(auto-fill, minmax(220px,1fr))`）。
- 空状态（抽奖、管理记录、排行榜、身份组面板）用 `.empty` + `confused-480.webp` + 一句下一步。

- [ ] **Step 1: 写失败测试** `utility_ui.test.cjs`：`cog label falls back to raw name`（`cogs.Netease` 不在字典 → 显示 `Netease`）；`groups render open`
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现；`server.js` 此时应已为空，从 `server.html` 移除引用
- [ ] **Step 4:** PASS；预览逐页 1440/375
- [ ] **Step 5:** `git commit -m "feat: rebuild giveaway, leveling, commands and log pages"`

### Task 15: 清理、登录页/错误页、防回退测试

**Files:**
- Delete: `static/css/{dashboard,dashboard-ui,server,dashboard-extras}.css`、`static/js/server.js`、`static/js/dashboard.js`
- Modify: `templates/login_gate.html`、`templates/error.html`（改链 `console.css`，去掉 Nunito/Noto；登录页不继承外壳）、`test_dashboard_templates.py`

**Interfaces:**
- `pg-personalizer` 与其 JS 已在前面任务中不再出现；这里用测试确认。

- [ ] **Step 1: 写测试**（`test_dashboard_templates.py`）：
  - `test_no_inline_styles_or_cdn`：渲染 `dashboard/server/settings/login_gate/error` 五个模板，断言不含 `style="`、`unpkg.com`、`@latest`、`Noto+Sans+SC`、`Nunito`
  - `test_every_tr_key_exists`：正则扫描 `templates/*.html` 的 `tr('…')` 与 `static/js/**/*.js` 的 `Console.tr('…')` / `tr('…')` 字面量键，断言都在 `console_strings()` 里（动态拼接的 `cogs.`、`nav.module.` 前缀除外）
  - `test_no_personalizer_page`：`server.html` 渲染结果不含 `pg-personalizer`
  - `test_static_assets_exist_and_versioned`：模板引用的每个 `/static/...` 文件都存在；css/js 引用都带 `?v=20261102`
  - 删除旧的版本号断言（`dashboard-extras.js?v=20260826c` 等）
- [ ] **Step 2:** 删除旧文件，`grep -r` 确认无引用
- [ ] **Step 3:** 全部测试 PASS
- [ ] **Step 4:** `git commit -m "fix: remove legacy dashboard styles and dead pages"`

### Task 16: 浏览器验收

**Files:** 无仓库改动（预览脚本在 scratchpad：`preview.py`，`.claude/launch.json` 不提交）

- [ ] **Step 1:** 更新预览脚本的假数据：加 `summary`、`POST /modules/<slug>/enabled`（可配置返回 500）、所有 POST 可切换成 500。
- [ ] **Step 2:** 每个页面在 1440、1280、860、375 截图；每页执行 `[document.documentElement, document.querySelector('.main')].every(e => e.scrollWidth <= e.clientWidth)` 应为 `true`。
- [ ] **Step 3:** 逐项操作并记录结果：改动→提示条出现、改回→收起；重置；`Ctrl+S`（含输入法组合中）；有改动时点功能列表/服务器栏/浏览器后退被拦且抖动；保存 500 时错误留在提示条；概览开关成功/失败/草稿中被拦；抽屉开关与焦点恢复；时长预设与自定义；减少动态效果；控制台无报错。
- [ ] **Step 4:** 把结果（含未通过项）报告给用户；有问题回到对应任务修。

---

## Self-Review Notes

- Spec 覆盖：§4.2 外壳→T7/T8；§4.3 控件→T6/T8/T13；§4.4 交互→T7/T8/T11；§5.1→T9；§5.2→T11；§5.3→T12–T14；§5.4→T10；§6→T1（及各任务加键）；§7.1→T3；§7.2→T4；§7.3→T2；§8→T5/T6/T15；§9→各任务测试 + T15/T16；§10→各任务提交，推送不在计划内（需用户同意）。
- 旧 `server.js` 在 T11–T14 间逐步掏空，T14 末尾移除引用，T15 删除文件。
