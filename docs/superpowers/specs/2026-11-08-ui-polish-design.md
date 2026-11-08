# 文字、按钮和组件打磨

日期：2026-11-08 · 状态：设计已确认，待审阅

## 1. 目标

官网和控制台的功能已经齐全，但细节还停留在“能用”：官网和控制台各有一套按钮，按下去没有反馈，部分按钮没有悬停态，加载时几乎看不出在忙；中文标题沿用英文的行距和字距；危险操作还在用浏览器自带的 `confirm()`。

逐页实测后还发现：同一类元素之间的间距不统一，提示框会贴住下方内容；按钮文字大小不一；切换界面时内容瞬间替换，跨页时会白闪。

这一轮不改配色和页面结构，只做五件事：让中文排版讲究起来，让所有按钮手感和字号一致，加五个落在真实场景上的小组件，统一间距，给界面切换加上克制的过渡。

完成标准：

- 用户在本地试用后认可。
- 第 3 到第 8 节列出的每一项都实现，浅色、深色、375px 手机宽度下都正常。
- 开启“减少动态效果”后，第 4 到第 8 节的动画全部关闭，功能不受影响。
- `python -m pytest -q`、`cd website && python -m pytest -q tests`、`cd website && node --test tests/*.cjs` 全部通过，包括第 9 节新增的测试。
- 不自动部署，部署时机由用户决定。

## 2. 范围

**修改：**

- `website/static/css/site.css`、`console.css`、`commands.css`、`legal.css`、`permissions.css`
- `website/templates/_site_base.html`、`index.html`、`server.html`、`settings.html`
- `website/static/js/console-core.js`、`dashboard-ui.js`、`commands.js`、`message-preview.js`
- `website/static/js/modules/welcome.js`、`roles.js`、`giveaway.js`、`utility.js`
- `website/i18n/zh.json`
- 测试：见第 9 节

**不做：**

- 配色和页面结构不动。按钮只新增一个小号，其余尺寸不变。
- 官网和控制台继续各用一份样式表，不合并。两边的 `.btn` 写法不同，已有测试也分别约束两份样式表。
- 后端接口不变。
- `dashboard-ui.js:144` 的离开页面确认保留系统弹窗：它必须同步返回结果。
- 没有 `maxlength` 的输入框不加字数环。
- 已讨论并放弃：长按发送、带小凛的提示条、数字滚动、悬停扫光、渐变描边、发光阴影、磁吸按钮、滚动进场、卡片错位入场、整页左右滑动、顶部进度条。

## 3. 文字排版

三个方案里选定 B：标题用圆体，正文用系统字。A（只修细节）中英仍然不搭，C（全站思源黑体）最重且缺少个性。

### 3.1 官网字体

- `_site_base.html` 的 Google Fonts 地址加上 `ZCOOL+KuaiLe`。授权为 SIL OFL 1.1，没有保留字体名，只有 Regular 一个字重。
- `site.css` 新增 `--title: 'Fredoka', 'ZCOOL KuaiLe', var(--read);`。
- 使用 `--title` 的元素：字号不小于 24px 的官网标题，以及官网的实心按钮 `.btn:not(.btn-ghost)`。这些元素同时设 `font-synthesis: none`，防止浏览器把中文硬加粗。
- 英文排版不变：`--title` 里 Fredoka 排在最前，西文字形仍由它显示。
- `--display` 和 `--font` 的取值不变，小标题和正文不受影响。
- 控制台不加圆体。

### 3.2 中文标题

`html[data-lang="zh"]` 下，使用 `--title` 的标题改为 `line-height: 1.3; letter-spacing: .02em`。英文保持现有数值，包括 `.hero h1` 的 `1.12` 和 `-.02em`。

### 3.3 两边都做的细节

| 项目 | 做法 |
|---|---|
| 中英间距 | `html { text-autospace: normal; }`，不支持的浏览器忽略 |
| 数字 | 统计值、排行榜、计数、倒计时用 `font-variant-numeric: tabular-nums` |
| 换行 | 标题 `text-wrap: balance`，段落 `text-wrap: pretty` |
| 段落宽度 | 中文段落不超过 `34em`，已经更窄的不动 |
| 首页导语 | 中文 `.hero .lead` 行高改为 1.8 |

