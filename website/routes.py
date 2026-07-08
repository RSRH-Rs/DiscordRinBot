from quart import redirect, url_for, render_template, session, jsonify, request
import asyncio
import time
import traceback
import aiohttp
import aiosqlite
import json
import os
from typing import Optional
from datetime import datetime, timezone
from config import BOT_TOKEN

try:
    from config import OWNER_ID
except ImportError:
    OWNER_ID = 0

# Shared aiohttp session — created at app startup, closed at shutdown
_session: Optional[aiohttp.ClientSession] = None

# Username cache: uid -> (name, expiry_ts). 1-hour TTL.
_username_cache: dict[str, tuple[str, float]] = {}
_USERNAME_TTL = 3600

# 首页统计缓存（公开接口，避免频繁打 Discord API）
_stats_cache: dict = {"data": None, "exp": 0.0}
_STATS_TTL = 120


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def _fetch_username(uid: str) -> str:
    """Resolve a Discord user ID to display name, with TTL cache."""
    now = time.time()
    cached = _username_cache.get(uid)
    if cached and cached[1] > now:
        return cached[0]
    udata = await discord_api_get(f"/users/{uid}")
    name = uid
    if udata:
        name = udata.get("global_name") or udata.get("username") or uid
    _username_cache[uid] = (name, now + _USERNAME_TTL)
    return name


# ── 关键：数据库在 rinbot 目录，网站在 website 目录 ──
# 相对路径: website/ → ../rinbot/
BOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rinbot")

DB_WELCOME = os.path.join(BOT_DIR, "welcome.db")
DB_AUTOMOD = os.path.join(BOT_DIR, "automod.db")
DB_MODERATION = os.path.join(BOT_DIR, "moderation.db")
DB_GIVEAWAY = os.path.join(BOT_DIR, "giveaway.db")
DB_LEVELING = os.path.join(BOT_DIR, "leveling.db")
DB_BOTCONFIG = os.path.join(BOT_DIR, "botconfig.db")
DB_RR = os.path.join(BOT_DIR, "reactionroles.db")
DB_CMDTOGGLE = os.path.join(BOT_DIR, "commandtoggle.db")
DB_MUSIC = os.path.join(BOT_DIR, "musicconfig.db")
DB_BOTLOG = os.path.join(BOT_DIR, "botlog.db")
DB_SERVERLOG = os.path.join(BOT_DIR, "serverlog.db")
DB_GLOBAL = os.path.join(BOT_DIR, "globalsettings.db")


async def ensure_tables():
    """Bot 可能还没跑过，先建好所有表"""
    try:
        async with aiosqlite.connect(DB_WELCOME) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS welcome_config (
                guild_id INTEGER PRIMARY KEY, welcome_channel INTEGER DEFAULT 0,
                farewell_channel INTEGER DEFAULT 0, auto_roles TEXT DEFAULT '',
                welcome_msg TEXT DEFAULT '欢迎 {member} 加入 {server}！🎉',
                farewell_msg TEXT DEFAULT '{member} 离开了我们... 👋',
                show_card INTEGER DEFAULT 0, welcome_title TEXT DEFAULT '',
                author_icon TEXT DEFAULT '', thumbnail_url TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1, image_url TEXT DEFAULT '')""")
            for ddl in (
                "show_card INTEGER DEFAULT 0",
                "welcome_title TEXT DEFAULT ''",
                "author_icon TEXT DEFAULT ''",
                "thumbnail_url TEXT DEFAULT ''",
                "enabled INTEGER DEFAULT 1",
                "image_url TEXT DEFAULT ''",
            ):
                try:
                    await db.execute(f"ALTER TABLE welcome_config ADD COLUMN {ddl}")
                except Exception:
                    pass
            await db.commit()
        async with aiosqlite.connect(DB_AUTOMOD) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS automod_config (
                guild_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 1,
                log_channel INTEGER DEFAULT 0, anti_spam INTEGER DEFAULT 1,
                spam_threshold INTEGER DEFAULT 5, spam_interval INTEGER DEFAULT 5,
                anti_badword INTEGER DEFAULT 1, badwords TEXT DEFAULT '[]',
                anti_link INTEGER DEFAULT 0, link_whitelist TEXT DEFAULT '[]',
                anti_caps INTEGER DEFAULT 1, caps_threshold INTEGER DEFAULT 70,
                caps_min_length INTEGER DEFAULT 10, anti_repeat INTEGER DEFAULT 1,
                repeat_threshold INTEGER DEFAULT 3, mute_duration INTEGER DEFAULT 300,
                ignored_channels TEXT DEFAULT '[]', ignored_roles TEXT DEFAULT '[]')""")
            await db.commit()
        async with aiosqlite.connect(DB_MODERATION) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS mod_config (
                guild_id INTEGER PRIMARY KEY, log_channel INTEGER DEFAULT 0,
                warn_kick_threshold INTEGER DEFAULT 0, warn_ban_threshold INTEGER DEFAULT 0,
                warn_mute_threshold INTEGER DEFAULT 3, warn_mute_duration INTEGER DEFAULT 600)"""
            )
            await db.execute("""CREATE TABLE IF NOT EXISTS mod_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                action TEXT NOT NULL, user_id INTEGER NOT NULL, mod_id INTEGER NOT NULL,
                reason TEXT DEFAULT '未提供原因', duration TEXT DEFAULT '',
                created_at REAL NOT NULL)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, mod_id INTEGER NOT NULL,
                reason TEXT DEFAULT '未提供原因', created_at REAL NOT NULL)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS tempbans (
                guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                unban_at REAL NOT NULL, PRIMARY KEY (guild_id, user_id))""")
            await db.commit()
        async with aiosqlite.connect(DB_GIVEAWAY) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL, message_id INTEGER DEFAULT 0,
                host_id INTEGER NOT NULL, prize TEXT NOT NULL,
                winners_count INTEGER DEFAULT 1, end_time REAL NOT NULL,
                ended INTEGER DEFAULT 0)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS giveaway_entries (
                giveaway_id INTEGER, user_id INTEGER,
                PRIMARY KEY (giveaway_id, user_id))""")
            await db.commit()
        async with aiosqlite.connect(DB_LEVELING) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER, user_id INTEGER,
                xp INTEGER DEFAULT 0, level INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id))""")
            await db.commit()
        async with aiosqlite.connect(DB_BOTCONFIG) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS bot_personalizer (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                bot_status TEXT DEFAULT 'online',
                activity_type TEXT DEFAULT 'watching',
                activity_text TEXT DEFAULT '正在偷看你的聊天记录|rin-bot.com',
                updated_at REAL DEFAULT 0)""")
            await db.execute("INSERT OR IGNORE INTO bot_personalizer (id) VALUES (1)")
            await db.commit()
        async with aiosqlite.connect(DB_RR) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS rr_panels (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                title TEXT DEFAULT '身份组选择',
                mappings TEXT DEFAULT '{}',
                exclusive INTEGER DEFAULT 0)""")
            try:
                await db.execute(
                    "ALTER TABLE rr_panels ADD COLUMN exclusive INTEGER DEFAULT 0"
                )
            except Exception:
                pass
            await db.commit()
        async with aiosqlite.connect(DB_CMDTOGGLE) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS disabled_commands (
                guild_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                PRIMARY KEY (guild_id, command_name))""")
            await db.commit()
        async with aiosqlite.connect(DB_MUSIC) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS music_config (
                guild_id INTEGER PRIMARY KEY,
                dj_role INTEGER DEFAULT 0,
                notify_channel INTEGER DEFAULT 0)""")
            await db.commit()
        async with aiosqlite.connect(DB_BOTLOG) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS botlog_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                levels TEXT DEFAULT 'error,warning,info,config')""")
            await db.commit()
        async with aiosqlite.connect(DB_SERVERLOG) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS serverlog_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                categories TEXT DEFAULT '',
                ignored_channels TEXT DEFAULT '')""")
            await db.commit()
        async with aiosqlite.connect(DB_GLOBAL) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS global_flags (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT '')""")
            await db.execute("""CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER PRIMARY KEY,
                reason TEXT DEFAULT '',
                added_at REAL DEFAULT 0)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                sent_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                created_at REAL DEFAULT 0,
                done_at REAL DEFAULT 0)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS global_disabled_cmds (
                name TEXT PRIMARY KEY)""")
            await db.commit()
        print(f"✅ Dashboard DB 就绪 (路径: {BOT_DIR})")
    except Exception as e:
        print(f"❌ ensure_tables: {e}")


