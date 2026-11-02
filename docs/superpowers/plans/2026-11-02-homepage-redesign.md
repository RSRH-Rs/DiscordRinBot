# 官网首页改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `website/templates/index.html` 重写成「频道里的小凛」：以 Discord 对话为叙事、中英双语、贴纸会动、手机可用。

**Architecture:** 单个 Jinja 模板，CSS/JS 内联。双语文字成对写在 HTML 里（`data-l="zh"` / `data-l="en"`），`<head>` 里的脚本在绘制前设置 `<html data-lang>`，由 CSS 只显示一种语言。贴纸的 WebP 和闭眼帧由 Pillow 脚本离线生成并提交。后端不改。

**Tech Stack:** Quart/Jinja2 模板、原生 CSS/JS、Pillow（生成资源）、pytest（模板与资源测试）。

**Spec:** `docs/superpowers/specs/2026-11-02-homepage-redesign-design.md`

## Global Constraints

- 只改 `website/templates/index.html`；新增 `website/static/images/rin/*.webp`、`website/tools/make_rin_assets.py`、`tests/test_homepage.py`。不碰 `routes.py`、其他模板、两个 `config.py`。
- 邀请链接必须一字不差：`https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=1374694796438&integration_type=0&scope=bot+applications.commands`，并带 `target="_blank" rel="noopener"`。
- 控制台链接 `/dashboard`；GitHub `https://github.com/RSRH-Rs/DiscordRinBot`；反馈问题 `https://github.com/RSRH-Rs/DiscordRinBot/issues`。
- 颜色：channel `#EEF0F8`、surface `#FFFFFF`、ink `#2A2440`、muted `#5E5873`、rin `#D9577A`、apricot `#F2A66B`、leaf `#6DB57A`、blurple `#5865F2`（只用于 BOT 标签和 `/指令`）。
- 字体：英文 Fredoka 500/600/700（Google Fonts，`display=swap`）；中文系统字体栈 `"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif`。不加载 Noto Sans SC，不加载 lucide。
- localStorage 键继续用 `rinbot_lang`，取值 `zh` / `en`。
- 内容默认可见。只有首屏对话有一段编排好的依次出现动画；所有动画遵守 `prefers-reduced-motion`。
- 文案用小凛第一人称、口语、简短；只描述 bot 真有的功能。标题使用 spec 3.3 节给定的中英文。
- 提交：在 master 上用用户身份，只 `git add` 本计划涉及的文件（另一个会话也在 master 上工作）。不推送。

## Review Focus

1. **localStorage 抛异常**（Safari 无痕模式、站点数据被禁）：仍要按浏览器语言选出默认语言，切换在本次会话内有效，页面不报错。由 Task 2 第 6 步的浏览器检查覆盖。
2. **`/api/stats` 失败、返回 0 或非数字**：频道头保持显示 12。由 Task 2 第 6 步检查。
3. **英文长文案在 375px 宽度**（导航三个入口、嵌入卡、按钮）：自动换行，不出现横向滚动。由 Task 4 第 2 步检查。
4. **关闭 JS**：中文内容完整可见，首屏对话不会卡在透明状态。动画用的初始隐藏样式必须挂在 `html.js` 下，由 head 脚本添加这个类。Task 3 有对应测试，Task 4 做手动检查。
5. **首选语言是英文、但列表里也有中文**（`['en-US','zh-CN']`）：应显示英文；`['zh-TW']` 应显示中文。由 Task 2 第 6 步在控制台调用 `rinPickLang` 检查。

---

### Task 1: 贴纸资源（WebP + 闭眼帧）

**Files:**
- Create: `website/tools/make_rin_assets.py`
- Create（生成）: `website/static/images/rin/{welcome,music,manage,confused}-{480,960}.webp`、`{manage,confused}-blink-{480,960}.webp`、`bot-avatar-96.webp`
- Test: `tests/test_homepage.py`

**Interfaces:**
- Produces: 上述文件名，Task 2–3 在模板里用 `url_for('static', filename='images/rin/<name>-<w>.webp')` 引用。

