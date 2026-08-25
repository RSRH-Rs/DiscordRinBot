<div align="center">

**English** | [中文](README.zh-CN.md)

# 小凛 RinBot

**Full-featured Discord Bot + Web Dashboard**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![License](https://img.shields.io/badge/License-MIT-E8899A)](LICENSE)
[![Website](https://img.shields.io/badge/Website-rin--bot.com-FFB7C5)](https://rin-bot.com)

A Discord bot built from scratch with music, leveling, moderation, welcome cards, reaction roles, giveaways, auto-moderation, and more — paired with a full web dashboard for browser-based server management.

[Invite RinBot](https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=8&integration_type=0&scope=bot+applications.commands) · [Dashboard](https://rin-bot.com/dashboard) · [Report Bug](https://github.com/RSRH-Rs/DiscordRinBot/issues)

</div>

---

## Features

### Bot

| Module | Description | Key Commands |
|--------|-------------|--------------|
| 🎵 **Music** | Full player — queue, loop, volume, shuffle, vote-skip, now-playing panel | `/play` `/queue` `/skip` `/loop` `/volume` |
| 🏆 **Leveling** | XP from chatting, PIL-rendered rank cards, server leaderboard | `/rank` |
| 🔨 **Moderation** | kick / ban / tempban / mute / warn / purge / lock, auto-punish thresholds, case log | `/kick` `/ban` `/warn` `/purge` `/modlog` |
| 🎀 **Welcome** | Welcome card on join + auto-role, farewell message on leave | `/welcome_setup` `/welcome_test` |
| 🏷 **Reaction Roles** | Emoji click → self-assign roles, multiple panels | `/rr_create` `/rr_add` `/rr_list` |
| 🎉 **Giveaways** | Countdown, button entry, auto-draw, reroll | `/giveaway start` `/giveaway end` |
| 🛡 **Auto-Mod** | Anti-spam, bad words, link filter, caps & repeat detection | `/automod` `/automod_words` |
| 🛠 **Utility** | Server stats, avatar viewer, dice, bot status | `/status` `/avatar` `/roll` |
| ⚙️ **Dev Tools** | Hot reload, cog management, command tree sync, eval | `/hot_update` `/sync` |

### Web Dashboard

Built with Quart + Discord OAuth2. Live at [rin-bot.com](https://rin-bot.com).

- **OAuth2 login** — auto-detects servers you have manage permission on
- **Module config panels** — welcome messages, auto-mod rules, moderation thresholds
- **Reaction role builder** — pick channel → add emoji + role pairs → send to Discord in one click
- **Giveaway creator** — prize, winner count, channel, end time picker → sends embed + button
- **Bot personalizer** — avatar, username, status, activity text with live Discord-style preview
- **Mod log viewer** — recent kick / ban / warn actions at a glance

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Bot | Python 3.10+, discord.py 2.3+, yt-dlp, Pillow, aiosqlite |
| Web | Quart, quart-discord, Jinja2, aiosqlite |
| Frontend | Vanilla HTML/CSS/JS, Lucide Icons |
| Database | SQLite — one `.db` file per module |

---

## Project Structure

```
├── rinbot/                 # Discord Bot
│   ├── main.py
│   ├── config.py
│   ├── cogs/
│   │   ├── music.py
│   │   ├── leveling.py
│   │   ├── moderation.py
│   │   ├── welcome.py
│   │   ├── reactionroles.py
│   │   ├── giveaway.py
│   │   ├── automod.py
│   │   ├── general.py
│   │   ├── dev.py
│   │   ├── help.py
│   │   └── botconfig.py
│   └── assets/
│
├── website/                # Web Dashboard
│   ├── main.py
│   ├── config.py
│   ├── routes.py
│   ├── templates/
│   └── static/
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- FFmpeg (for music)
- [Discord Bot Token](https://discord.com/developers/applications)

### 1. Clone & install

```bash
git clone https://github.com/RSRH-Rs/DiscordRinBot.git
cd DiscordRinBot
pip install -r rinbot/requirements.txt
```

### 2. Configure

Edit `rinbot/config.py`:

```python
TOKEN = "your-bot-token"
DEV_GUILD_ID = 123456789
```

### 3. Run

```bash
cd rinbot && python main.py
```

Use `/sync` in Discord to register slash commands after first launch.

### 4. Web dashboard (optional)

```bash
cd website && python main.py
```

Set your OAuth2 credentials in `website/config.py` first.

> Enable **Server Members Intent** and **Message Content Intent** in the Developer Portal.

---

## API Endpoints

All require OAuth2 login + `manage_guild` permission.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/guild/<id>/channels` | Text channel list |
| GET | `/api/guild/<id>/roles` | Role list |
| GET / POST | `/api/guild/<id>/welcome` | Welcome config |
| GET / POST | `/api/guild/<id>/automod` | Auto-mod config |
| GET / POST | `/api/guild/<id>/moderation` | Moderation config |
| POST | `/api/guild/<id>/reactionroles/send` | Send RR panel to Discord |
| POST | `/api/guild/<id>/giveaway/create` | Create giveaway |
| GET / POST | `/api/bot/personalizer` | Bot presence config |
| POST | `/api/bot/username` | Change bot username |
| POST | `/api/bot/avatar` | Change bot avatar |

---

## Contributing

1. Fork this repo
2. Create your branch (`git checkout -b feat/your-feature`)
3. Commit (`git commit -m 'feat: add something'`)
4. Push (`git push origin feat/your-feature`)
5. Open a Pull Request

---

## License

[MIT](LICENSE)

---

<div align="center">
Made with 💖 by <strong>Milk Chocolate</strong>
</div>