def has_manage_permission(guild) -> bool:
    try:
        if getattr(guild, "owner", False):
            return True
        perms = getattr(guild, "permissions", None)
        if perms is None:
            return False
        if hasattr(perms, "administrator") and perms.administrator:
            return True
        if hasattr(perms, "manage_guild") and perms.manage_guild:
            return True
        if isinstance(perms, int):
            return bool(perms & 0x8 or perms & 0x20)
        return False
    except Exception:
        return False


async def fetch_bot_guild_ids() -> set:
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    try:
        s = await _get_session()
        async with s.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                return {int(g["id"]) for g in await resp.json()}
    except Exception as e:
        print(f"[fetch_bot_guild_ids] {e}")
    return set()


async def discord_api_get(path):
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    try:
        s = await _get_session()
        async with s.get(
            f"https://discord.com/api/v10{path}",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            print(f"[Discord API] {path} → {resp.status}")
    except Exception as e:
        print(f"[Discord API] {path}: {e}")
    return None


async def discord_api_post(path, json_data):
    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    s = await _get_session()
    async with s.post(
        f"https://discord.com/api/v10{path}",
        headers=headers,
        json=json_data,
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        body = await resp.json()
        if resp.status in (200, 201):
            return body
        raise Exception(body.get("message", f"Discord API {resp.status}"))


async def discord_api_put(path):
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    s = await _get_session()
    async with s.put(
        f"https://discord.com/api/v10{path}",
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=5),
    ) as resp:
        return resp.status == 204


async def discord_api_delete(path):
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    s = await _get_session()
    async with s.delete(
        f"https://discord.com/api/v10{path}",
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=8),
    ) as resp:
        return resp.status in (200, 204)


# 等级配色和 emoji,跟 cogs/botlog.py 对齐
_AUDIT_LEVEL_META = {
    "error": {"emoji": "❌", "color": 0xE24B4A, "label": "错误"},
    "warning": {"emoji": "⚠️", "color": 0xEF9F27, "label": "警告"},
    "info": {"emoji": "ℹ️", "color": 0x85B7EB, "label": "信息"},
    "config": {"emoji": "⚙️", "color": 0x5A9E6F, "label": "配置变更"},
}


