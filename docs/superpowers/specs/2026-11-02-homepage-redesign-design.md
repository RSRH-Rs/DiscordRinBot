# 官网首页改版：「频道里的小凛」

日期：2026-11-02 · 路线图子项目 3 · 状态：待审阅

## 1. 目标

把 https://rin-bot.com 首页从通用 SaaS 模板改成以「小凛」为主线、中英并重的页面。读者是在考虑把 bot 拉进自己服务器的 Discord 管理员。

完成标准：

- 用户认可新设计。
- 中英可切换；首次访问按浏览器语言选默认语言；切换不刷新、不闪烁。
- 375px 手机宽度可用，没有横向滚动。
- 快速滚动不出现大片空白。
- 现有入口全部保留：邀请 bot、登录/进入控制台、中英切换、GitHub、反馈问题。
- 在本地浏览器里验证过。

## 2. 范围

改动：

- `website/templates/index.html`：整页重写，CSS 和 JS 继续内联。
- `website/static/images/rin/`：新增 WebP 版贴纸和闭眼帧，原 PNG 保留。

不改动：

- `website/routes.py`、`dashboard.html`、`server.html`、`settings.html`、`login_gate.html`、`error.html`。
- 两个 `config.py`。
- `rinbot_bg.jpg`、`rin_question_1.png`：首页不再引用，但文件保留。

## 3. 设计方向

页面本身就是一段 Discord 频道对话。每个功能都用小凛对一条真实指令或事件的回复来展示，贴纸当作 Discord 贴纸发出来。不用 eyebrow 小标签，也不用卡片网格。

**视觉第三版（2026-11-02）**：第一版被嫌背景空、单调；第二版的整幅彩色色带又太亮眼。第三版参照同类 Discord 机器人官网（MEE6、Carl-bot、Sapphire、Arcane）的布局：首屏下面先给一排功能一览，再把每个功能放进一块大圆角面板，文字和 Discord 对话窗口左右交替。

**配色第五版「雾粉」+ 宽屏侧栏（2026-11-03）**：樱花白上线后，整页几乎都是白和浅粉，亮度一样高，看着刺眼；宽屏上内容只有 1180px，两边是空白。改动：

- 底色压到中间调 `#EFE2E7`，面板改成米白渐变，只有 Discord 对话窗口保持纯白，这样页面有了「底色 < 面板 < 窗口」的明暗层次。
- 1440px 以上，左侧固定一个 Discord 客户端式的侧栏（参考 Discord 开发者门户、PostHog）：最左是服务器栏（小凛头像、邀请、控制台、GitHub，悬停有提示），旁边是频道列表 `# 大厅 # 音乐 # 欢迎 # 管理日志 # 控制台`，点了跳到对应区块，滚动时高亮当前频道；底部是小凛的状态卡，显示服务器数。顶部导航在宽屏上隐藏品牌名，内容区放宽到 1320px。
- 1440px 以下（笔记本、平板、手机）没有侧栏，保持顶部导航。

### 3.1 视觉

| 名称 | 值 | 用途 |
|---|---|---|
| bg | `#EFE2E7` | 页面底色（雾粉中间调） |
| panel / panel-line | `#FBF6F8` / `#E9D2DB` | 功能面板（向下渐变到 `#F6EBEF`）、面板边线 |
| text / muted | `#3A2433` / `#6E5565` | 正文（深梅紫）/ 次要文字 |
| rin / on-rin | `#B0335A` / `#FFFFFF` | 强调色：主按钮、小凛名字色、链接下划线 |
| chip-bg / chip-text | `#FCE4EB` / `#A3375C` | 斜杠指令小标签 |
| side-rail / side-chan / side-active / side-me | `#DCC3CD` / `#E7D4DC` / `#D9C1CB` / `#DFCAD3` | 宽屏侧栏：服务器栏、频道列表、当前频道、状态卡 |
| side-text | `#634A5A` | 侧栏文字 |
| apricot | `#FFB37A` | 音乐嵌入卡左边条、进度条 |
| dc-* | `#FFFFFF` 等 | Discord 浅色主题：对话窗口、嵌入卡、按钮 |

所有文字/底色组合满足 WCAG AA（4.5:1），由测试逐对检查。

字体：