- [ ] **Step 1: 写失败的测试** `test_rin_assets_exist_and_sized`：对每个 `name ∈ {welcome,music,manage,confused,manage-blink,confused-blink}` 和 `w ∈ {480,960}`，断言 `website/static/images/rin/{name}-{w}.webp` 存在、`Image.open(p).width == w`、模式为 `RGBA`、文件小于 150KB；`bot-avatar-96.webp` 宽 96。
- [ ] **Step 2: 运行确认失败**：`python -m pytest tests/test_homepage.py -q`，预期 FAIL（文件不存在）。
- [ ] **Step 3: 实现 `make_rin_assets.py`**。命令行 `python website/tools/make_rin_assets.py`，读取同目录下的原 PNG。
  - 缩放用 `Image.LANCZOS`，WebP `quality=82, method=6`。
  - 闭眼帧算法沿用 brainstorm 原型：先定位眼睛包围盒（manage：`(479,523,523,665)`、`(707,753,510,654)`；confused：`(461,505,500,646)`、`(684,728,526,670)`，坐标基于 1254px 原图）。在外扩 9px 的椭圆内逐行做左右肤色线性插值，从下往上处理；端点不像肤色的行（RGB 和 ≤ 640，说明碰到了发丝描线），只替换 `R−B < 60` 的像素，保住棕色发丝线。最后用 4 倍超采样画眼睑弧线：颜色 `(38,24,20)`，宽 8px，角度 25°–155°，弧宽是眼宽的 1.6 倍，中心在眼高 62% 处。
  - 生成时同时输出一张 960 宽的眼部裁切预览，保存到 `sys.argv[1]`（可选参数）用于人工检查，不写进仓库。
- [ ] **Step 4: 生成并检查**：运行脚本，再运行 pytest，预期 PASS。用 Read 打开眼部裁切预览，确认没有白边、没有发丝断点或棕色涂抹；有问题就调参数后重新生成。
- [ ] **Step 5: 提交**：`git add website/tools/make_rin_assets.py website/static/images/rin/*.webp tests/test_homepage.py`，提交信息 `Homepage: generate WebP stickers and blink frames`。

### Task 2: 模板骨架：head、双语机制、导航、首屏、页脚

**Files:**
- Modify: `website/templates/index.html`（整文件重写）
- Test: `tests/test_homepage.py`
- 本地预览（不提交）：`<scratchpad>/preview_app.py`

**Interfaces:**
- Consumes: Task 1 的 WebP 文件名。
- Produces（后续任务依赖）：
  - CSS 变量 `--channel --surface --ink --muted --rin --apricot --leaf --blurple`。
  - 组件类：`.chat`（对话面板）、`.chat-head`（频道头）、`.msg`（一条消息）、`.av`（头像）、`.nm.rin`（小凛名字）、`.bot-tag`、`.cmd`、`.embed`（嵌入卡，`--apricot` 左边条）、`.embed.leaf`、`.scene`（场景区块）、`.scene-channel`（`# 频道名`标签）、`.stk`（贴纸容器）。
  - JS：`window.rinPickLang(stored: string|null, languages: string[]) -> 'zh'|'en'`、`window.rinSetLang(lang)`；属性文字字典 `ATTR_I18N`，键 `title`、`description`，以及 `[data-i18n-alt]` 元素的 alt。

- [ ] **Step 1: 写失败的测试**。用 `jinja2.Environment(FileSystemLoader('website/templates'))` 渲染，globals 加 `url_for=lambda endpoint, filename: '/static/' + filename`，分别渲染 `is_logged_in=False` 和 `True`。用标准库 `html.parser` 收集标签和属性。测试项：
  - `test_invite_links_exact`：所有包含 `discord.com/oauth2` 的 href 都等于常量 `INVITE`，数量 ≥ 4，每个都有 `target="_blank"`，`rel` 含 `noopener`。
  - `test_dashboard_and_github_links`：`href="/dashboard"` 至少 3 个；GitHub 和 issues 两个 URL 各至少 1 个。
  - `test_login_copy_switches`：未登录渲染结果含 `登录控制台` 和 `Dashboard login`；登录渲染结果含 `进入控制台` 和 `Open dashboard`。
  - `test_bilingual_pairs_balanced`：`data-l="zh"` 的数量等于 `data-l="en"` 的数量，且 > 20。
  - `test_prepaint_script_in_head`：`rinbot_lang` 出现在 `</head>` 之前；`<html` 标签带 `data-lang="zh"`。
  - `test_no_heavy_deps`：页面不含 `lucide`、`Noto+Sans+SC`、`rinbot_bg.jpg`。
  - `test_static_refs_exist`：每个 `/static/...` 引用在 `website/static` 下都有对应文件。
- [ ] **Step 2: 运行确认失败**：`python -m pytest tests/test_homepage.py -q`，预期新测试 FAIL。
- [ ] **Step 3: 写 head**：
  - `<html lang="zh-CN" data-lang="zh">`。
  - head 内联脚本：定义 `rinPickLang`。规则：`stored` 是 `zh` 或 `en` 就直接用；否则取 `languages[0]`，以 `zh` 开头返回 `zh`，否则返回 `en`。读 localStorage 时用 try/catch 包住。脚本最后设置 `data-lang`、`lang`（`zh-CN` 或 `en`），并给 `<html>` 加上 `js` 类。
  - CSS 规则：`html[data-lang="zh"] [data-l="en"], html[data-lang="en"] [data-l="zh"] { display:none !important }`。
  - `<meta name="description">` 写中文默认值；favicon 沿用 `rin_bot_web_icon.ico`；加载 Fredoka 字体。