async def _botlog_send(
    guild_id: int, level: str, title: str, desc: str = "", actor: str = "", **fields
):
    """从 Web 进程发送日志到 botlog 频道(通过 Discord REST)"""
    try:
        async with aiosqlite.connect(DB_BOTLOG) as db:
            cur = await db.execute(
                "SELECT channel_id, enabled, levels FROM botlog_config WHERE guild_id=?",
                (guild_id,),
            )
            row = await cur.fetchone()
        if not row or not row[0] or not row[1]:
            return
        allowed_levels = set((row[2] or "").split(","))
        if level not in allowed_levels:
            return

        meta = _AUDIT_LEVEL_META.get(level, _AUDIT_LEVEL_META["info"])
        embed_fields = [
            {"name": k, "value": str(v)[:1000], "inline": True}
            for k, v in fields.items()
            if v not in (None, "")
        ]
        if actor:
            embed_fields.insert(0, {"name": "操作者", "value": actor, "inline": True})

        embed = {
            "title": f"{meta['emoji']} {title}",
            "color": meta["color"],
            "author": {"name": f"系统日志 · {meta['label']}"},
            "footer": {"text": f"网页控制台 · Guild ID: {guild_id}"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if desc:
            embed["description"] = desc[:4000]
        if embed_fields:
            embed["fields"] = embed_fields[:25]

        session = await _get_session()
        async with session.post(
            f"https://discord.com/api/v10/channels/{row[0]}/messages",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            json={"embeds": [embed]},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                print(f"[_botlog_send] Discord {resp.status}: {body[:200]}")
    except Exception as e:
        print(f"[_botlog_send] {e}")


def audit(gid, title, **fields):
    """配置变更便捷调用,自动 fire-and-forget"""
    asyncio.create_task(_botlog_send(int(gid), "config", title, **fields))


async def _resolve_actor(discord_oauth) -> str:
    """从当前 OAuth session 拿登录用户的显示名"""
    try:
        if await discord_oauth.authorized:
            u = await discord_oauth.fetch_user()
            return f"{u.name}"
    except Exception:
        pass
    return "未知"


async def discord_api_patch(path, json_data):
    """PATCH helper used by bot username/avatar endpoints. Returns (status, body)."""
    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    s = await _get_session()
    async with s.patch(
        f"https://discord.com/api/v10{path}",
        headers=headers,
        json=json_data,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        return resp.status, await resp.json()


async def is_owner(discord_oauth) -> bool:
    """当前登录用户是否为 bot 主人（config.OWNER_ID）"""
    try:
        if not OWNER_ID or not await discord_oauth.authorized:
            return False
        u = await discord_oauth.fetch_user()
        return int(u.id) == int(OWNER_ID)
    except Exception:
        return False


async def check_guild_access(discord_oauth, gid_str):
    try:
        if not await discord_oauth.authorized:
            return False
        guilds = await discord_oauth.fetch_guilds()
        gid = int(gid_str)
        g = next((g for g in guilds if int(g.id) == gid), None)
        return g is not None and has_manage_permission(g)
    except Exception as e:
        print(f"[check_guild_access] {e}")
        return False


def setup_routes(app, discord):

    @app.before_serving
    async def startup():
        await ensure_tables()
        await _get_session()  # warm up shared aiohttp session

    @app.after_serving
    async def shutdown():
        global _session
        if _session and not _session.closed:
            await _session.close()
            _session = None

    # ═══════ Page routes ═══════

    @app.route("/")
    async def index():
        bot_info = {
            "name": "小凛 RinBot",
            "status": "Online",
            "server_count": 12,
            "description": "全能型音乐/娱乐/管理机器人",
        }
        try:
            is_logged_in = await discord.authorized
        except Exception:
            is_logged_in = False
        return await render_template(
            "index.html", bot=bot_info, is_logged_in=is_logged_in
        )

    @app.route("/login")
    async def login():
        session.clear()
        session.permanent = True
        return await discord.create_session(scope=["identify", "guilds"])

    @app.route("/callback")
    async def callback():
        try:
            await discord.callback()
        except Exception as e:
            session.clear()
            return await render_template("error.html", error=str(e)), 400
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    async def dashboard():
        try:
            if not await discord.authorized:
                return await render_template("login_gate.html")
            user = await discord.fetch_user()
            all_guilds = await discord.fetch_guilds()
            bot_guild_ids = await fetch_bot_guild_ids()
            manageable = []
            for g in all_guilds:
                if has_manage_permission(g):
                    g.bot_joined = int(g.id) in bot_guild_ids
                    manageable.append(g)
            return await render_template(
                "dashboard.html",
                user=user,
                guilds=manageable,
                is_owner=await is_owner(discord),
            )
        except Exception as e:
            return await render_template("error.html", error=str(e)), 500

    @app.route("/dashboard/settings")
    async def global_settings():
        try:
            if not await discord.authorized:
                return await render_template("login_gate.html")
            if not await is_owner(discord):
                return (
                    await render_template(
                        "error.html", error="此页面仅限机器人主人访问"
                    ),
                    403,
                )
            user = await discord.fetch_user()
            return await render_template("settings.html", user=user)
        except Exception as e:
            return await render_template("error.html", error=str(e)), 500

    @app.route("/dashboard/server/<int:guild_id>")
    async def server_settings(guild_id):
        try:
            if not await discord.authorized:
                return await render_template("login_gate.html")
            user = await discord.fetch_user()
            all_guilds = await discord.fetch_guilds()
            current = next((g for g in all_guilds if int(g.id) == guild_id), None)
            if not current:
                return (
                    await render_template(
                        "error.html", error="找不到该服务器或无权访问"
                    ),
                    404,
                )
            return await render_template("server.html", user=user, guild=current)
        except Exception as e:
            return await render_template("error.html", error=str(e)), 500

    @app.route("/logout")
    async def logout():
        try:
            discord.revoke()
        except Exception:
            pass
        session.clear()
        return redirect(url_for("index"))

    # ═══════════════════════════════════
    #  API — 全部用 <string:gid> 避免大数溢出
    # ═══════════════════════════════════

    @app.route("/api/guild/<string:gid>/channels")
    async def api_channels(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            data = await discord_api_get(f"/guilds/{gid}/channels")
            if not data:
                return jsonify([])
            ch = sorted(
                [
                    {"id": str(c["id"]), "name": c["name"]}
                    for c in data
                    if c.get("type") == 0
                ],
                key=lambda c: c["name"],
            )
            return jsonify(ch)
        except Exception as e:
            print(f"[api_channels] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/roles")
    async def api_roles(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            data = await discord_api_get(f"/guilds/{gid}/roles")
            if not data:
                return jsonify([])
            roles = sorted(
                [
                    {"id": str(r["id"]), "name": r["name"], "color": r.get("color", 0)}
                    for r in data
                    if r["name"] != "@everyone"
                ],
                key=lambda r: r["name"],
            )
            return jsonify(roles)
        except Exception as e:
            print(f"[api_roles] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/emojis")
    async def api_emojis(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            data = await discord_api_get(f"/guilds/{gid}/emojis")
            if not data:
                return jsonify([])
            emojis = [
                {
                    "id": str(e["id"]),
                    "name": e["name"],
                    "animated": bool(e.get("animated")),
                    "url": f"https://cdn.discordapp.com/emojis/{e['id']}.{'gif' if e.get('animated') else 'png'}",
                }
                for e in data
                if e.get("id") and e.get("name")
            ]
            emojis.sort(key=lambda e: e["name"].lower())
            return jsonify(emojis)
        except Exception as e:
            print(f"[api_emojis] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/info")
    async def api_guild_info(gid):
        """服务器统计:成员数、在线数、频道数、bot 加入时间"""
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401

            guild_data = await discord_api_get(f"/guilds/{gid}?with_counts=true")
            channels = await discord_api_get(f"/guilds/{gid}/channels")
            me = await discord_api_get(
                f"/guilds/{gid}/members/{app.config.get('DISCORD_CLIENT_ID', 0)}"
            )

            if not guild_data:
                return jsonify({"error": "无法获取服务器信息"}), 502

            text_ch = sum(1 for c in (channels or []) if c.get("type") in (0, 5))
            voice_ch = sum(1 for c in (channels or []) if c.get("type") in (2, 13))

            return jsonify(
                {
                    "name": guild_data.get("name", ""),
                    "member_count": guild_data.get("approximate_member_count", 0),
                    "online_count": guild_data.get("approximate_presence_count", 0),
                    "text_channels": text_ch,
                    "voice_channels": voice_ch,
                    "boost_tier": guild_data.get("premium_tier", 0),
                    "boost_count": guild_data.get("premium_subscription_count", 0),
                    "bot_joined_at": me.get("joined_at") if me else None,
                }
            )
        except Exception as e:
            print(f"[api_guild_info] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── 模块列表 ──

    MODULES = [
        {
            "slug": "music",
            "name": "音乐系统",
            "desc": "完整播放器：队列、循环、音量、投票跳过",
            "icon": "music",
            "db": "musicconfig.db",
        },
        {
            "slug": "welcome",
            "name": "欢迎新成员",
            "desc": "欢迎图卡、自动身份组、道别消息",
            "icon": "smile-plus",
            "db": "welcome.db",
        },
        {
            "slug": "roles",
            "name": "领取身份组",
            "desc": "成员点击 emoji 自助获取身份组",
            "icon": "tags",
            "db": "reactionroles.db",
        },
        {
            "slug": "automod",
            "name": "自动审核",
            "desc": "反刷屏、违禁词、链接过滤、大写轰炸",
            "icon": "shield-check",
            "db": "automod.db",
        },
        {
            "slug": "moderation",
            "name": "管理模块",
            "desc": "kick / ban / mute / warn / purge + 自动处罚",
            "icon": "gavel",
            "db": "moderation.db",
        },
        {
            "slug": "giveaway",
            "name": "抽奖管理",
            "desc": "倒计时自动开奖，公平透明",
            "icon": "gift",
            "db": "giveaway.db",
        },
        {
            "slug": "leveling",
            "name": "等级系统",
            "desc": "曲线式经验算法，精美等级卡片",
            "icon": "trophy",
            "db": "leveling.db",
        },
        {
            "slug": "utility",
            "name": "指令管理",
            "desc": "按需启用/禁用每个指令",
            "icon": "sliders-horizontal",
            "db": "commandtoggle.db",
        },
        {
            "slug": "botlog",
            "name": "系统日志",
            "desc": "将 bot 内部活动转发到指定频道",
            "icon": "scroll-text",
            "db": "botlog.db",
        },
        {
            "slug": "serverlog",
            "name": "审计日志",
            "desc": "记录消息/成员/频道/身份组/封禁等服务器事件",
            "icon": "history",
            "db": "serverlog.db",
        },
        {
            "slug": "general",
            "name": "通用工具",
            "desc": "status / avatar / roll 等实用指令",
            "icon": "wrench",
            "db": None,
        },
    ]

    @app.route("/api/modules")
    async def api_modules():
        result = []
        for m in MODULES:
            if m["db"] is None:
                loaded = True
            else:
                loaded = os.path.exists(os.path.join(BOT_DIR, m["db"]))
            result.append(
                {k: v for k, v in m.items() if k != "db"} | {"loaded": loaded}
            )
        return jsonify(result)

    @app.route("/api/stats")
    async def api_stats():
        """首页公开统计：服务器数、功能模块数（带 120s 缓存）"""
        now = time.time()
        if _stats_cache["data"] and _stats_cache["exp"] > now:
            return jsonify(_stats_cache["data"])
        try:
            guild_ids = await fetch_bot_guild_ids()
            servers = len(guild_ids)
        except Exception:
            servers = 0
        # 统计可展示的功能模块（排除“通用工具”这类无独立 db 的）
        modules = len([m for m in MODULES if m["slug"] != "general"])
        data = {"servers": servers, "modules": modules}
        _stats_cache["data"] = data
        _stats_cache["exp"] = now + _STATS_TTL
        return jsonify(data)

    # ── Welcome ──

    @app.route("/api/guild/<string:gid>/welcome", methods=["GET"])
    async def api_welcome_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_WELCOME) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT * FROM welcome_config WHERE guild_id=?", (g,)
                )
                row = await cur.fetchone()
            if row:
                return jsonify(dict(row))
            return jsonify(
                {
                    "guild_id": g,
                    "welcome_channel": 0,
                    "farewell_channel": 0,
                    "auto_roles": "",
                    "welcome_msg": "欢迎 {member} 加入 {server}！🎉",
                    "farewell_msg": "{member} 离开了我们... 👋",
                    "show_card": 0,
                    "welcome_title": "",
                    "author_icon": "",
                    "thumbnail_url": "",
                    "enabled": 1,
                    "image_url": "",
                }
            )
        except Exception as e:
            print(f"[api_welcome_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/welcome", methods=["POST"])
    async def api_welcome_post(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            g = int(gid)
            async with aiosqlite.connect(DB_WELCOME) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO welcome_config (guild_id) VALUES (?)", (g,)
                )
                await db.execute(
                    """UPDATE welcome_config SET
                    welcome_channel=?, farewell_channel=?, auto_roles=?,
                    welcome_msg=?, farewell_msg=?,
                    show_card=?, welcome_title=?, author_icon=?, thumbnail_url=?,
                    enabled=?, image_url=?
                    WHERE guild_id=?""",
                    (
                        int(d.get("welcome_channel", 0)),
                        int(d.get("farewell_channel", 0)),
                        d.get("auto_roles", ""),
                        d.get("welcome_msg", ""),
                        d.get("farewell_msg", ""),
                        1 if d.get("show_card") else 0,
                        (d.get("welcome_title") or "")[:200],
                        (d.get("author_icon") or "").strip(),
                        (d.get("thumbnail_url") or "").strip(),
                        1 if d.get("enabled", True) else 0,
                        (d.get("image_url") or "").strip(),
                        g,
                    ),
                )
                await db.commit()
            actor = await _resolve_actor(discord)
            audit(g, "欢迎模块配置已更新", **{"操作者": actor})
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_welcome_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── AutoMod ──

    @app.route("/api/guild/<string:gid>/automod", methods=["GET"])
    async def api_automod_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_AUTOMOD) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT * FROM automod_config WHERE guild_id=?", (g,)
                )
                row = await cur.fetchone()
            if row:
                d = dict(row)
                for k in (
                    "badwords",
                    "link_whitelist",
                    "ignored_channels",
                    "ignored_roles",
                ):
                    try:
                        d[k] = json.loads(d.get(k, "[]"))
                    except Exception:
                        d[k] = []
                return jsonify(d)
            return jsonify(
                {
                    "guild_id": g,
                    "enabled": 0,
                    "log_channel": 0,
                    "anti_spam": 1,
                    "spam_threshold": 5,
                    "spam_interval": 5,
                    "anti_badword": 1,
                    "badwords": [],
                    "anti_link": 0,
                    "link_whitelist": [],
                    "anti_caps": 1,
                    "caps_threshold": 70,
                    "caps_min_length": 10,
                    "anti_repeat": 1,
                    "repeat_threshold": 3,
                    "mute_duration": 300,
                    "ignored_channels": [],
                    "ignored_roles": [],
                }
            )
        except Exception as e:
            print(f"[api_automod_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/automod", methods=["POST"])
    async def api_automod_post(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            g = int(gid)
            async with aiosqlite.connect(DB_AUTOMOD) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (g,)
                )
                await db.execute(
                    """UPDATE automod_config SET
                    enabled=?, log_channel=?, anti_spam=?, spam_threshold=?, spam_interval=?,
                    anti_badword=?, badwords=?, anti_link=?, link_whitelist=?,
                    anti_caps=?, caps_threshold=?, anti_repeat=?, repeat_threshold=?,
                    mute_duration=?, ignored_channels=?, ignored_roles=?
                    WHERE guild_id=?""",
                    (
                        int(d.get("enabled", 1)),
                        int(d.get("log_channel", 0)),
                        int(d.get("anti_spam", 1)),
                        int(d.get("spam_threshold", 5)),
                        int(d.get("spam_interval", 5)),
                        int(d.get("anti_badword", 1)),
                        json.dumps(d.get("badwords", []), ensure_ascii=False),
                        int(d.get("anti_link", 0)),
                        json.dumps(d.get("link_whitelist", []), ensure_ascii=False),
                        int(d.get("anti_caps", 1)),
                        int(d.get("caps_threshold", 70)),
                        int(d.get("anti_repeat", 1)),
                        int(d.get("repeat_threshold", 3)),
                        int(d.get("mute_duration", 300)),
                        json.dumps(d.get("ignored_channels", []), ensure_ascii=False),
                        json.dumps(d.get("ignored_roles", []), ensure_ascii=False),
                        g,
                    ),
                )
                await db.commit()
            actor = await _resolve_actor(discord)
            audit(g, "自动审核配置已更新", **{"操作者": actor})
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_automod_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── Moderation ──

    @app.route("/api/guild/<string:gid>/moderation", methods=["GET"])
    async def api_moderation_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_MODERATION) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT * FROM mod_config WHERE guild_id=?", (g,)
                )
                row = await cur.fetchone()
            if row:
                return jsonify(dict(row))
            return jsonify(
                {
                    "guild_id": g,
                    "log_channel": 0,
                    "warn_kick_threshold": 0,
                    "warn_ban_threshold": 0,
                    "warn_mute_threshold": 3,
                    "warn_mute_duration": 600,
                }
            )
        except Exception as e:
            print(f"[api_moderation_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/moderation", methods=["POST"])
    async def api_moderation_post(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            g = int(gid)
            async with aiosqlite.connect(DB_MODERATION) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO mod_config (guild_id) VALUES (?)", (g,)
                )
                await db.execute(
                    """UPDATE mod_config SET
                    log_channel=?, warn_mute_threshold=?, warn_kick_threshold=?,
                    warn_ban_threshold=?, warn_mute_duration=? WHERE guild_id=?""",
                    (
                        int(d.get("log_channel", 0)),
                        int(d.get("warn_mute_threshold", 3)),
                        int(d.get("warn_kick_threshold", 0)),
                        int(d.get("warn_ban_threshold", 0)),
                        int(d.get("warn_mute_duration", 600)),
                        g,
                    ),
                )
                await db.commit()
            actor = await _resolve_actor(discord)
            audit(g, "管理模块配置已更新", **{"操作者": actor})
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_moderation_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/moderation/cases")
    async def api_mod_cases(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_MODERATION) as db:
                cur = await db.execute(
                    "SELECT id,action,user_id,mod_id,reason,duration,created_at "
                    "FROM mod_cases WHERE guild_id=? ORDER BY created_at DESC LIMIT 20",
                    (g,),
                )
                rows = await cur.fetchall()

            # Batch resolve unique user IDs concurrently
            all_ids = list({str(r[2]) for r in rows} | {str(r[3]) for r in rows})
            names = await asyncio.gather(
                *[_fetch_username(uid) for uid in all_ids], return_exceptions=True
            )
            name_cache = {
                uid: (n if isinstance(n, str) else uid)
                for uid, n in zip(all_ids, names)
            }

            return jsonify(
                [
                    {
                        "id": r[0],
                        "action": r[1],
                        "user_id": str(r[2]),
                        "user_name": name_cache.get(str(r[2]), str(r[2])),
                        "mod_id": str(r[3]),
                        "mod_name": name_cache.get(str(r[3]), str(r[3])),
                        "reason": r[4],
                        "duration": r[5],
                        "created_at": r[6],
                    }
                    for r in rows
                ]
            )
        except Exception as e:
            print(f"[api_mod_cases] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── Giveaway ──

    @app.route("/api/guild/<string:gid>/giveaways")
    async def api_giveaways(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_GIVEAWAY) as db:
                cur = await db.execute(
                    "SELECT id,prize,winners_count,end_time,ended "
                    "FROM giveaways WHERE guild_id=? ORDER BY end_time DESC LIMIT 10",
                    (g,),
                )
                rows = await cur.fetchall()
            return jsonify(
                [
                    {
                        "id": r[0],
                        "prize": r[1],
                        "winners_count": r[2],
                        "end_time": r[3],
                        "ended": bool(r[4]),
                    }
                    for r in rows
                ]
            )
        except Exception as e:
            print(f"[api_giveaways] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── Music config ──

    @app.route("/api/guild/<string:gid>/music", methods=["GET"])
    async def api_music_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_MUSIC) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT * FROM music_config WHERE guild_id=?", (g,)
                )
                row = await cur.fetchone()
            if row:
                return jsonify(dict(row))
            return jsonify({"guild_id": g, "dj_role": 0, "notify_channel": 0})
        except Exception as e:
            print(f"[api_music_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/music", methods=["POST"])
    async def api_music_post(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            g = int(gid)
            async with aiosqlite.connect(DB_MUSIC) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO music_config (guild_id, dj_role, notify_channel) VALUES (?, ?, ?)",
                    (g, int(d.get("dj_role", 0)), int(d.get("notify_channel", 0))),
                )
                await db.commit()
            actor = await _resolve_actor(discord)
            audit(g, "音乐模块配置已更新", **{"操作者": actor})
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_music_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── Bot Log ──

    @app.route("/api/guild/<string:gid>/botlog", methods=["GET"])
    async def api_botlog_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_BOTLOG) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT * FROM botlog_config WHERE guild_id=?", (g,)
                )
                row = await cur.fetchone()
            if row:
                d = dict(row)
                d["channel_id"] = str(d["channel_id"])
                d["guild_id"] = str(d["guild_id"])
                d["levels"] = d["levels"].split(",") if d["levels"] else []
                d["enabled"] = bool(d["enabled"])
                return jsonify(d)
            return jsonify(
                {
                    "guild_id": str(g),
                    "channel_id": "0",
                    "enabled": True,
                    "levels": ["error", "warning", "info", "config"],
                }
            )
        except Exception as e:
            print(f"[api_botlog_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/botlog", methods=["POST"])
    async def api_botlog_post(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            g = int(gid)
            valid_levels = {"error", "warning", "info", "config"}
            levels = [l for l in (d.get("levels") or []) if l in valid_levels]
            async with aiosqlite.connect(DB_BOTLOG) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO botlog_config (guild_id, channel_id, enabled, levels) VALUES (?, ?, ?, ?)",
                    (
                        g,
                        int(d.get("channel_id", 0)),
                        int(bool(d.get("enabled", True))),
                        ",".join(levels),
                    ),
                )
                await db.commit()
            actor = await _resolve_actor(discord)
            audit(
                g,
                "系统日志配置已更新",
                **{"操作者": actor, "等级": ",".join(levels) or "(无)"},
            )
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_botlog_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/botlog/test", methods=["POST"])
    async def api_botlog_test(gid):
        """通过 Discord REST 直接发测试消息(不依赖 bot 进程)"""
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_BOTLOG) as db:
                cur = await db.execute(
                    "SELECT channel_id, enabled FROM botlog_config WHERE guild_id=?",
                    (g,),
                )
                row = await cur.fetchone()
            if not row or not row[0]:
                return jsonify({"error": "未配置日志频道,请先选择并保存"}), 400
            if not row[1]:
                return jsonify({"error": "日志系统已禁用"}), 400
            if not BOT_TOKEN:
                return jsonify({"error": "BOT_TOKEN 未配置"}), 500

            embed = {
                "title": "ℹ️ 测试消息",
                "description": "如果你看到这条消息,说明系统日志频道配置正确!",
                "color": 0x85B7EB,
                "footer": {"text": f"由网页控制台触发 · Guild ID: {g}"},
            }
            session = await _get_session()
            async with session.post(
                f"https://discord.com/api/v10/channels/{row[0]}/messages",
                headers={"Authorization": f"Bot {BOT_TOKEN}"},
                json={"embeds": [embed]},
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    print(f"[api_botlog_test] Discord {resp.status}: {body}")
                    err_map = {
                        401: "Bot Token 无效",
                        403: "Bot 在该频道没有「发送消息」权限",
                        404: "找不到该频道(可能已被删除)",
                    }
                    msg = err_map.get(resp.status, f"Discord API 错误 ({resp.status})")
                    return jsonify({"error": msg}), 400
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_botlog_test] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── Server Log (审计日志) ──

    SERVERLOG_CATS = {
        "message",
        "member",
        "member_update",
        "ban",
        "channel",
        "role",
        "voice",
        "server",
    }
    SERVERLOG_DEFAULT = ["message", "member", "ban", "channel", "role", "server"]

    @app.route("/api/guild/<string:gid>/serverlog", methods=["GET"])
    async def api_serverlog_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_SERVERLOG) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    "SELECT * FROM serverlog_config WHERE guild_id=?", (g,)
                )
                row = await cur.fetchone()
            if row:
                d = dict(row)
                d["guild_id"] = str(d["guild_id"])
                d["channel_id"] = str(d["channel_id"])
                d["enabled"] = bool(d["enabled"])
                d["categories"] = d["categories"].split(",") if d["categories"] else []
                d["ignored_channels"] = (
                    d["ignored_channels"].split(",") if d["ignored_channels"] else []
                )
                return jsonify(d)
            return jsonify(
                {
                    "guild_id": str(g),
                    "channel_id": "0",
                    "enabled": True,
                    "categories": SERVERLOG_DEFAULT,
                    "ignored_channels": [],
                }
            )
        except Exception as e:
            print(f"[api_serverlog_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/serverlog", methods=["POST"])
    async def api_serverlog_post(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            g = int(gid)
            cats = [c for c in (d.get("categories") or []) if c in SERVERLOG_CATS]
            # 用 UPSERT 只更新这三列，保留 slash 指令设的忽略频道
            async with aiosqlite.connect(DB_SERVERLOG) as db:
                await db.execute(
                    "INSERT INTO serverlog_config (guild_id, channel_id, enabled, categories) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET "
                    "channel_id=excluded.channel_id, enabled=excluded.enabled, categories=excluded.categories",
                    (
                        g,
                        int(d.get("channel_id", 0)),
                        int(bool(d.get("enabled", True))),
                        ",".join(cats),
                    ),
                )
                await db.commit()
            actor = await _resolve_actor(discord)
            audit(
                g,
                "审计日志配置已更新",
                **{"操作者": actor, "分类": ",".join(cats) or "(无)"},
            )
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_serverlog_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/serverlog/test", methods=["POST"])
    async def api_serverlog_test(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_SERVERLOG) as db:
                cur = await db.execute(
                    "SELECT channel_id, enabled FROM serverlog_config WHERE guild_id=?",
                    (g,),
                )
                row = await cur.fetchone()
            if not row or not row[0]:
                return jsonify({"error": "未配置日志频道,请先选择并保存"}), 400
            if not row[1]:
                return jsonify({"error": "审计日志已禁用"}), 400
            if not BOT_TOKEN:
                return jsonify({"error": "BOT_TOKEN 未配置"}), 500

            embed = {
                "title": "🗃️ 测试消息",
                "description": "如果你看到这条消息,说明审计日志频道配置正确!",
                "color": 0x5A9E6F,
                "footer": {"text": f"由网页控制台触发 · Guild ID: {g}"},
            }
            session = await _get_session()
            async with session.post(
                f"https://discord.com/api/v10/channels/{row[0]}/messages",
                headers={"Authorization": f"Bot {BOT_TOKEN}"},
                json={"embeds": [embed]},
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    print(f"[api_serverlog_test] Discord {resp.status}: {body}")
                    err_map = {
                        401: "Bot Token 无效",
                        403: "Bot 在该频道没有「发送消息」权限",
                        404: "找不到该频道(可能已被删除)",
                    }
                    msg = err_map.get(resp.status, f"Discord API 错误 ({resp.status})")
                    return jsonify({"error": msg}), 400
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_serverlog_test] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── Leaderboard ──

    @app.route("/api/guild/<string:gid>/leaderboard")
    async def api_leaderboard(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_LEVELING) as db:
                cur = await db.execute(
                    "SELECT user_id,xp,level FROM users "
                    "WHERE guild_id=? ORDER BY xp DESC LIMIT 15",
                    (g,),
                )
                rows = await cur.fetchall()

            # Fetch usernames concurrently (TTL-cached)
            uids = [str(r[0]) for r in rows]
            names = await asyncio.gather(
                *[_fetch_username(uid) for uid in uids], return_exceptions=True
            )
            result = [
                {
                    "user_id": uid,
                    "username": (n if isinstance(n, str) else None) or f"用户 {uid}",
                    "xp": r[1],
                    "level": r[2],
                }
                for r, uid, n in zip(rows, uids, names)
            ]
            return jsonify(result)
        except Exception as e:
            print(f"[api_leaderboard] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ═══════ Bot Personalizer ═══════

    @app.route("/api/bot/health")
    async def api_bot_health():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        path = os.path.join(BOT_DIR, "health.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["online"] = (time.time() - data.get("updated_at", 0)) < 90
            return jsonify(data)
        except FileNotFoundError:
            return jsonify(
                {
                    "online": False,
                    "error": "暂无健康数据（bot 未运行，或未加载 health 模块）",
                }
            )
        except Exception as e:
            return jsonify({"online": False, "error": str(e)})

    # ── 全局：维护模式 / 黑名单 / 公告（owner-only）──

    @app.route("/api/bot/maintenance", methods=["GET"])
    async def api_maint_get():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        async with aiosqlite.connect(DB_GLOBAL) as db:
            cur = await db.execute(
                "SELECT key, value FROM global_flags WHERE key IN ('maintenance','maintenance_msg')"
            )
            rows = dict(await cur.fetchall())
        return jsonify(
            {
                "maintenance": rows.get("maintenance") == "1",
                "message": rows.get("maintenance_msg", ""),
            }
        )

    @app.route("/api/bot/maintenance", methods=["POST"])
    async def api_maint_post():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        d = await request.get_json()
        on = "1" if d.get("maintenance") else "0"
        msg = (d.get("message") or "")[:300]
        async with aiosqlite.connect(DB_GLOBAL) as db:
            await db.execute(
                "INSERT OR REPLACE INTO global_flags (key, value) VALUES ('maintenance', ?)",
                (on,),
            )
            await db.execute(
                "INSERT OR REPLACE INTO global_flags (key, value) VALUES ('maintenance_msg', ?)",
                (msg,),
            )
            await db.commit()
        return jsonify({"ok": True})

    @app.route("/api/bot/blacklist", methods=["GET"])
    async def api_bl_get():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        async with aiosqlite.connect(DB_GLOBAL) as db:
            cur = await db.execute(
                "SELECT user_id, reason, added_at FROM blacklist ORDER BY added_at DESC"
            )
            rows = await cur.fetchall()
        return jsonify(
            [{"user_id": str(r[0]), "reason": r[1], "added_at": r[2]} for r in rows]
        )

    @app.route("/api/bot/blacklist", methods=["POST"])
    async def api_bl_add():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        d = await request.get_json()
        try:
            uid = int(str(d.get("user_id", "")).strip())
        except ValueError:
            return jsonify({"error": "用户 ID 必须是数字"}), 400
        if OWNER_ID and uid == int(OWNER_ID):
            return jsonify({"error": "不能把自己加入黑名单"}), 400
        async with aiosqlite.connect(DB_GLOBAL) as db:
            await db.execute(
                "INSERT OR REPLACE INTO blacklist (user_id, reason, added_at) VALUES (?, ?, ?)",
                (uid, (d.get("reason") or "")[:200], time.time()),
            )
            await db.commit()
        return jsonify({"ok": True})

    @app.route("/api/bot/blacklist/remove", methods=["POST"])
    async def api_bl_remove():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        d = await request.get_json()
        try:
            uid = int(str(d.get("user_id", "")).strip())
        except ValueError:
            return jsonify({"error": "无效 ID"}), 400
        async with aiosqlite.connect(DB_GLOBAL) as db:
            await db.execute("DELETE FROM blacklist WHERE user_id=?", (uid,))
            await db.commit()
        return jsonify({"ok": True})

    @app.route("/api/bot/announce", methods=["POST"])
    async def api_announce():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        d = await request.get_json()
        msg = (d.get("message") or "").strip()
        if not msg:
            return jsonify({"error": "公告内容不能为空"}), 400
        if len(msg) > 1800:
            return jsonify({"error": "公告过长（最多 1800 字）"}), 400
        async with aiosqlite.connect(DB_GLOBAL) as db:
            await db.execute(
                "INSERT INTO broadcasts (message, status, created_at) VALUES (?, 'pending', ?)",
                (msg, time.time()),
            )
            await db.commit()
        return jsonify({"ok": True})

    @app.route("/api/bot/announce/recent")
    async def api_announce_recent():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        async with aiosqlite.connect(DB_GLOBAL) as db:
            cur = await db.execute(
                "SELECT message, status, sent_count, total_count, created_at "
                "FROM broadcasts ORDER BY id DESC LIMIT 5"
            )
            rows = await cur.fetchall()
        return jsonify(
            [
                {
                    "message": r[0],
                    "status": r[1],
                    "sent": r[2],
                    "total": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
        )

    @app.route("/api/bot/guilds")
    async def api_bot_guilds():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        data = await discord_api_get("/users/@me/guilds?with_counts=true")
        if data is None:
            return jsonify({"error": "无法获取服务器列表"}), 502
        out = [
            {
                "id": str(g["id"]),
                "name": g.get("name", ""),
                "icon": g.get("icon"),
                "members": g.get("approximate_member_count"),
            }
            for g in data
        ]
        out.sort(key=lambda x: (x["members"] or 0), reverse=True)
        return jsonify(out)

    @app.route("/api/bot/guilds/leave", methods=["POST"])
    async def api_bot_guild_leave():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        d = await request.get_json()
        gid = str(d.get("guild_id", "")).strip()
        if not gid.isdigit():
            return jsonify({"error": "无效的服务器 ID"}), 400
        ok = await discord_api_delete(f"/users/@me/guilds/{gid}")
        if not ok:
            return jsonify({"error": "退出失败（可能已不在该服务器）"}), 502
        return jsonify({"ok": True})

    @app.route("/api/bot/commands")
    async def api_bot_commands():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        cmds = []
        try:
            with open(os.path.join(BOT_DIR, "health.json"), encoding="utf-8") as f:
                cmds = json.load(f).get("commands", [])
        except Exception:
            pass
        async with aiosqlite.connect(DB_GLOBAL) as db:
            cur = await db.execute("SELECT name FROM global_disabled_cmds")
            disabled = [r[0] for r in await cur.fetchall()]
        return jsonify({"commands": cmds, "disabled": disabled})

    @app.route("/api/bot/commands/toggle", methods=["POST"])
    async def api_bot_command_toggle():
        if not await is_owner(discord):
            return jsonify({"error": "unauthorized"}), 401
        d = await request.get_json()
        name = (d.get("name") or "").strip()
        if not name:
            return jsonify({"error": "缺少指令名"}), 400
        async with aiosqlite.connect(DB_GLOBAL) as db:
            if d.get("disabled"):
                await db.execute(
                    "INSERT OR IGNORE INTO global_disabled_cmds (name) VALUES (?)",
                    (name,),
                )
            else:
                await db.execute(
                    "DELETE FROM global_disabled_cmds WHERE name=?", (name,)
                )
            await db.commit()
        return jsonify({"ok": True})

    @app.route("/api/bot/personalizer", methods=["GET"])
    async def api_bot_cfg_get():
        try:
            if not await is_owner(discord):
                return jsonify({"error": "unauthorized"}), 401
            async with aiosqlite.connect(DB_BOTCONFIG) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("SELECT * FROM bot_personalizer WHERE id=1")
                row = await cur.fetchone()
            if row:
                return jsonify(dict(row))
            return jsonify(
                {
                    "bot_status": "online",
                    "activity_type": "watching",
                    "activity_text": "正在偷看你的聊天记录|rin-bot.com",
                }
            )
        except Exception as e:
            print(f"[api_bot_cfg_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bot/personalizer", methods=["POST"])
    async def api_bot_cfg_post():
        try:
            if not await is_owner(discord):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            async with aiosqlite.connect(DB_BOTCONFIG) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO bot_personalizer (id) VALUES (1)"
                )
                await db.execute(
                    """UPDATE bot_personalizer SET
                    bot_status=?, activity_type=?, activity_text=?, updated_at=?
                    WHERE id=1""",
                    (
                        d.get("bot_status", "online"),
                        d.get("activity_type", "watching"),
                        d.get("activity_text", ""),
                        time.time(),
                    ),
                )
                await db.commit()
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_bot_cfg_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bot/username", methods=["POST"])
    async def api_bot_username():
        """Change bot username via Discord REST API (rate limited: 2/hour)"""
        try:
            if not await is_owner(discord):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            name = d.get("username", "").strip()
            if not name or len(name) < 2 or len(name) > 32:
                return jsonify({"error": "用户名长度需要 2-32 字符"}), 400
            status, body = await discord_api_patch("/users/@me", {"username": name})
            if status == 200:
                return jsonify({"ok": True})
            return (
                jsonify({"error": body.get("message", f"Discord API {status}")}),
                status,
            )
        except Exception as e:
            print(f"[api_bot_username] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bot/avatar", methods=["POST"])
    async def api_bot_avatar():
        """Change bot avatar via Discord REST API"""
        try:
            if not await is_owner(discord):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            avatar_b64 = d.get("avatar")  # expects "data:image/png;base64,..."
            if not avatar_b64:
                return jsonify({"error": "missing avatar data"}), 400
            status, body = await discord_api_patch("/users/@me", {"avatar": avatar_b64})
            if status == 200:
                return jsonify({"ok": True})
            return (
                jsonify({"error": body.get("message", f"Discord API {status}")}),
                status,
            )
        except Exception as e:
            print(f"[api_bot_avatar] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ═══════ Reaction Roles — Web Config ═══════

    @app.route("/api/guild/<string:gid>/reactionroles", methods=["GET"])
    async def api_rr_list(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_RR) as db:
                cur = await db.execute(
                    "SELECT message_id, channel_id, title, mappings, exclusive FROM rr_panels WHERE guild_id=?",
                    (g,),
                )
                rows = await cur.fetchall()
            return jsonify(
                [
                    {
                        "message_id": str(r[0]),
                        "channel_id": str(r[1]),
                        "title": r[2],
                        "mappings": r[3],
                        "exclusive": bool(r[4]),
                    }
                    for r in rows
                ]
            )
        except Exception as e:
            print(f"[api_rr_list] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/reactionroles/send", methods=["POST"])
    async def api_rr_send(gid):
        """Send a role-button panel to a Discord channel via Bot REST API"""
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            channel_id = d.get("channel_id")
            title = d.get("title", "🏷 身份组选择")
            content = d.get("content", "点击下方的按钮来领取身分组")
            mappings_list = d.get("mappings", [])  # [{emoji, role_id, role_name}]
            exclusive = bool(d.get("exclusive", False))

            if not channel_id or not mappings_list:
                return jsonify({"error": "缺少频道或身份组映射"}), 400
            if len(mappings_list) > 25:
                return jsonify({"error": "最多 25 个身份组(5 行 × 5 个按钮)"}), 400

            # ── 构造按钮 components(每行最多 5 个,最多 5 行)──
            mapping_dict = {}
            components = []
            current_row = {"type": 1, "components": []}

            for m in mappings_list:
                emoji_raw = m["emoji"]
                role_id = str(m["role_id"])
                role_name = m.get("role_name", "身份组")[:80]
                mapping_dict[emoji_raw] = int(role_id)

                # 解析 emoji:Unicode 或自定义 <:name:id> / <a:name:id>
                emoji_obj = None
                if emoji_raw.startswith("<") and emoji_raw.endswith(">"):
                    inner = emoji_raw.strip("<>")
                    parts = inner.split(":")
                    if len(parts) == 3:
                        emoji_obj = {
                            "name": parts[1],
                            "id": parts[2],
                            "animated": inner.startswith("a:"),
                        }
                else:
                    emoji_obj = {"name": emoji_raw}

                btn = {
                    "type": 2,
                    "style": 2,  # SECONDARY (gray)
                    "label": role_name,
                    "custom_id": f"rr:{role_id}",
                }
                if emoji_obj:
                    btn["emoji"] = emoji_obj

                if len(current_row["components"]) >= 5:
                    components.append(current_row)
                    current_row = {"type": 1, "components": []}
                current_row["components"].append(btn)

            if current_row["components"]:
                components.append(current_row)

            # 单选模式提示加在 description
            desc_with_hint = content
            if exclusive:
                desc_with_hint = f"{content}\n\n*注:只能选一个身份组,选其他会自动替换*"

            # ── 发送 embed + 按钮 ──
            msg_data = await discord_api_post(
                f"/channels/{channel_id}/messages",
                {
                    "embeds": [
                        {
                            "title": title,
                            "description": desc_with_hint,
                            "color": 0x2DD4BF,
                        }
                    ],
                    "components": components,
                },
            )
            message_id = msg_data["id"]

            g = int(gid)
            async with aiosqlite.connect(DB_RR) as db:
                await db.execute(
                    "INSERT INTO rr_panels (message_id, channel_id, guild_id, title, mappings, exclusive) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        int(message_id),
                        int(channel_id),
                        g,
                        title,
                        json.dumps(mapping_dict),
                        int(exclusive),
                    ),
                )
                await db.commit()

            actor = await _resolve_actor(discord)
            audit(
                g,
                "发送了身份组面板",
                **{
                    "操作者": actor,
                    "频道": f"<#{channel_id}>",
                    "标题": title,
                    "按钮数量": str(len(mapping_dict)),
                    "单选模式": "是" if exclusive else "否",
                },
            )
            return jsonify({"ok": True, "message_id": message_id})
        except Exception as e:
            print(f"[api_rr_send] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ═══════ Giveaway — Web Create ═══════

    @app.route("/api/guild/<string:gid>/giveaway/create", methods=["POST"])
    async def api_gw_create(gid):
        """Create a giveaway and send embed to Discord channel via Bot REST API"""
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            prize = d.get("prize", "").strip()
            winners_count = int(d.get("winners_count", 1))
            channel_id = d.get("channel_id")
            end_time = float(d.get("end_time", 0))
            restrict_role = d.get("restrict_role")

            if not prize or not channel_id or end_time <= 0:
                return jsonify({"error": "缺少必填字段"}), 400

            if end_time <= time.time():
                return jsonify({"error": "结束时间必须在未来"}), 400

            end_ts = int(end_time)

            # 1. Send giveaway embed with button to Discord
            embed_desc = (
                f"**奖品:** {prize}\n"
                f"**中奖名额:** {winners_count} 人\n"
                f"**结束时间:** <t:{end_ts}:R> (<t:{end_ts}:f>)\n\n"
                f"点击下方按钮参加抽奖！"
            )
            if restrict_role:
                embed_desc += f"\n\n🔒 限制身份组: <@&{restrict_role}>"

            msg_data = await discord_api_post(
                f"/channels/{channel_id}/messages",
                {
                    "embeds": [
                        {
                            "title": "🎉 抽奖活动！",
                            "description": embed_desc,
                            "color": 0x57F287,
                            "footer": {"text": "小凛抽奖系统 | 公平公正公开"},
                        }
                    ],
                    "components": [
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 1,
                                    "label": "🎉 参加抽奖!",
                                    "custom_id": "giveaway_enter",
                                }
                            ],
                        }
                    ],
                },
            )
            message_id = msg_data["id"]

            # 2. Save to giveaway DB
            g = int(gid)
            # Get host user from session (we know they're logged in)
            try:
                user = await discord.fetch_user()
                host_id = int(user.id)
            except Exception:
                host_id = 0

            async with aiosqlite.connect(DB_GIVEAWAY) as db:
                await db.execute(
                    "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        g,
                        int(channel_id),
                        int(message_id),
                        host_id,
                        prize,
                        winners_count,
                        end_time,
                    ),
                )
                await db.commit()

            actor = await _resolve_actor(discord)
            audit(
                g,
                "创建了抽奖活动",
                **{
                    "操作者": actor,
                    "奖品": prize,
                    "中奖人数": str(winners_count),
                    "频道": f"<#{channel_id}>",
                },
            )
            return jsonify({"ok": True, "message_id": message_id})
        except Exception as e:
            print(f"[api_gw_create] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ═══════ Command Toggle (Utility) ═══════

    # Static command registry — matches bot's actual commands
    COMMAND_REGISTRY = [
        {"name": "play", "desc": "播放音乐 (歌名或链接)", "cog": "Music"},
        {"name": "queue", "desc": "查看播放队列", "cog": "Music"},
        {"name": "skip", "desc": "跳过当前歌曲", "cog": "Music"},
        {"name": "pause", "desc": "暂停播放", "cog": "Music"},
        {"name": "resume", "desc": "恢复播放", "cog": "Music"},
        {"name": "stop", "desc": "停止播放并离开频道", "cog": "Music"},
        {"name": "nowplaying", "desc": "查看正在播放的歌曲", "cog": "Music"},
        {"name": "loop", "desc": "设置循环模式", "cog": "Music"},
        {"name": "volume", "desc": "调整音量 (0-200)", "cog": "Music"},
        {"name": "shuffle", "desc": "随机打乱队列", "cog": "Music"},
        {"name": "move", "desc": "移动队列中的歌曲位置", "cog": "Music"},
        {"name": "remove", "desc": "从队列移除指定歌曲", "cog": "Music"},
        {"name": "clear", "desc": "清空播放队列", "cog": "Music"},
        {"name": "join", "desc": "加入你的语音频道", "cog": "Music"},
        {"name": "rank", "desc": "查看你的等级卡片", "cog": "Leveling"},
        {"name": "kick", "desc": "踢出成员", "cog": "Moderation"},
        {"name": "ban", "desc": "永久封禁成员", "cog": "Moderation"},
        {"name": "tempban", "desc": "临时封禁成员", "cog": "Moderation"},
        {"name": "unban", "desc": "解除封禁", "cog": "Moderation"},
        {"name": "mute", "desc": "禁言成员 (Timeout)", "cog": "Moderation"},
        {"name": "unmute", "desc": "解除禁言", "cog": "Moderation"},
        {"name": "warn", "desc": "警告成员", "cog": "Moderation"},
        {"name": "warns", "desc": "查看警告记录", "cog": "Moderation"},
        {"name": "clearwarns", "desc": "清除所有警告", "cog": "Moderation"},
        {"name": "delwarn", "desc": "删除指定警告", "cog": "Moderation"},
        {"name": "purge", "desc": "批量清理消息", "cog": "Moderation"},
        {"name": "slowmode", "desc": "设置频道慢速模式", "cog": "Moderation"},
        {"name": "lock", "desc": "锁定频道", "cog": "Moderation"},
        {"name": "unlock", "desc": "解锁频道", "cog": "Moderation"},
        {"name": "modlog", "desc": "查看管理操作日志", "cog": "Moderation"},
        {"name": "status", "desc": "显示服务器详细状态", "cog": "General"},
        {"name": "roll", "desc": "投掷骰子 (默认6面)", "cog": "General"},
        {"name": "avatar", "desc": "查看用户的大图头像", "cog": "General"},
        {"name": "setstatus", "desc": "修改机器人的活动状态", "cog": "General"},
        {"name": "resetstatus", "desc": "重置机器人状态", "cog": "General"},
        {"name": "setbio", "desc": "修改机器人的简介", "cog": "General"},
        {"name": "welcome_setup", "desc": "配置迎新和道别系统", "cog": "Welcome"},
        {"name": "welcome_test", "desc": "测试欢迎图卡效果", "cog": "Welcome"},
        {"name": "rr_create", "desc": "创建反应身份组面板", "cog": "ReactionRoles"},
        {"name": "rr_add", "desc": "添加 emoji → 身份组映射", "cog": "ReactionRoles"},
        {"name": "rr_remove", "desc": "移除一个 emoji 映射", "cog": "ReactionRoles"},
        {"name": "rr_list", "desc": "列出所有面板", "cog": "ReactionRoles"},
        {"name": "rr_delete", "desc": "删除面板", "cog": "ReactionRoles"},
        {"name": "giveaway", "desc": "抽奖管理 (start/end/reroll)", "cog": "Giveaway"},
        {"name": "automod", "desc": "自动审核配置面板", "cog": "AutoMod"},
        {"name": "automod_words", "desc": "管理违禁词列表", "cog": "AutoMod"},
        {"name": "automod_whitelist", "desc": "管理链接白名单", "cog": "AutoMod"},
        {"name": "automod_ignore", "desc": "管理审核忽略列表", "cog": "AutoMod"},
        {"name": "toggle", "desc": "启用/禁用指定指令", "cog": "System"},
        {"name": "togglelist", "desc": "查看已禁用的指令", "cog": "System"},
    ]
    PROTECTED = {
        "toggle",
        "togglelist",
        "hot_update",
        "sync",
        "load",
        "unload",
        "extensions",
        "eval",
        "help",
    }

    @app.route("/api/guild/<string:gid>/commands", methods=["GET"])
    async def api_commands_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            disabled = set()
            async with aiosqlite.connect(DB_CMDTOGGLE) as db:
                cur = await db.execute(
                    "SELECT command_name FROM disabled_commands WHERE guild_id=?", (g,)
                )
                rows = await cur.fetchall()
                disabled = {r[0] for r in rows}
            result = []
            for cmd in COMMAND_REGISTRY:
                result.append(
                    {
                        "name": cmd["name"],
                        "desc": cmd["desc"],
                        "cog": cmd["cog"],
                        "enabled": cmd["name"] not in disabled,
                        "protected": cmd["name"] in PROTECTED,
                    }
                )
            return jsonify(result)
        except Exception as e:
            print(f"[api_commands_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/commands/toggle", methods=["POST"])
    async def api_commands_toggle(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            name = d.get("name", "")
            enabled = d.get("enabled", True)
            if name in PROTECTED:
                return jsonify({"error": "核心指令不能被禁用"}), 400
            g = int(gid)
            async with aiosqlite.connect(DB_CMDTOGGLE) as db:
                if enabled:
                    await db.execute(
                        "DELETE FROM disabled_commands WHERE guild_id=? AND command_name=?",
                        (g, name),
                    )
                else:
                    await db.execute(
                        "INSERT OR IGNORE INTO disabled_commands (guild_id, command_name) VALUES (?, ?)",
                        (g, name),
                    )
                await db.commit()
            actor = await _resolve_actor(discord)
            action = "启用" if enabled else "禁用"
            audit(g, f"{action}了指令", **{"操作者": actor, "指令": f"/{name}"})
            return jsonify({"ok": True, "name": name, "enabled": enabled})
        except Exception as e:
            print(f"[api_commands_toggle] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500