### 3.4 字号和字体栈

- 官网页面样式里的 `12.5px` 改为 `13px`，`19px` 改为 `18px`。`index.html` 的 `.hero .lead` 同样改为 18px。页面字号表更新为 `{13, 14, 15, 16, 18, 24, 32, 40}`。
- `console.css` 的 `.preview-notice` 模仿 Discord 的字号，已在豁免范围内，不改。
- 控制台 `--font-body` 改用和官网 `--read` 相同的顺序：西文字体在前，中文字体在后。

## 4. 按钮

尺寸、颜色和现有变体名称都不变，只补状态。

### 4.1 共同规则

| 状态 | 规则 |
|---|---|
| 过渡 | 只列具体属性：`background-color`、`color`、`box-shadow`、`transform`，150ms；禁止 `transition: all` |
| 悬停 | 全部放在 `@media (hover: hover)` 内 |
| 按下 | 填充按钮 `transform: scale(.97)`，按入 60ms，回弹 150ms ease-out；禁用和加载中不响应 |
| 触屏 | `touch-action: manipulation`，`-webkit-tap-highlight-color: transparent` |
| 图标 | 按钮以图标开头时，图标一侧的内边距减 4px |

`site.css:169` 的 `:focus-visible` 删除 `border-radius: 6px`，修复键盘聚焦时圆角突变。

### 4.2 控制台各变体

新增令牌，三处调色板（浅色、深色、跟随系统的深色）都要写：

| 令牌 | 浅色 | 深色 | 文字对比度 |
|---|---|---|---|
| `--accent-soft-hover` | `#FBDDE8` | `#4A2233` | 5.02 / 6.22（配 `--accent-text`） |
| `--bad-soft-hover` | `#FAD9D5` | `#4A1F1C` | 4.99 / 6.12（配 `--bad`） |

| 变体 | 悬停 | 按下 |
|---|---|---|
| `--primary` | `--accent-hover`（不变） | 缩放 |
| `--secondary` | `--accent-soft-hover` | 缩放 |
| `--danger` | `--bad-soft-hover` | 缩放 |
| `--discord` | 不变 | 缩放 |
| `--text` | 底色 `color-mix(in srgb, currentColor 9%, transparent)` | 底色 16%，不缩放 |
| `--icon` | 不变 | 底色加深，不缩放 |

每个变体用 `--btn-fg` 声明文字色，供加载态的 spinner 使用。

### 4.2.1 按钮只有两种字号

实测控制台的按钮有 14px/600、13px/600、13px/400 等多种组合，同一屏里大小不一。统一成两档：

| 档位 | 高度 | 字号和字重 | 圆角 | 水平内边距 | 用在 |
|---|---|---|---|---|---|
| 默认 `.btn` | 40px | 14px / 600 | 8px | 16px | 所有常规操作 |
| 小号 `.btn--sm` | 32px | 13px / 600 | 8px | 12px | 插入变量、指令分组的批量开关这类依附在内容旁的操作 |

- `.variable-tools button` 改用 `.btn btn--secondary btn--sm`，不再单独写一套样式。
- 指令分组的批量开关（`utility.js` 的 `.cmd-bulk`）改用 `.btn--text btn--sm`。
- 删除 `.server-row.is-unjoined .btn` 的 `font-size: 13px`，服务器列表的“邀请小凛”回到默认字号。

### 4.3 文字按钮

- 去掉常驻下划线。规则：带下划线的是链接，会跳到别处；不带下划线的是按钮，在当前页面操作。
- 水平内边距 8px。是一行的第一个元素时 `margin-inline-start: -8px`，是最后一个时 `margin-inline-end: -8px`，这样文字仍和上下内容对齐，悬停底色也不会贴上相邻按钮。
- 底色用 `currentColor` 混合，`.unsaved-bar` 的深色底上也能用。

### 4.4 官网按钮

`.btn`、`.btn-ghost` 使用第 4.1 节的规则。实心按钮按下时投影减弱，悬停颜色不变。