- [ ] **Step 4: 写导航、首屏、页脚和语言切换**，按 spec 3.2 第 1、2、7 项：
  - 导航 sticky。600px 以下，「登录控制台」改用短文案「控制台 / Dashboard」，同样走 `data-l` 成对写法。
  - 切换按钮标签显示目标语言（中文模式显示「EN」，英文模式显示「中文」），带 `aria-label`。点击调用 `rinSetLang`：设置 `data-lang` 和 `lang`、写 localStorage（try/catch）、更新 `document.title` 和 meta description，并给所有 `[data-i18n-alt]` 元素设置 alt。
  - 首屏对话的频道头写 `# 大厅`/`# lobby`，后面跟服务器数 `<span id="stat-servers">12</span>`。`fetch('/api/stats')` 只在 `typeof servers === 'number' && servers > 0` 时更新这个数。
  - 首屏 4 条消息按 spec 写，贴纸消息用 `welcome-480.webp`。小凛头像用 `bot-avatar-96.webp`，首屏图片不加 lazy。
  - 页脚：链接、口号（`lang="en"`，不加 `data-l`）、© 2026 RinBot、Created by Milk Chocolate。
- [ ] **Step 5: 运行测试**：`python -m pytest tests/test_homepage.py -q`，预期 PASS。
- [ ] **Step 6: 在浏览器里检查**。写 `preview_app.py`：一个 Quart 应用，`template_folder` 和 `static_folder` 指向 `website/`；`/` 渲染 `index.html`，`is_logged_in` 由 `?login=1` 控制；`/api/stats` 返回 `{"servers":34}`，`?stats=fail` 时返回 500。然后用内置浏览器逐项检查：
  - 中英切换即时生效；刷新后语言保持；加载时没有闪烁。
  - 在控制台运行 `rinPickLang(null,['en-US','zh-CN'])==='en'` 和 `rinPickLang(null,['zh-TW'])==='zh'`。
  - 用 `Object.defineProperty(window,'localStorage',{get(){throw 1}})` 模拟 localStorage 不可用，再调用 `rinSetLang('en')`，不应报错。
  - 服务器数显示 34；`?stats=fail` 时显示 12。
- [ ] **Step 7: 提交**：`git add website/templates/index.html tests/test_homepage.py`，提交信息 `Homepage: bilingual skeleton with channel-style hero`。

### Task 3: 三个场景 + 收尾屏

**Files:**
- Modify: `website/templates/index.html`
- Test: `tests/test_homepage.py`

**Interfaces:**
- Consumes: Task 2 的组件类和 CSS 变量。
- Produces: 场景 id `#music`、`#welcome`、`#moderation`、`#dashboard`（页脚锚点会用到）；贴纸元素结构 `<div class="stk stk-blink"><img …-960/480 srcset><img class="lid" …-blink…></div>`、`.stk-bob`、`.stk-sway`，供 Task 4 加动画。

- [ ] **Step 1: 写失败的测试** `test_scenes_present`：页面里有 `id="music"`、`id="welcome"`、`id="moderation"`、`id="dashboard"` 四个场景；每个场景都有 `.scene-channel` 标签；`manage-blink` 和 `confused-blink` 各被引用一次。另写 `test_hidden_states_gated_by_js`：在 `<style>` 内容里，所有含 `opacity:0` 的规则选择器都以 `.js` 或 `html.js` 开头（用正则逐条检查）。
- [ ] **Step 2: 运行确认失败**。
- [ ] **Step 3: 写 `# 音乐` 场景**：
  - 对话：`/play 夜に駆ける` → 播放器嵌入卡（封面用 `images/demo/yoru-ni-kakeru.png`、进度条、队列 2 首）→ `/rank` → 等级卡（`avatar-milk.jpg`、Lv.5、1,240/1,800 XP）+ 前三名（Milk Chocolate / Starlight / GamerKun，沿用现有 demo 头像，Starlight 头像保留 `transform:scale(1.55)` 的裁切）。
  - 贴纸：`music` 放在 `.stk-bob` 里，旁边放 3 个 `.note` 音符元素。
  - 标题用 spec 3.3 的文案。
