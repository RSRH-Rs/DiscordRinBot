<div align="center">

[English](README.md) | **中文**

# 小凛 RinBot

**全功能 Discord 机器人 + Web 管理仪表盘**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![License](https://img.shields.io/badge/License-MIT-E8899A)](LICENSE)
[![Website](https://img.shields.io/badge/Website-rin--bot.com-FFB7C5)](https://rin-bot.com)

从零构建的 Discord 全能机器人，覆盖音乐、等级、管理、迎新、身份组、抽奖、自动审核等模块，并配备独立的 Web 仪表盘，让管理员在浏览器里就能完成所有配置。

[邀请小凛](https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=8&integration_type=0&scope=bot+applications.commands) · [管理面板](https://rin-bot.com/dashboard) · [问题反馈](https://github.com/RSRH-Rs/DiscordRinBot/issues)

</div>

---

## 功能总览

### 🤖 Bot 端

| 模块 | 说明 | 主要指令 |
|------|------|----------|
| 🎵 **音乐系统** | 完整播放器 — 队列、循环、音量、洗牌、投票跳过、正在播放面板 | `/play` `/queue` `/skip` `/loop` `/volume` |
| 🏆 **等级系统** | 发言自动积累经验，PIL 绘制的精美等级卡片，服务器排行榜 | `/rank` |
| 🔨 **管理模块** | kick / ban / tempban / mute / warn / purge / lock，警告阈值自动处罚，案件日志 | `/kick` `/ban` `/warn` `/purge` `/modlog` |
| 🎀 **迎新道别** | 新成员加入自动发送欢迎图卡 + 分配身份组，离开时发送道别消息 | `/welcome_setup` `/welcome_test` |
| 🏷 **反应身份组** | 点击 emoji 自助获取身份组，支持多面板 | `/rr_create` `/rr_add` `/rr_list` |
| 🎉 **抽奖管理** | 倒计时自动开奖，按钮参与，支持 reroll 重抽 | `/giveaway start` `/giveaway end` |
| 🛡 **自动审核** | 反刷屏、违禁词过滤、链接过滤、大写轰炸、重复消息检测 | `/automod` `/automod_words` |
| 🛠 **通用工具** | 服务器状态、头像查看、骰子、Bot 状态修改 | `/status` `/avatar` `/roll` |
| ⚙️ **开发者工具** | 热更新、cog 管理、指令树同步、eval 执行 | `/hot_update` `/sync` |

### 🌐 Web 仪表盘

基于 Quart + Discord OAuth2，部署在 [rin-bot.com](https://rin-bot.com)。

- **Discord OAuth2 登录** — 自动识别你有管理权限的服务器
- **模块配置面板** — 迎新消息编辑、频道选择、身份组多选、自动审核开关 / 违禁词管理
- **身份组面板构建器** — 选频道 → 添加 emoji + 角色映射 → 一键发送到 Discord
- **抽奖活动创建** — 填写奖品、人数、频道、结束时间 → 自动发送抽奖 embed
- **Bot 个性化** — 头像、用户名、在线状态、活动文字，带 Discord 风格实时预览
- **管理日志** — 查看最近的 kick / ban / warn 等操作记录

---

## 技术栈

| 层 | 技术 |
|----|------|
| Bot | Python 3.10+, discord.py 2.3+, yt-dlp, Pillow, aiosqlite |
| Web | Quart, quart-discord, Jinja2, aiosqlite |
| 前端 | 原生 HTML / CSS / JS, Lucide Icons |
| 数据库 | SQLite — 每个模块独立 `.db` 文件 |

---

## 项目结构

```
├── rinbot/                 # Discord Bot
│   ├── main.py             # 入口
│   ├── config.py           # Token 及配置
│   ├── cogs/
│   │   ├── music.py        # 音乐播放器
│   │   ├── leveling.py     # 等级系统
│   │   ├── moderation.py   # 管理模块
│   │   ├── welcome.py      # 迎新道别
│   │   ├── reactionroles.py# 反应身份组
│   │   ├── giveaway.py     # 抽奖系统
│   │   ├── automod.py      # 自动审核
│   │   ├── general.py      # 通用工具
│   │   ├── dev.py          # 开发者工具
│   │   ├── help.py         # 帮助菜单
│   │   └── botconfig.py    # Bot 个性化
│   └── assets/             # 等级卡片素材
│
├── website/                # Web 仪表盘
│   ├── main.py
│   ├── config.py
│   ├── routes.py
│   ├── templates/
│   └── static/
```

---

## 快速开始

### 前置条件

- Python 3.10 或更高版本
- FFmpeg（音乐模块需要）
- [Discord Bot Token](https://discord.com/developers/applications)

### 1. 克隆与安装

```bash
git clone https://github.com/RSRH-Rs/DiscordRinBot.git
cd DiscordRinBot
pip install -r requirements.txt
```

### 2. 填写配置

编辑 `rinbot/config.py`：

```python
TOKEN = "你的 Bot Token"
DEV_GUILD_ID = 你的测试服务器ID
```

### 3. 启动 Bot

```bash
cd rinbot && python main.py
```

首次启动后在 Discord 中使用 `/sync` 同步斜杠指令。

### 4. 启动 Web 仪表盘（可选）

```bash
cd website && python main.py
```

先在 `website/config.py` 填入 OAuth2 Client ID / Secret / Redirect URI。

> **提醒：** 需要在 Discord Developer Portal 开启 **Server Members Intent** 和 **Message Content Intent**。

---

## API 端点

所有接口需要 Discord OAuth2 登录且具有 `manage_guild` 权限。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/guild/<id>/channels` | 频道列表 |
| GET | `/api/guild/<id>/roles` | 身份组列表 |
| GET / POST | `/api/guild/<id>/welcome` | 迎新配置 |
| GET / POST | `/api/guild/<id>/automod` | 自动审核配置 |
| GET / POST | `/api/guild/<id>/moderation` | 管理模块配置 |
| POST | `/api/guild/<id>/reactionroles/send` | 发送身份组面板 |
| POST | `/api/guild/<id>/giveaway/create` | 创建抽奖活动 |
| GET / POST | `/api/bot/personalizer` | Bot 状态 / 活动 |
| POST | `/api/bot/username` | 修改用户名 |
| POST | `/api/bot/avatar` | 修改头像 |

---

## 参与贡献

欢迎提交 Issue 和 Pull Request。

1. Fork 本仓库
2. 创建你的分支 (`git checkout -b feat/your-feature`)
3. 提交更改 (`git commit -m 'feat: add something'`)
4. 推送 (`git push origin feat/your-feature`)
5. 发起 Pull Request

---

## 许可证

[MIT](LICENSE)

---

<div align="center">
Made with 💖 by <strong>Milk Chocolate</strong>
</div>