### 4.5 加载态

新增 `Console.busy(button, task)`，返回 `task` 的结果：

1. 按钮已在忙时，再次调用不执行 `task`，直接返回 `undefined`。
2. 立即设 `aria-disabled="true"`，不用 `disabled`，这样键盘焦点不丢。
3. 150ms 后设 `aria-busy="true"`。`task` 在此之前结束就不显示 spinner。
4. spinner 一旦出现，至少显示 300ms。
5. 结束后恢复属性，无论 `task` 成功还是失败。

`.btn[aria-busy="true"]` 把文字设为透明，文字仍占位，所以宽度不变；`::after` 居中画 16px 的 spinner，颜色取 `--btn-fg`。开启减少动态效果时显示静止的圆弧。

替换的调用点：`settings.html` 的 `saveProfile`、`saveUsername`、`saveAvatar`、`sendAnnounce`、`saveMaint`、`addBlacklist`；`welcome.js` 的上传和清除；`roles.js` 的发送；`giveaway.js` 的创建；未保存提示条的保存按钮。

不再把按钮文字换成“发送中”“上传中”“创建中”“保存中”。`roles.sending`、`welcome.image.uploading`、`giveaway.creating`、`bar.saving` 没有其他用处时从 `zh.json` 删除。

## 5. 新增小组件

### 5.1 确认气泡

`Console.confirm(anchor, {message, action, danger})` 返回 `Promise<boolean>`。

- 固定定位，默认在触发按钮下方右对齐，下方放不下时翻到上方，最大宽度 `calc(100vw - 32px)`。
- `role="alertdialog"`，打开时焦点落在取消按钮，Tab 在气泡内循环。
- Esc、点外部、点取消都返回 `false`，并把焦点还给触发按钮。
- 同一时间只有一个气泡，新气泡打开时旧气泡按取消处理。
- 确认按钮写清动作，不用“确定”。

| 场景 | 文案 | 确认按钮 | 样式 |
|---|---|---|---|
| `settings.html` 发公告 | 沿用现有文案 | 发送公告 | primary |
| `settings.html` 开启维护 | 沿用现有文案 | 进入维护模式 | danger |
| `settings.html` 加黑名单 | 沿用现有文案 | 加入黑名单 | danger |
| `message-preview.js` 套用示例 | 沿用现有文案 | 套用示例 | primary |
| `welcome.js` 清除图片 | 沿用现有文案 | 清除图片 | danger |

### 5.2 字数环

给 `w-title`、`gw-prize`、`bp-act-text`、`bp-username`、`ann-msg`、`maint-msg` 加 `data-limit`，页面脚本自动接管带这个属性的字段。

- 输入框外包一层 `.limit-field`，不改变字段原有宽度；环叠在字段内右侧，textarea 则在右下角。
- 字数达到 `maxlength` 的 70% 时显示 20px 的进度环和剩余字数，否则隐藏，也不占内边距。
- 到上限时环变成 `--bad`，并通过 `sr-only` 的 polite 区域播报一次。
- 监听 `input` 和 `focus`。接口回填的内容在聚焦时才计算，因为环只在输入时才有用。

### 5.3 复制按钮变身

`commands.js` 的 `.copy` 按钮复制成功后，图标在 160ms 内淡入淡出换成对勾，1.5 秒后还原。按钮文字不变，宽度不跳。成功时不再弹提示条，改为把“已复制”写进页面现有的 `#sel-status` 播报区，读屏用户仍能收到反馈；失败时仍显示现有提示条，告诉用户去 Discord 里直接输入。

### 5.4 抽奖倒计时

`giveaway.js` 把结束时刻换成剩余时间，鼠标悬停时 `title` 显示具体时刻。

| 剩余时间 | 显示 | 刷新间隔 |
|---|---|---|
| 不少于 1 天 | N 天 N 小时 | 60 秒 |
| 不少于 1 小时 | N 小时 N 分 | 60 秒 |
| 少于 1 小时 | N 分 NN 秒 | 1 秒 |
| 已到时间 | 等待开奖 | 不再刷新 |

