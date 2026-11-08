<div align="center">

[English](README.md) | **中文**

# 小凛 RinBot

**全功能 Discord 机器人 + Web 管理仪表盘**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![Tests](https://img.shields.io/badge/tests-992_passing-3FB950)](#测试)
[![License](https://img.shields.io/badge/License-MIT-E8899A)](LICENSE)
[![Website](https://img.shields.io/badge/Website-rin--bot.com-FFB7C5)](https://rin-bot.com)

从零构建的多服务器 Discord 机器人，覆盖音乐、等级、管理、迎新、身份组、抽奖、自动审核、审计日志等模块。配套的 Web 仪表盘让管理员在浏览器里就能配置所有模块，保存后几秒内同步到 Bot。

[邀请小凛](https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=1374694796438&integration_type=0&scope=bot+applications.commands) · [管理面板](https://rin-bot.com/dashboard) · [问题反馈](https://github.com/RSRH-Rs/DiscordRinBot/issues)

</div>

---

## 功能总览

### 🤖 Bot 端

指令同时支持斜杠指令和 `r!` 前缀。

| 模块 | 说明 | 主要指令 |
|------|------|----------|
| 🎵 **音乐系统** | 完整播放器：队列、循环、音量、洗牌、投票跳过、正在播放面板、保存歌单。可设置 DJ 身份组和通知频道 | `/play` `/queue` `/skip` `/loop` `/volume` `/playlist` |
| 🏆 **等级系统** | 发言积累经验，PIL 绘制等级卡片（在事件循环外渲染，不卡 Bot），服务器排行榜 | `/rank` `/leaderboard` |
| 🔨 **管理模块** | kick / ban（支持成员或用户 ID，可选时长和删除消息）/ mute / warn / purge / slowmode / lock。警告达到阈值可自动处罚，每条处罚都有按服务器编号的案件号，可以改原因和时长 | `/ban` `/warn` `/warnings` `/purge` `/case` |
| 🎀 **迎新道别** | 新成员加入发送欢迎图卡（支持自定义图片）并自动分配身份组，离开时发送道别消息。会等待成员通过 Discord 的入群审核。消息和图片在控制台里设置 | `/welcome setup` `/welcome test` |
| 🏷 **领取身份组** | 点按钮自助领取身份组，支持多面板和单选模式（每个面板只能选一个）。面板在控制台里发，发出后用 `/roles` 修改 | `/roles add` `/roles remove` `/roles exclusive` |
| 🎉 **抽奖管理** | 倒计时自动开奖，按钮参与，支持重抽 | `/giveaway start` `/giveaway reroll` |
| 🛡 **自动审核** | 反刷屏（自动清理刷屏消息）、违禁词过滤（识别零宽字符、全角字母和分隔符绕过）、链接和邀请过滤（支持白名单）、大写轰炸、重复消息检测 | `/automod status` `/automod words` `/automod whitelist` |
| 📋 **服务器日志** | 把服务器事件（消息、成员、身份组、频道等）转发到日志频道。在控制台里设置，用 `/serverlog` 设置跳过的频道 | `/serverlog ignore` `/serverlog unignore` |
| 🚦 **指令开关** | 按服务器启用或禁用任意指令 | `/commands disable` `/commands enable` `/commands list` |
| 🛠 **通用工具** | 服务器状态、头像查看、骰子、Bot 状态和简介修改 | `/status` `/avatar` `/roll` |
| ⚙️ **开发者工具** | 热更新、cog 管理、指令树同步 | `/hot_update` `/sync` |

另外有几个模块在后台运行：

- **系统日志**：把错误和 Bot 事件发送到指定频道。
- **健康状态**：给仪表盘提供实时运行状态。
- **全局设置**：维护模式、用户黑名单和全局公告。
- **友好报错**：给用户发一条简短的私密提示和错误编号，而不是一大段报错。

### 🌐 Web 仪表盘

基于 Quart + Discord OAuth2，部署在 [rin-bot.com](https://rin-bot.com)。

官网页面（中英双语）：

- **[指令大全](https://rin-bot.com/commands)**：全部斜杠指令，可以搜索，用 Discord 输入框的样子说明怎么填、谁能用。
- **[邀请权限](https://rin-bot.com/permissions)**：邀请时要的 16 项权限各用来做什么，取消后哪些功能会受影响。
- **[隐私政策](https://rin-bot.com/privacy)和[服务条款](https://rin-bot.com/terms)**。

控制台：

- **OAuth2 登录**：自动识别你拥有"管理服务器"权限的服务器。
- **权限体检**：概览页对比小凛现有的权限和需要的权限，逐条说明缺哪项会少哪些功能。
- **模块配置面板**：迎新（支持上传图片）、自动审核、管理阈值、音乐、系统日志、服务器日志。
- **反应身份组编辑器**：选频道，添加 emoji 和身份组，一键发送到 Discord。
- **抽奖创建**：设置奖品、中奖人数、频道和结束时间。
- **指令管理**：按服务器启用或禁用指令，支持批量操作。
- **排行榜和处罚记录查看**。
- **Bot 主人控制台**：
  - 健康状态
  - 维护模式、黑名单和全局公告
  - 服务器列表
  - 全局指令开关
  - Bot 个性化（头像、名字、状态、活动），带 Discord 风格实时预览

---

## 架构

```
 浏览器 ──► website（Quart, hypercorn）──► SQLite（每个模块一个 .db，WAL 模式）
                      │                              ▲
                      └─ notify(模块, 服务器) ──► sync.db 变更日志
                                                     │
 Discord ◄──► rinbot（discord.py）◄── ChangeWatcher 每 3 秒检查，只重载对应模块
```

- **两个进程，共享数据**：Bot 和仪表盘是两个独立进程，共用 SQLite 文件。所有数据库都开了 WAL 模式，仪表盘写入时不会阻塞 Bot 读取。
- **用变更日志代替轮询每张表**：仪表盘保存设置时往 `sync.db` 追加一条 `(模块, 服务器 ID)`，Bot 监听这份日志，只重载受影响服务器的那个模块。记录保留 24 小时后自动清理。
- **公共核心（`rinbot/rincore/`）**：两端共用、带单元测试的纯逻辑，包括数据库路径和 WAL、变更日志、自动审核的文本和链接匹配、时长解析、按服务器编号的案件号、单选身份组逻辑，以及用于限速编辑的防抖器。
- **健康心跳**：Bot 定时写 `health.json`，仪表盘读取后显示实时状态。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| Bot | Python 3.11、discord.py 2.7、yt-dlp、Pillow、aiosqlite |
| Web | Quart、quart-discord、hypercorn、Jinja2、aiosqlite |
| 前端 | 原生 HTML/CSS/JS、Lucide Icons |
| 数据库 | SQLite，每个模块一个 `.db` 文件，WAL 模式 |
| 测试 | pytest + pytest-asyncio、unittest、Node 测试运行器 |

---

## 项目结构

```
├── rinbot/                     # Discord Bot
│   ├── main.py
│   ├── config.example.py       # 复制为 config.py
│   ├── requirements.txt
│   ├── cogs/
│   │   ├── music.py  musicconfig.py
│   │   ├── leveling.py
│   │   ├── moderation.py
│   │   ├── welcome.py
│   │   ├── reactionroles.py
│   │   ├── giveaway.py
│   │   ├── automod.py
│   │   ├── serverlog.py  botlog.py
│   │   ├── commandtoggle.py  globalsettings.py
│   │   ├── botconfig.py  health.py  errors.py
│   │   └── general.py  help.py  dev.py
│   ├── rincore/                # 公共核心逻辑（带单元测试）
│   ├── tools/                  # 诊断工具
│   └── assets/
│
├── website/                    # Web 仪表盘
│   ├── main.py
│   ├── config.example.py       # 复制为 config.py
│   ├── routes.py
│   ├── templates/  static/
│   └── tests/                  # 仪表盘测试（Python + Node）
│
├── tests/                      # Bot 与核心逻辑测试
└── deploy/post-receive         # git 推送即部署的钩子
```

---

## 快速开始

### 环境要求

- Python 3.11+
- FFmpeg（音乐功能需要）
- [Discord Bot Token](https://discord.com/developers/applications)

### 1. 克隆并安装依赖

```bash
git clone https://github.com/RSRH-Rs/DiscordRinBot.git
cd DiscordRinBot
pip install -r rinbot/requirements.txt
```

### 2. 配置

```bash
cp rinbot/config.example.py rinbot/config.py
cp website/config.example.py website/config.py
```

在 `rinbot/config.py` 里填写 `TOKEN`、`DEV_GUILD_ID` 和 `OWNER_ID`；在 `website/config.py` 里填写同一个 Bot Token、`SECRET_KEY`、OAuth2 的 Client ID、Secret 和回调地址，还可以填 `CONTACT_EMAIL`（显示在隐私政策里；留空就改为指向 GitHub issues）。这两个文件已被 git 忽略。

> 记得在 Developer Portal 中开启 **Server Members Intent** 和 **Message Content Intent**。

### 3. 启动 Bot

```bash
cd rinbot && python main.py
```

首次启动后，在 Discord 里运行 `/sync`（或 `r!sync`）注册斜杠指令。

### 4. 启动仪表盘（可选）

```bash
cd website && python -m hypercorn main:app --bind 127.0.0.1:5000
```

---

## 测试

测试只覆盖核心逻辑，使用临时 SQLite 数据库，不连接 Discord。

```bash
pip install -r requirements-dev.txt
python -m pytest -q                       # Bot、核心逻辑和官网页面：634 个测试
cd website && python -m pytest -q tests   # 仪表盘：185 个测试
node --test tests/*.cjs                   # 仪表盘和官网界面：173 个测试（在 website/ 下运行）
```

改了斜杠指令以后，运行 `python website/tools/build_commands.py` 重新生成官网的指令清单；不重新生成，`tests/test_command_catalog.py` 会失败。

---

## 部署

生产环境采用推送即部署：`git push prod master` 会把代码推到服务器上的裸仓库，由 [`post-receive`](deploy/post-receive) 钩子依次完成：

1. 把代码检出到临时目录。
2. 编译检查并运行全部测试。
3. 逐个导入所有 cog 和仪表盘，确认能正常加载。
4. 同步到线上目录（配置、数据库和上传文件不会被改动）。
5. 只有 `requirements.txt` 变了才重新安装依赖。
6. 重启两个 systemd 服务，并输出 `DEPLOY OK`。

同步之前任何一步失败都会中止部署，正在运行的 Bot 不受影响。

**上线前**，先在 Discord 开发者后台（OAuth2 → Redirects）登记 `https://rin-bot.com/invited`。邀请链接会在新服务器添加小凛后跳到这个地址，没有登记的话 Discord 会拒绝跳转。

---

## API 接口

所有接口都需要 OAuth2 登录。`/api/guild/<id>/…` 还要求你在该服务器拥有"管理服务器"权限，`/api/bot/…` 仅限 Bot 主人。

| 分类 | 接口 |
|------|------|
| 服务器信息 | `GET /api/guild/<id>/channels` `roles` `emojis` `info` `leaderboard` |
| 模块配置（GET / POST） | `/api/guild/<id>/welcome` `automod` `moderation` `music` `botlog` `serverlog` |
| 权限体检 | `GET /api/guild/<id>/checkup` |
| 操作 | `POST /api/guild/<id>/reactionroles/send` `giveaway/create` `botlog/test` `serverlog/test` |
| 记录 | `GET /api/guild/<id>/moderation/cases` `giveaways` `reactionroles` |
| 指令 | `GET /api/guild/<id>/commands`，`POST …/commands/toggle` `…/commands/bulk-toggle` |
| Bot 主人 | `/api/bot/health` `maintenance` `blacklist` `announce` `guilds` `commands` `personalizer` `username` `avatar` |

---

## 许可证

[MIT](LICENSE)

---

<div align="center">
Made with 💖 by <strong>Milk Chocolate</strong>
</div>