- 英文用 Fredoka（Google Fonts，500/600/700）；中文用系统字体栈 `"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif`，不加载中文网络字体。
- 首屏标题 40–64px；场景标题 28–38px；正文 16–18px。

布局：

- 最大宽度约 1180px，文字左对齐。
- 首屏下方「我能帮你做这些」：8 条功能（音乐、等级、迎新、抽奖、自动审核、警告与处罚、服务器日志、网页控制台），做成 Discord 嵌入卡式的左色条条目，点了跳到对应场景；桌面 4 列，平板 2 列，手机 1 列。
- 每个场景是一块面板：「文字 + 斜杠指令 + 对话窗口」，桌面两栏左右交替；960px 以下单栏，先文字后对话。

### 3.2 页面结构

1. **导航**：只保留一个，`position: sticky`。内容依次是 bot 头像 +「小凛 RinBot」、中文/EN 切换、登录控制台（登录后显示「进入控制台」）、邀请小凛按钮。600px 以下，「登录控制台」缩短为「控制台」/「Dashboard」，不隐藏。
2. **首屏**：
   - 左栏：标题「把小凛拉进你的服务器」+ 一句介绍 + 邀请按钮 + 登录控制台按钮 +「已经在 N 个服务器里，免费使用」，N 来自 `/api/stats`，请求失败时显示默认值 12。
   - 右栏：大号「来啦~」贴纸从 `# 大厅` 对话窗口上沿探头。
   - 对话依次是：Milk `/play 夜に駆ける` → 小凛的播放嵌入卡 → Starlight 加入 → 小凛「欢迎 Starlight！」。
3. **# 音乐**：`/play` 播放器嵌入卡（含队列）→ `/rank` 等级卡 + 前三名排行榜（沿用 `images/demo/` 里的头像和封面）。配「听歌中♪」贴纸。
4. **# 欢迎**：新成员加入 → 欢迎消息 + 自动发放身份组 → 周五抽奖嵌入卡（奖品、剩余时间、参与人数、🎉 按钮）。配「来啦~」贴纸。
5. **# 管理日志**：可疑链接被删除 + 警告 1/3（再犯的后果）→ 日志频道里的编辑/进出记录。配「交给我!」贴纸。
6. **收尾**：
   - 迷你控制台截图（沿用现有示意：侧栏 + 开关行）+「这些都在控制台里设」+ 邀请按钮 + 打开控制台链接。
   - 一行事实：免费 · 不需要管理员权限 · 不做完整聊天归档。
   - 「诶?」贴纸 +「还有问题？去 GitHub 问我」，链接到 issues。
7. **页脚**：控制台、邀请小凛、GitHub、反馈问题；口号 "All in one, one for all."；© 与作者署名。

删掉：顶部胶囊标签、统计带、走马灯、三组卡片网格、How it works、FAQ、信任卡。

### 3.3 文案基调

小凛第一人称，口语，简短。每条对话都是 bot 真实会做的事，不编造功能。所有指令和功能描述以现有代码为准。

- 标题示例（中 / 英）：
  - 首屏：「把小凛拉进你的服务器」/「Bring Rin into your server」
  - 音乐：「叫一声，就开始放歌」/「Ask, and the music starts」
  - 欢迎：「新朋友来了，我去打招呼」/「New friend? I'll say hi」
  - 管理：「规则你定，我来执行」/「You set the rules. I follow them」
  - 收尾：「这些都在控制台里设」/「Set it all up in the dashboard」
- 英文模式下，对话、嵌入卡、按钮全部是英文；只有贴纸图里画着的中文保留，当作角色口头禅。
- 示例里的用户名、歌名、头像沿用现有 demo 素材。

## 4. 双语机制

做法：双语都写进 HTML，渲染前就选好语言，不改后端。