整个列表共用一个定时器，页面隐藏或列表重新渲染时清除。文案写进 `zh.json`，数字用 `tabular-nums`。

### 5.5 小凛探头

只用在 `index.html` 的两个邀请按钮上，是这轮唯一张扬的地方。

- 用 `bot-avatar-96.webp` 以 36px 显示，`alt=""`，放在按钮背后。
- 悬停或键盘聚焦时上移，露出半个头，用 280ms 的回弹曲线 `cubic-bezier(.34, 1.56, .64, 1)`；离开时 150ms ease-out。
- 触屏设备不触发。减少动态效果时不显示。
- 图片不接收鼠标事件，不扩大按钮的点击区域。

## 6. 现有组件打磨

| 组件 | 改动 |
|---|---|
| `.seg`、`.theme-switch` | 选中底色由一个绝对定位的滑块承担，用 `:has()` 算出位置，切换时滑过去，180ms |
| `.tog` | 按住时滑块宽 20px，松手后归位 |
| `.select-popup`、`.palette`、`.switcher-pop`、`.emoji-picker` | 打开时从 `scale(.97)`、透明度 0 过渡到正常，140ms ease-out，用 `@starting-style`，不支持时直接显示 |
| 控制台 `.toast` | 鼠标悬停时暂停计时，移开后重新计时 |
| 指令大全 `.toast` | 从底部移到顶部居中，和控制台一致 |
| `.chip-remove` | 用 `::after` 把点击区扩大到至少 24px，外观不变 |
| `.search-btn kbd` | Mac 上显示 `⌘K`，其他系统保持 `Ctrl K` |
| 服务器图标、头像 | `outline: 1px solid` 半透明描边，`outline-offset: -1px`，两种主题各取一个透明度 |

## 7. 间距和对齐

逐页实测了控制台 12 个模块页、设置页 3 个面板、服务器列表、登录页、错误页，以及官网首页、指令大全、权限页、隐私页和 404 页，桌面和 375px 两种宽度。现有的 `align-audit.js` 在这两种宽度下都没有报告对齐问题，也没有横向溢出；问题集中在纵向间距。

控制台的纵向间距统一为：

| 位置 | 间距 |
|---|---|
| 页头到内容 | 24px |
| 分节到分节，包括标签页内的分节 | 32px |
| 分节标题到下方内容 | 8px |
| 通知条到下方内容 | 16px |
| 列表到操作按钮 | 16px |
| 操作按钮到下方的文字区 | 24px |

对应的修正：

| 页面 | 实测 | 改为 | 根因 |
|---|---|---|---|
| 指令管理：提示框到搜索框 | 0 | 16 | `.note` 只有上边距 |
| 全局管理：提示框到“全局公告” | 0 | 16 | 同上 |
| 抽奖记录、等级榜、最近管理记录：标题到内容 | 0 | 8 | `.section-title + .list` 没有覆盖这些列表 |
| 领取身份组：“1. 面板内文”到内容 | 12 | 8 | `.section-head` 的下边距 |
| 自动审核：分节之间 | 16 | 32 | `.tab-panel` 的 `gap: 16px` |
| 全局管理：发送按钮到“最近发送” | 8 | 24 | 缺少规则 |

官网首页 Discord 消息模拟区的间距照搬 Discord，不在修正范围内。

## 8. 界面过渡

原则：只响应用户操作；只做入场，旧内容立刻消失；只动 `transform` 和 `opacity`；高频操作不超过 200ms；键盘发起的跳转不播放动画。

两份样式表新增令牌：`--ease-out: cubic-bezier(.22, 1, .36, 1)`，`--dur-fast: 120ms`，`--dur-base: 160ms`，`--dur-slow: 200ms`。

