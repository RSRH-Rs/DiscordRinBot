<div align="center">

**English** | [中文](README.zh-CN.md)

# 小凛 RinBot

**Full-featured Discord Bot + Web Dashboard**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![Tests](https://img.shields.io/badge/tests-1090_passing-3FB950)](#testing)
[![License](https://img.shields.io/badge/License-MIT-E8899A)](LICENSE)
[![Website](https://img.shields.io/badge/Website-rin--bot.com-FFB7C5)](https://rin-bot.com)

A multi-server Discord bot built from scratch, with music, leveling, moderation, welcome cards, reaction roles, giveaways, auto-moderation and audit logging. It comes with a full web dashboard for managing every module from the browser, and dashboard changes reach the bot within seconds.

[Invite RinBot](https://discord.com/oauth2/authorize?client_id=1352551616427069492&permissions=1374694796438&integration_type=0&scope=bot+applications.commands) · [Dashboard](https://rin-bot.com/dashboard) · [Report Bug](https://github.com/RSRH-Rs/DiscordRinBot/issues)

</div>

---

## Features

### Bot

Commands work both as slash commands and with the `r!` prefix.

| Module | Description | Key Commands |
|--------|-------------|--------------|
| 🎵 **Music** | Full player with queue, loop, volume, shuffle, vote-skip, a now-playing panel and saved queues. DJ role and notification channel are configurable | `/play` `/queue` `/skip` `/loop` `/volume` `/playlist` |
| 🏆 **Leveling** | XP from chatting, PIL-rendered rank cards (drawn off the event loop), server leaderboard | `/rank` `/leaderboard` |
| 🔨 **Moderation** | kick / ban (members or user IDs, optional duration and message cleanup) / mute / warn / purge / slowmode / lock. Warnings can trigger automatic punishments, and every action gets a per-server case number whose reason and duration you can change | `/ban` `/warn` `/warnings` `/purge` `/case` |
| 🎀 **Welcome** | Welcome card on join (custom images allowed), auto-role, farewell message. Respects Discord membership screening. Messages and images are set on the dashboard | `/welcome setup` `/welcome test` |
| 🏷 **Reaction Roles** | Click a button to get a role. Supports multiple panels and an exclusive mode (one role per panel). Panels are sent from the dashboard and edited with `/roles` | `/roles add` `/roles remove` `/roles exclusive` |
| 🎉 **Giveaways** | Countdown, button entry, auto-draw, reroll | `/giveaway start` `/giveaway reroll` |
| 🛡 **Auto-Mod** | Anti-spam with message cleanup, bad words (sees through zero-width characters, full-width letters and separators), link and invite filter with whitelist, caps and repeat detection | `/automod status` `/automod words` `/automod whitelist` |
| 📋 **Server Log** | Forwards server events (messages, members, roles, channels…) to a log channel. Set it up on the dashboard and skip channels with `/serverlog` | `/serverlog ignore` `/serverlog unignore` |
| 🚦 **Command Toggle** | Turn any command on or off per server | `/commands disable` `/commands enable` `/commands list` |
| 🛠 **Utility** | Server stats, avatar viewer, dice, bot status and bio | `/status` `/avatar` `/roll` |
| ⚙️ **Dev Tools** | Hot reload, cog management, command tree sync | `/hot_update` `/sync` |

The bot also runs some modules in the background:

- **Bot Log** reports errors and bot events to a channel.
- **Health** publishes runtime status for the dashboard.
- **Global Settings** handles maintenance mode, the user blacklist and announcements.
- **Friendly errors** gives users a short private message and an error ID instead of a stack trace.

### Web Dashboard

Built with Quart + Discord OAuth2. Live at [rin-bot.com](https://rin-bot.com).

Public pages, in Chinese and English:

- **[Commands](https://rin-bot.com/commands).** Every slash command, searchable, with a Discord-style preview of how to fill it in and who can use it.
- **[Invite permissions](https://rin-bot.com/permissions).** What each of the 16 invite permissions is for and what stops working without it.
- **[Privacy](https://rin-bot.com/privacy) and [Terms](https://rin-bot.com/terms).**

The dashboard:

- **OAuth2 login.** Detects the servers where you have Manage Server.
- **Permission check.** The overview page compares what Rin has with what it needs and says what stops working for each missing permission.
- **Module panels.** Configure welcome (with image uploads), auto-mod, moderation thresholds, music, bot log and server log.
- **Reaction role builder.** Pick a channel, add emoji + role pairs, and send the panel to Discord in one click.
- **Giveaway creator.** Set the prize, winner count, channel and end time.
- **Command manager.** Enable or disable commands per server, one at a time or in bulk.
- **Leaderboard and mod case viewer.**
- **Owner console:**
  - Bot health
  - Maintenance mode, blacklist and global announcements
  - Server list
  - Global command switches
  - Bot personalizer (avatar, username, status, activity) with a live Discord-style preview

---

## Architecture

```
 Browser ──► website (Quart, hypercorn) ──► SQLite (one .db per module, WAL)
                       │                           ▲
                       └─ notify(module, guild) ──► sync.db change log
                                                   │
 Discord ◄──► rinbot (discord.py) ◄── ChangeWatcher polls every 3 s, reloads that module
```

- **Two processes, shared data.** The bot and the dashboard are separate processes that share SQLite files. Every database runs in WAL mode, so the dashboard writing never blocks the bot reading.
- **Change log instead of polling every table.** When the dashboard saves a setting, it appends `(module, guild_id)` to `sync.db`. The bot watches that log and reloads only the affected module for that server. Entries are pruned after 24 hours.
- **Shared core (`rinbot/rincore/`).** Pure, unit-tested helpers used by both sides: storage paths and WAL, the change log, text and link matching for auto-mod, duration parsing, per-server case numbers, exclusive-role logic and a debouncer for rate-limited edits.
- **Health heartbeat.** The bot writes `health.json`, and the dashboard reads it for the live status panel.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Bot | Python 3.11, discord.py 2.7, yt-dlp, Pillow, aiosqlite |
| Web | Quart, quart-discord, hypercorn, Jinja2, aiosqlite |
| Frontend | Vanilla HTML/CSS/JS, Lucide Icons |
| Database | SQLite, one `.db` file per module, WAL mode |
| Tests | pytest + pytest-asyncio, unittest, Node test runner |

---

## Project Structure

```
├── rinbot/                     # Discord bot
│   ├── main.py
│   ├── config.example.py       # copy to config.py
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
│   ├── rincore/                # shared, unit-tested core logic
│   ├── tools/                  # diagnostics
│   └── assets/
│
├── website/                    # Web dashboard
│   ├── main.py
│   ├── config.example.py       # copy to config.py
│   ├── routes.py
│   ├── templates/  static/
│   └── tests/                  # dashboard tests (Python + Node)
│
├── tests/                      # bot and core logic tests
└── deploy/post-receive         # git push-to-deploy hook
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg (for music)
- [Discord Bot Token](https://discord.com/developers/applications)

### 1. Clone & install

```bash
git clone https://github.com/RSRH-Rs/DiscordRinBot.git
cd DiscordRinBot
pip install -r rinbot/requirements.txt
```

### 2. Configure

```bash
cp rinbot/config.example.py rinbot/config.py
cp website/config.example.py website/config.py
```

In `rinbot/config.py`, fill in `TOKEN`, `DEV_GUILD_ID` and `OWNER_ID`. In `website/config.py`, fill in the same bot token, a `SECRET_KEY`, your OAuth2 client ID, secret and redirect URI, and optionally `CONTACT_EMAIL` (shown on the privacy page; empty points people to GitHub issues). Both files are git-ignored.

> Enable **Server Members Intent** and **Message Content Intent** in the Developer Portal.

### 3. Run the bot

```bash
cd rinbot && python main.py
```

After the first launch, run `/sync` (or `r!sync`) in Discord to register slash commands.

### 4. Run the dashboard (optional)

```bash
cd website && python -m hypercorn main:app --bind 127.0.0.1:5000
```

---

## Testing

Tests cover core logic and use temporary SQLite databases only. They never connect to Discord.

```bash
pip install -r requirements-dev.txt
python -m pytest -q                       # bot, core and website pages: 667 tests
cd website && python -m pytest -q tests   # dashboard: 209 tests
node --test tests/*.cjs                   # dashboard and site UI: 214 tests (from website/)
```

After changing a slash command, regenerate the website's command list with `python website/tools/build_commands.py`; `tests/test_command_catalog.py` fails until you do.

---

## Deployment

Production uses push-to-deploy. `git push prod master` sends the code to a bare repository on the server, and its [`post-receive`](deploy/post-receive) hook runs these steps:

1. Checks out the code into a staging directory.
2. Compiles everything and runs the full test suite.
3. Import-checks every cog and the dashboard.
4. Syncs the code into the live directories (configs, databases and uploads are left alone).
5. Installs dependencies only if `requirements.txt` changed.
6. Restarts both systemd services and prints `DEPLOY OK`.

If any step before the sync fails, the deploy stops and the running bot is untouched.

**Before going live,** register `https://rin-bot.com/invited` as a redirect URI in the Discord Developer Portal (OAuth2 → Redirects). The invite link sends new servers there after they add Rin, and Discord rejects a redirect that is not registered.

---

## API Endpoints

Every endpoint requires OAuth2 login. `/api/guild/<id>/…` endpoints also require Manage Server on that server, and `/api/bot/…` endpoints are owner-only.

| Group | Endpoints |
|-------|-----------|
| Server info | `GET /api/guild/<id>/channels` `roles` `emojis` `info` `leaderboard` |
| Module config (GET / POST) | `/api/guild/<id>/welcome` `automod` `moderation` `music` `botlog` `serverlog` |
| Permission check | `GET /api/guild/<id>/checkup` |
| Actions | `POST /api/guild/<id>/reactionroles/send` `giveaway/create` `botlog/test` `serverlog/test` |
| Records | `GET /api/guild/<id>/moderation/cases` `giveaways` `reactionroles` |
| Commands | `GET /api/guild/<id>/commands`, `POST …/commands/toggle` `…/commands/bulk-toggle` |
| Owner | `/api/bot/health` `maintenance` `blacklist` `announce` `guilds` `commands` `personalizer` `username` `avatar` |

---

## License

[MIT](LICENSE)

---

<div align="center">
Made with 💖 by <strong>Milk Chocolate</strong>
</div>
