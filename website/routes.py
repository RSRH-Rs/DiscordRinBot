from quart import redirect, url_for, render_template, session, jsonify, request
import traceback
import aiohttp
import aiosqlite
import json
import os
from config import BOT_TOKEN

# ── 关键：数据库在 rinbot 目录，网站在 website 目录 ──
# 相对路径: website/ → ../rinbot/
BOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rinbot")

DB_WELCOME    = os.path.join(BOT_DIR, "welcome.db")
DB_AUTOMOD    = os.path.join(BOT_DIR, "automod.db")
DB_MODERATION = os.path.join(BOT_DIR, "moderation.db")
DB_GIVEAWAY   = os.path.join(BOT_DIR, "giveaway.db")
DB_LEVELING   = os.path.join(BOT_DIR, "leveling.db")
DB_BOTCONFIG  = os.path.join(BOT_DIR, "botconfig.db")
DB_RR         = os.path.join(BOT_DIR, "reactionroles.db")


async def ensure_tables():
    """Bot 可能还没跑过，先建好所有表"""
    try:
        async with aiosqlite.connect(DB_WELCOME) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS welcome_config (
                guild_id INTEGER PRIMARY KEY, welcome_channel INTEGER DEFAULT 0,
                farewell_channel INTEGER DEFAULT 0, auto_roles TEXT DEFAULT '',
                welcome_msg TEXT DEFAULT '欢迎 {member} 加入 {server}！🎉',
                farewell_msg TEXT DEFAULT '{member} 离开了我们... 👋')""")
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
            await db.execute("""CREATE TABLE IF NOT EXISTS mod_config (
                guild_id INTEGER PRIMARY KEY, log_channel INTEGER DEFAULT 0,
                warn_kick_threshold INTEGER DEFAULT 0, warn_ban_threshold INTEGER DEFAULT 0,
                warn_mute_threshold INTEGER DEFAULT 3, warn_mute_duration INTEGER DEFAULT 600)""")
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
                mappings TEXT DEFAULT '{}')""")
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
        async with aiohttp.ClientSession() as s:
            async with s.get("https://discord.com/api/v10/users/@me/guilds",
                             headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return {int(g["id"]) for g in await resp.json()}
    except Exception as e:
        print(f"[fetch_bot_guild_ids] {e}")
    return set()


async def discord_api_get(path):
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://discord.com/api/v10{path}",
                             headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"[Discord API] {path} → {resp.status}")
    except Exception as e:
        print(f"[Discord API] {path}: {e}")
    return None


async def discord_api_post(path, json_data):
    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"https://discord.com/api/v10{path}",
                          headers=headers, json=json_data,
                          timeout=aiohttp.ClientTimeout(total=10)) as resp:
            body = await resp.json()
            if resp.status in (200, 201):
                return body
            raise Exception(body.get("message", f"Discord API {resp.status}"))