| 场景 | 现在 | 改为 |
|---|---|---|
| 控制台切换模块（`show()`） | 瞬间替换 | 内容淡入并上移 4px，`--dur-base`；首次打开和 `Ctrl K` 面板跳转不播放 |
| 标签页（`selectTab()`） | 瞬切，下划线跳动 | 下划线滑到新位置 180ms，面板淡入 `--dur-fast`，不位移 |
| 数据加载完成 | 骨架屏瞬变成内容 | 内容淡入 `--dur-fast`；骨架屏延迟 150ms 才出现，快请求不闪 |
| `.fold` 折叠区 | 瞬开瞬合 | 用 `::details-content` 和 `interpolate-size` 过渡高度，`--dur-slow`；不支持时瞬开 |
| 依赖开关带动的子行 | 透明度瞬变 | `opacity` 过渡 150ms |
| 新增的行和标签 | 瞬间出现 | 用 `@starting-style` 淡入 140ms；删除不播放 |
| 抽屉、未保存提示条 | `.2s ease` | 曲线换成 `--ease-out` |
| 跨页跳转（官网各页、服务器列表进入服务器） | 白闪 | `@view-transition { navigation: auto; }` 根元素淡入淡出 180ms；官网 `.nav`、控制台 `.sidebar` 用 `view-transition-name` 保持静止 |

实现约束：

- `.page` 的入场动画不设 `fill-mode`，结束后不留 `transform`，页面内 `position: fixed` 的弹层定位不受影响。
- 骨架屏的延迟只作用在显示上：`aria-busy` 和表单隐藏仍立即生效，未加载的默认值不会露出来。
- 减少动态效果时同时关闭 `::view-transition-*`，并设 `@view-transition { navigation: none; }`。

## 9. 测试

**更新：**

- `test_console_contrast.py`：`PAIRS` 加上 `('accent-text', 'accent-soft-hover')` 和 `('bad', 'bad-soft-hover')`。
- `test_site_css.py`：`PAGE_SIZES` 改为第 3.4 节的集合。
- 断言了旧行为的用例：文字按钮下划线、按钮文字切换、系统 `confirm()`。

**新增：**

- `Console.busy`：重复调用被忽略；150ms 内结束不显示 spinner；spinner 至少显示 300ms；`task` 抛错时属性也会恢复。
- `Console.confirm`：确认和取消的返回值；Esc 和点外部返回 `false`；打开第二个时第一个按取消处理；焦点归还。
- 字数环：70% 的显示阈值、到上限变色、到上限只播报一次。
- 倒计时：四档格式和边界值。
- 样式表：不出现 `transition: all`；`--title` 的元素带 `font-synthesis: none`；`:active` 排除禁用和加载中；第 5.1 节的五处不再调用 `confirm(`；按钮字号只有 `.btn` 和 `.btn--sm` 两档；减少动态效果时关闭 `::view-transition-*`。
- 把这次的间距测量整理成 `website/tests/browser/spacing-audit.js`，按第 7 节的表检查，用法和 `align-audit.js` 相同。

**人工验证：** 在浅色、深色、375px 下截图，中文和英文各看一遍官网，逐项按第 10 节检查。深色主题、`/terms`、无服务器时的列表，以及标签页内子页的间距，这次实测没有覆盖，实现时一并检查。

## 10. 验收要点

- 中文首页标题的字体是站酷快乐体，没有被浏览器加粗；缺字时退回系统字体，没有方块。
- 英文首页和这轮改动前看起来一样，只有按钮手感变了。
- 加载时按钮宽度不跳，快请求不闪 spinner。
- 确认气泡能完全用键盘操作，靠近窗口底部时会翻到上方。
- 小凛探头不被首页其他元素裁切，头像露出的高度自然。
- 连续快速点击侧栏时，页面不抖动、不积压动画，弹层定位正确。
- 跨页跳转时官网导航栏和控制台侧栏保持不动，没有白闪。

## 11. 风险

| 风险 | 处理 |
|---|---|
| 中国大陆访问 Google Fonts 不稳定 | 和现有 Fredoka 相同，`display=swap`，失败时退回系统字体 |
| `text-autospace`、`@starting-style`、`::details-content`、跨文档 View Transitions 支持不完整 | 都是渐进增强，不支持时只是少了效果 |
| 去掉下划线后文字按钮不够显眼 | 颜色仍是 `--accent-text`，试用后再判断 |
| 站酷快乐体在按钮的小字号下观感 | 实现后看截图，不合适就只保留标题 |