- 可翻译的文字写成成对的 `<span data-l="zh">…</span><span data-l="en">…</span>`。CSS 规则：`html[data-lang="zh"] [data-l="en"]{display:none}`，反过来同理。不用 `lang` 属性做开关，因为口号 "All in one, one for all." 这类在两种模式下都显示的英文，本身就该标 `lang="en"`。属性值（`alt`、`aria-label`、`<title>`、`<meta name="description">`）由 JS 字典设置，数量很少。
- `<head>` 顶部放内联脚本，在页面绘制前确定语言：先读 `localStorage.rinbot_lang`（沿用现有键）；没有记录就看首选语言 `navigator.languages[0]`（没有时用 `navigator.language`），以 `zh` 开头就选 `zh`，否则选 `en`；最后设置 `<html data-lang>` 和 `lang`。localStorage 不可用时用 try/catch 兜底。
- 没有 JS 时，模板默认 `data-lang="zh"`，中文正常显示。
- 切换按钮是 `<button>`：点击后切换 `data-lang`、写入 localStorage、更新 `lang`、`<title>` 和属性文字。按钮标签显示目标语言（中文模式显示「EN」，英文模式显示「中文」），并带上 `aria-label`。
- 登录状态：继续由 Jinja 变量 `is_logged_in` 输出「登录控制台 / 进入控制台」和「Dashboard login / Open dashboard」。

## 5. 动画

原则：内容默认可见；整页只有一处编排动画；贴纸的小动作是角色表演，不是入场特效。

- **首屏对话依次出现**：每条消息间隔约 0.6s，总长约 2s；只在首次加载播放。消息位置事先占好，不会造成布局跳动。
- **场景对话**：完整显示，不淡入。场景进入视口（IntersectionObserver，`rootMargin: 200px`）时，最后一条消息播放一次轻微的出现效果（0.3s）。没有 JS 时直接全部显示。
- **贴纸表演**：
  - 眨眼：交给我!、诶?。闭眼帧叠在原图上，每 4–5 秒切换约 120ms，两张贴纸的节奏错开。
  - 点头 + ♪ 往上飘：听歌中♪。
  - 轻摇 + 两颗星星闪烁：来啦~。
  - 贴纸不在视口内时暂停（`animation-play-state`）。
- `prefers-reduced-motion: reduce`：上面所有动画停用，首屏对话直接全部显示。
- 不做每个区块的淡入上移，不做每张卡片的 hover 浮起。

## 6. 资源与性能

- 贴纸：welcome / music / manage / confused 四张由 1254px PNG（约 800KB）生成 WebP 两档，`-480.webp` 和 `-960.webp`，用 `srcset` 按需加载。闭眼帧 `manage-blink`、`confused-blink` 同样生成两档。
- 生成方法：一次性的 Pillow 脚本 `website/tools/make_rin_assets.py`，提交进仓库，方便以后重新生成。闭眼帧用左右肤色插值抹掉眼睛，再画上眼睑弧线，人工检查效果。
- 除首屏外，图片都加 `loading="lazy"` 和 `decoding="async"`，并写明宽高，避免布局跳动。
- 移除 `unpkg.com/lucide@latest`（没锁版本，且阻塞渲染），图标改为少量内联 SVG。
- Google Fonts 只加载 Fredoka，使用 `display=swap`。

## 7. 保留的链接与行为

| 入口 | 目标 |
|---|---|
| 邀请小凛（导航、首屏、收尾、页脚） | `https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=1374694796438&integration_type=0&scope=bot+applications.commands`，`target="_blank" rel="noopener"` |
| 登录/进入控制台（导航、首屏、收尾、页脚） | `/dashboard` |
| GitHub / 反馈问题 | `https://github.com/RSRH-Rs/DiscordRinBot`、`…/issues` |
| 中英切换 | 页内按钮 |
| 服务器数 | `GET /api/stats` 返回的 `servers`，只接受正数 |

## 8. 验证

- 本地启动 `website/main.py`。如果配置挡住本地启动，就改用只渲染 `index.html` 的临时预览脚本，放在 scratchpad 里，不提交。
- 在浏览器里逐项检查：
  - 浏览器语言分别为 `zh-CN` 和 `en-US` 的首次访问默认语言；手动切换后刷新，选择能保持；加载时没有闪烁。
  - 375px 和 768px 宽度：没有横向滚动，导航上的三个入口都能点到。
  - 快速滚到底：没有空白区域。
  - 所有邀请和控制台链接的 href 与第 7 节一致。
  - `is_logged_in` 为真和为假时的文案。
  - 开启减少动态效果后，没有动画。
  - 控制台没有报错。
- 不做自动化测试。这是纯模板改动，仓库也没有前端测试框架。

## 9. 不在本次范围

- 暗色模式。
- 其他语言（日语等）。
- 仪表盘页面的双语。
- SEO 用的 hreflang / 分语言 URL（需要后端，留给路线图 2）。
- 部署：由用户决定时机，本会话不推送。