- [ ] **Step 4: 写 `# 欢迎` 场景**：
  - 对话：成员加入的系统行 → 小凛欢迎 Starlight，并说明已发放身份组「新朋友」→ 抽奖嵌入卡。嵌入卡的写法参照 `rinbot/cogs/giveaway.py:387-398`：标题「🎉 抽奖活动！」，正文依次是奖品、中奖名额、结束时间（「还剩 2 天」）、发起者，页脚「小凛抽奖系统 | 公平公正公开」，下面有按钮「🎉 参加抽奖!」和参与人数。英文版对应翻译。
  - 贴纸：`welcome` 放在 `.stk-sway` 里，旁边 2 个 `.spark`。
  - 版式与上一个场景左右交替。
- [ ] **Step 5: 写 `# 管理日志` 场景**：
  - 对话：一条被划掉的可疑链接 → 小凛「已删除一条包含链接的消息」（自动审核）→ 管理员 `/warn` → 小凛「已警告 spam_bot_9（3/3），达到阈值，禁言 10 分钟」（对应 `moderation.py` 的 `_check_warn_thresholds`）→ `#日志` 频道里 2 条记录（消息编辑、成员进出）。嵌入卡用 `.embed.leaf`。
  - 贴纸：`manage` 加闭眼帧，放在 `.stk-blink` 里。
- [ ] **Step 6: 写收尾屏 `#dashboard`**：
  - 迷你控制台示意沿用旧页面的侧栏加开关行结构，双语。
  - 标题「这些都在控制台里设」，配邀请按钮和打开控制台链接。
  - 事实行：免费 · 不需要管理员权限 · 不做完整聊天归档。
  - `confused` 加闭眼帧放在 `.stk-blink` 里，配文「还有问题？去 GitHub 问我」，链接到 issues。
  - 场景里的图片都加 `loading="lazy" decoding="async"`，写明宽高，贴纸用 `srcset="…-480.webp 480w, …-960.webp 960w"` 和合适的 `sizes`。
- [ ] **Step 7: 运行测试，预期 PASS**；在预览页面里截图检查四个场景在桌面宽度下的样子。
- [ ] **Step 8: 提交**：`Homepage: music, welcome, moderation scenes and dashboard finale`。

### Task 4: 动效与响应式收尾，完整验证

**Files:**
- Modify: `website/templates/index.html`
- Test: `tests/test_homepage.py`

**Interfaces:**
- Consumes: Task 2 的 `html.js` 类，Task 3 的 `.stk-*`、`.note`、`.spark`、`.msg` 结构。

- [ ] **Step 1: 写动效**，参数照 spec 第 5 节：
  - 首屏 `html.js .hero .msg` 依次出现：间隔 0.6s，单条 0.4s，消息位置事先占好。
  - 场景里只有最后一条消息有出现效果：IntersectionObserver `rootMargin:'200px'`，进入后加 `.seen` 类，只触发一次。
  - 眨眼：周期 4.6s，闭眼约 120ms，第二张贴纸加 `animation-delay:-2.1s` 错开节奏。
  - 点头：1.15s，±2.5°；音符：3.4s，三个依次错开。
  - 轻摇：3.2s，±1.5°；星星：2.4s。
  - 贴纸不在视口时加 `.paused`，设置 `animation-play-state: paused`。
  - `@media (prefers-reduced-motion: reduce)` 停掉以上所有动画，首屏消息直接显示。
  - 不加区块淡入，不加卡片 hover 浮起。
- [ ] **Step 2: 响应式**：
  - 960px 以下单栏（先文字后对话），贴纸缩到约 140–180px 放在标题旁边。
  - 600px 以下页面两侧留 16px，导航用短文案，嵌入卡和按钮可以换行。
  - 在 375 / 768 / 1280 三个宽度下截图检查，确认 `document.documentElement.scrollWidth <= innerWidth`，中英文都要检查。
- [ ] **Step 3: 测试** `test_reduced_motion_block_present`：样式里有 `prefers-reduced-motion: reduce` 媒体查询，而且里面引用了 `.stk-blink`、`.stk-bob`、`.stk-sway`。运行全部测试：`python -m pytest -q`，预期全部 PASS（包括另一个会话的测试）。
- [ ] **Step 4: 完整浏览器验证**，逐项对照 spec 第 8 节：
  - 快速滚到底，没有空白。
  - 所有 href 与 Global Constraints 一致。
  - `?login=1` 时文案切换正确。
  - 开启减少动态效果后没有动画（用 resize_window 或 CSS 模拟）。
  - 禁用 JS 时内容可见：用 `?nojs` 预览路由去掉所有 `<script>` 后渲染，或者手动检查。
  - 控制台无报错。
- [ ] **Step 5: 提交**：`Homepage: sticker motion, hero sequence, responsive polish`。用户确认设计之前不推送，部署时机由用户决定。