async def discord_api_put(path):
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.put(f"https://discord.com/api/v10{path}",
                         headers=headers,
                         timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 204:
                return True
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

    # ═══════ Page routes ═══════

    @app.route("/")
    async def index():
        bot_info = {"name": "小凛 RinBot", "status": "Online", "server_count": 12,
                    "description": "全能型音乐/娱乐/管理机器人"}
        try:
            is_logged_in = await discord.authorized
        except Exception:
            is_logged_in = False
        return await render_template("index.html", bot=bot_info, is_logged_in=is_logged_in)

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
            return await render_template("dashboard.html", user=user, guilds=manageable)
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
                return await render_template("error.html", error="找不到该服务器或无权访问"), 404
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
                [{"id": str(c["id"]), "name": c["name"]} for c in data if c.get("type") == 0],
                key=lambda c: c["name"])
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
                [{"id": str(r["id"]), "name": r["name"], "color": r.get("color", 0)}
                 for r in data if r["name"] != "@everyone"],
                key=lambda r: r["name"])
            return jsonify(roles)
        except Exception as e:
            print(f"[api_roles] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ── Welcome ──

    @app.route("/api/guild/<string:gid>/welcome", methods=["GET"])
    async def api_welcome_get(gid):
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            g = int(gid)
            async with aiosqlite.connect(DB_WELCOME) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("SELECT * FROM welcome_config WHERE guild_id=?", (g,))
                row = await cur.fetchone()
            if row:
                return jsonify(dict(row))
            return jsonify({"guild_id": g, "welcome_channel": 0, "farewell_channel": 0,
                            "auto_roles": "",
                            "welcome_msg": "欢迎 {member} 加入 {server}！🎉",
                            "farewell_msg": "{member} 离开了我们... 👋"})
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
                await db.execute("INSERT OR IGNORE INTO welcome_config (guild_id) VALUES (?)", (g,))
                await db.execute("""UPDATE welcome_config SET
                    welcome_channel=?, farewell_channel=?, auto_roles=?,
                    welcome_msg=?, farewell_msg=? WHERE guild_id=?""",
                    (int(d.get("welcome_channel", 0)), int(d.get("farewell_channel", 0)),
                     d.get("auto_roles", ""), d.get("welcome_msg", ""),
                     d.get("farewell_msg", ""), g))
                await db.commit()
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
                cur = await db.execute("SELECT * FROM automod_config WHERE guild_id=?", (g,))
                row = await cur.fetchone()
            if row:
                d = dict(row)
                for k in ("badwords", "link_whitelist", "ignored_channels", "ignored_roles"):
                    try:
                        d[k] = json.loads(d.get(k, "[]"))
                    except Exception:
                        d[k] = []
                return jsonify(d)
            return jsonify({"guild_id": g, "enabled": 0, "log_channel": 0,
                            "anti_spam": 1, "spam_threshold": 5, "spam_interval": 5,
                            "anti_badword": 1, "badwords": [], "anti_link": 0,
                            "link_whitelist": [], "anti_caps": 1, "caps_threshold": 70,
                            "caps_min_length": 10, "anti_repeat": 1, "repeat_threshold": 3,
                            "mute_duration": 300, "ignored_channels": [], "ignored_roles": []})
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
                await db.execute("INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (g,))
                await db.execute("""UPDATE automod_config SET
                    enabled=?, log_channel=?, anti_spam=?, spam_threshold=?, spam_interval=?,
                    anti_badword=?, badwords=?, anti_link=?, link_whitelist=?,
                    anti_caps=?, caps_threshold=?, anti_repeat=?, repeat_threshold=?,
                    mute_duration=?, ignored_channels=?, ignored_roles=?
                    WHERE guild_id=?""",
                    (int(d.get("enabled", 1)), int(d.get("log_channel", 0)),
                     int(d.get("anti_spam", 1)), int(d.get("spam_threshold", 5)),
                     int(d.get("spam_interval", 5)), int(d.get("anti_badword", 1)),
                     json.dumps(d.get("badwords", []), ensure_ascii=False),
                     int(d.get("anti_link", 0)),
                     json.dumps(d.get("link_whitelist", []), ensure_ascii=False),
                     int(d.get("anti_caps", 1)), int(d.get("caps_threshold", 70)),
                     int(d.get("anti_repeat", 1)), int(d.get("repeat_threshold", 3)),
                     int(d.get("mute_duration", 300)),
                     json.dumps(d.get("ignored_channels", []), ensure_ascii=False),
                     json.dumps(d.get("ignored_roles", []), ensure_ascii=False),
                     g))
                await db.commit()
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
                cur = await db.execute("SELECT * FROM mod_config WHERE guild_id=?", (g,))
                row = await cur.fetchone()
            if row:
                return jsonify(dict(row))
            return jsonify({"guild_id": g, "log_channel": 0,
                            "warn_kick_threshold": 0, "warn_ban_threshold": 0,
                            "warn_mute_threshold": 3, "warn_mute_duration": 600})
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
                await db.execute("INSERT OR IGNORE INTO mod_config (guild_id) VALUES (?)", (g,))
                await db.execute("""UPDATE mod_config SET
                    log_channel=?, warn_mute_threshold=?, warn_kick_threshold=?,
                    warn_ban_threshold=?, warn_mute_duration=? WHERE guild_id=?""",
                    (int(d.get("log_channel", 0)), int(d.get("warn_mute_threshold", 3)),
                     int(d.get("warn_kick_threshold", 0)), int(d.get("warn_ban_threshold", 0)),
                     int(d.get("warn_mute_duration", 600)), g))
                await db.commit()
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
                    "FROM mod_cases WHERE guild_id=? ORDER BY created_at DESC LIMIT 20", (g,))
                rows = await cur.fetchall()
            return jsonify([
                {"id": r[0], "action": r[1], "user_id": str(r[2]),
                 "mod_id": str(r[3]), "reason": r[4], "duration": r[5],
                 "created_at": r[6]}
                for r in rows
            ])
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
                    "FROM giveaways WHERE guild_id=? ORDER BY end_time DESC LIMIT 10", (g,))
                rows = await cur.fetchall()
            return jsonify([
                {"id": r[0], "prize": r[1], "winners_count": r[2],
                 "end_time": r[3], "ended": bool(r[4])}
                for r in rows
            ])
        except Exception as e:
            print(f"[api_giveaways] {traceback.format_exc()}")
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
                    "WHERE guild_id=? ORDER BY xp DESC LIMIT 15", (g,))
                rows = await cur.fetchall()
            return jsonify([
                {"user_id": str(r[0]), "xp": r[1], "level": r[2]}
                for r in rows
            ])
        except Exception as e:
            print(f"[api_leaderboard] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # ═══════ Bot Personalizer ═══════

    @app.route("/api/bot/personalizer", methods=["GET"])
    async def api_bot_cfg_get():
        try:
            if not await discord.authorized:
                return jsonify({"error": "unauthorized"}), 401
            async with aiosqlite.connect(DB_BOTCONFIG) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("SELECT * FROM bot_personalizer WHERE id=1")
                row = await cur.fetchone()
            if row:
                return jsonify(dict(row))
            return jsonify({"bot_status": "online", "activity_type": "watching",
                            "activity_text": "正在偷看你的聊天记录|rin-bot.com"})
        except Exception as e:
            print(f"[api_bot_cfg_get] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bot/personalizer", methods=["POST"])
    async def api_bot_cfg_post():
        try:
            if not await discord.authorized:
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            import time
            async with aiosqlite.connect(DB_BOTCONFIG) as db:
                await db.execute("INSERT OR IGNORE INTO bot_personalizer (id) VALUES (1)")
                await db.execute("""UPDATE bot_personalizer SET
                    bot_status=?, activity_type=?, activity_text=?, updated_at=?
                    WHERE id=1""",
                    (d.get("bot_status", "online"),
                     d.get("activity_type", "watching"),
                     d.get("activity_text", ""),
                     time.time()))
                await db.commit()
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_bot_cfg_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bot/username", methods=["POST"])
    async def api_bot_username():
        """Change bot username via Discord REST API (rate limited: 2/hour)"""
        try:
            if not await discord.authorized:
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            name = d.get("username", "").strip()
            if not name or len(name) < 2 or len(name) > 32:
                return jsonify({"error": "用户名长度需要 2-32 字符"}), 400
            headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as s:
                async with s.patch("https://discord.com/api/v10/users/@me",
                                   headers=headers, json={"username": name},
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return jsonify({"ok": True})
                    body = await resp.json()
                    return jsonify({"error": body.get("message", f"Discord API {resp.status}")}), resp.status
        except Exception as e:
            print(f"[api_bot_username] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bot/avatar", methods=["POST"])
    async def api_bot_avatar():
        """Change bot avatar via Discord REST API"""
        try:
            if not await discord.authorized:
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            avatar_b64 = d.get("avatar")  # expects "data:image/png;base64,..."
            if not avatar_b64:
                return jsonify({"error": "missing avatar data"}), 400
            headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as s:
                async with s.patch("https://discord.com/api/v10/users/@me",
                                   headers=headers, json={"avatar": avatar_b64},
                                   timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return jsonify({"ok": True})
                    body = await resp.json()
                    return jsonify({"error": body.get("message", f"Discord API {resp.status}")}), resp.status
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
                    "SELECT message_id, channel_id, title, mappings FROM rr_panels WHERE guild_id=?", (g,))
                rows = await cur.fetchall()
            return jsonify([
                {"message_id": str(r[0]), "channel_id": str(r[1]),
                 "title": r[2], "mappings": r[3]}
                for r in rows
            ])
        except Exception as e:
            print(f"[api_rr_list] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/reactionroles/send", methods=["POST"])
    async def api_rr_send(gid):
        """Send a reaction role panel to a Discord channel via Bot REST API"""
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            channel_id = d.get("channel_id")
            title = d.get("title", "🏷 身份组选择")
            content = d.get("content", "点击下方的反应来领取对应身份组")
            mappings_list = d.get("mappings", [])  # [{emoji, role_id}]

            if not channel_id or not mappings_list:
                return jsonify({"error": "缺少频道或身份组映射"}), 400

            # Build embed description with emoji → role mapping display
            desc_lines = [content, ""]
            mapping_dict = {}
            for m in mappings_list:
                emoji = m["emoji"]
                role_id = m["role_id"]
                mapping_dict[emoji] = int(role_id)
                desc_lines.append(f"{emoji} → <@&{role_id}>")

            # 1. Send embed message to Discord channel
            msg_data = await discord_api_post(f"/channels/{channel_id}/messages", {
                "embeds": [{
                    "title": title,
                    "description": "\n".join(desc_lines),
                    "color": 0x2DD4BF,
                    "footer": {"text": "点击下方反应获取对应身份组 | 再次点击移除"}
                }]
            })
            message_id = msg_data["id"]

            # 2. Add reactions to the message
            import urllib.parse
            for m in mappings_list:
                emoji = m["emoji"]
                encoded = urllib.parse.quote(emoji)
                try:
                    await discord_api_put(
                        f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me")
                except Exception as e:
                    print(f"[RR] Failed to add reaction {emoji}: {e}")
                import asyncio
                await asyncio.sleep(0.3)  # Rate limit safety

            # 3. Save to DB
            g = int(gid)
            async with aiosqlite.connect(DB_RR) as db:
                await db.execute(
                    "INSERT INTO rr_panels (message_id, channel_id, guild_id, title, mappings) VALUES (?, ?, ?, ?, ?)",
                    (int(message_id), int(channel_id), g, title, json.dumps(mapping_dict)))
                await db.commit()

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

            import time
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

            msg_data = await discord_api_post(f"/channels/{channel_id}/messages", {
                "embeds": [{
                    "title": "🎉 抽奖活动！",
                    "description": embed_desc,
                    "color": 0x57F287,
                    "footer": {"text": "小凛抽奖系统 | 公平公正公开"}
                }],
                "components": [{
                    "type": 1,
                    "components": [{
                        "type": 2,
                        "style": 1,
                        "label": "🎉 参加抽奖!",
                        "custom_id": "giveaway_enter"
                    }]
                }]
            })
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
                    (g, int(channel_id), int(message_id), host_id, prize, winners_count, end_time))
                await db.commit()

            return jsonify({"ok": True, "message_id": message_id})
        except Exception as e:
            print(f"[api_gw_create] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500
