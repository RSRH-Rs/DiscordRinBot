from quart import redirect, url_for, render_template, session, jsonify, request, send_file
import asyncio
import base64
import binascii
import hashlib
import time
import math
import re
import traceback
import aiohttp
import aiosqlite
import json
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError
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

_MAX_IMAGE_URL_LENGTH = 2048
_MAX_AVATAR_BYTES = 5 * 1024 * 1024
_MAX_AVATAR_DIMENSION = 4096
_ALLOWED_AVATAR_MIMES = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/gif": "GIF",
    "image/webp": "WEBP",
}
_IMAGE_PLACEHOLDERS = {"%avatar%", "%server_avatar%"}
_MAX_WELCOME_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_WELCOME_IMAGE_DIMENSION = 4096
_MAX_WELCOME_IMAGE_FRAMES = 200
_MAX_WELCOME_ANIMATED_PIXELS = 100_000_000
_WELCOME_IMAGE_FORMATS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "GIF": (".gif", "image/gif"),
    "WEBP": (".webp", "image/webp"),
}
_WELCOME_IMAGE_COLUMNS = {
    "welcome": "welcome_image_file",
    "farewell": "farewell_image_file",
}
_WELCOME_IMAGE_NAME = re.compile(
    r"^(?P<gid>[1-9][0-9]*)-(?P<kind>welcome|farewell)-(?P<digest>[0-9a-f]{16})"
    r"(?P<suffix>\.png|\.jpg|\.gif|\.webp)$"
)
_welcome_upload_locks: dict[tuple[int, str], asyncio.Lock] = {}


class _WelcomeImageValidationError(ValueError):
    pass


def _normalize_image_url(value, *, allow_placeholders=True) -> str:
    """Return a safe optional HTTP(S) image URL or supported placeholder."""
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValueError("图片链接格式无效")
    value = value.strip()
    if allow_placeholders and value in _IMAGE_PLACEHOLDERS:
        return value
    if len(value) > _MAX_IMAGE_URL_LENGTH or any(ord(ch) < 32 for ch in value):
        raise ValueError("图片链接过长或包含非法字符")
    parsed = urlparse(value)
    try:
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError("图片链接格式无效") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise ValueError("图片链接必须是有效的 HTTP 或 HTTPS 地址")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("图片链接不能包含登录凭据")
    return value


def _bot_avatar_url(bot_user) -> str:
    """Only build a Discord CDN URL from the bot's public identity fields."""
    uid = str(bot_user.get("id", ""))
    avatar = bot_user.get("avatar")
    if uid.isascii() and uid.isdigit() and isinstance(avatar, str):
        digest = avatar.removeprefix("a_")
        if len(digest) == 32 and all(c in "0123456789abcdef" for c in digest):
            extension = "gif" if avatar.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.{extension}?size=256"
    return url_for("static", filename="images/rin/bot-avatar.png")


def _validate_avatar_data_uri(value) -> Optional[str]:
    """Validate an avatar data URI; return an error message when invalid."""
    if not isinstance(value, str):
        return "头像数据格式无效"
    header, separator, payload = value.partition(",")
    if not separator or not header.lower().endswith(";base64"):
        return "头像必须使用 Base64 data URI"
    mime = header[5:-7].lower() if header.lower().startswith("data:") else ""
    expected_format = _ALLOWED_AVATAR_MIMES.get(mime)
    if expected_format is None:
        return "仅支持 PNG、JPEG、GIF 或 WebP 图片"
    if len(payload) > ((_MAX_AVATAR_BYTES + 2) // 3) * 4:
        return "头像文件不能超过 5 MB"
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return "头像 Base64 数据无效"
    if not raw or len(raw) > _MAX_AVATAR_BYTES:
        return "头像文件不能为空且不能超过 5 MB"
    try:
        with Image.open(BytesIO(raw)) as image:
            width, height = image.size
            actual_format = (image.format or "").upper()
            if width < 1 or height < 1:
                return "头像尺寸无效"
            if width > _MAX_AVATAR_DIMENSION or height > _MAX_AVATAR_DIMENSION:
                return "头像尺寸不能超过 4096×4096"
            if actual_format != expected_format:
                return "头像声明的类型与实际文件不一致"
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return "头像文件损坏或不是有效图片"
    return None


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
_BOT_DIR_ABS = os.path.abspath(BOT_DIR)
if _BOT_DIR_ABS not in sys.path:
    sys.path.insert(0, _BOT_DIR_ABS)
from rincore import storage, sync  # noqa: E402
from guild_ids import collect_guild_ids  # noqa: E402
WELCOME_UPLOAD_DIR = os.path.abspath(
    os.environ.get(
        "RINBOT_WELCOME_UPLOAD_DIR", os.path.join(BOT_DIR, "uploads", "welcome")
    )
)

DB_WELCOME = storage.db_path("welcome")
DB_AUTOMOD = storage.db_path("automod")
DB_MODERATION = storage.db_path("moderation")
DB_GIVEAWAY = storage.db_path("giveaway")
DB_LEVELING = storage.db_path("leveling")
DB_BOTCONFIG = storage.db_path("botconfig")
DB_RR = storage.db_path("reactionroles")
DB_CMDTOGGLE = storage.db_path("commandtoggle")
DB_MUSIC = storage.db_path("musicconfig")
DB_BOTLOG = storage.db_path("botlog")
DB_SERVERLOG = storage.db_path("serverlog")
DB_GLOBAL = storage.db_path("globalsettings")


def _validate_welcome_image(raw: bytes, claimed_mime: str = "") -> tuple[str, str]:
    """Validate uploaded image bytes and return (suffix, canonical MIME)."""
    if not raw:
        raise _WelcomeImageValidationError("请选择一张图片")
    if len(raw) > _MAX_WELCOME_IMAGE_BYTES:
        raise _WelcomeImageValidationError("图片不能超过 5 MB")
    try:
        with Image.open(BytesIO(raw)) as image:
            actual_format = (image.format or "").upper()
            image_spec = _WELCOME_IMAGE_FORMATS.get(actual_format)
            if image_spec is None:
                raise _WelcomeImageValidationError(
                    "仅支持 PNG、JPG、GIF 或 WebP 图片"
                )
            width, height = image.size
            if width < 1 or height < 1:
                raise _WelcomeImageValidationError("图片尺寸无效")
            if (
                width > _MAX_WELCOME_IMAGE_DIMENSION
                or height > _MAX_WELCOME_IMAGE_DIMENSION
            ):
                raise _WelcomeImageValidationError("图片尺寸不能超过 4096×4096")
            frames = int(getattr(image, "n_frames", 1))
            if frames > _MAX_WELCOME_IMAGE_FRAMES:
                raise _WelcomeImageValidationError("动图不能超过 200 帧")
            if width * height * frames > _MAX_WELCOME_ANIMATED_PIXELS:
                raise _WelcomeImageValidationError(
                    "动图总尺寸过大，请缩小尺寸或减少帧数"
                )
            image.verify()
    except _WelcomeImageValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("图片文件损坏或不是有效图片") from exc

    suffix, expected_mime = image_spec
    normalized_mime = (claimed_mime or "").split(";", 1)[0].strip().lower()
    if normalized_mime and normalized_mime != expected_mime:
        raise ValueError("图片声明的类型与实际文件不一致")
    return suffix, expected_mime


def _welcome_image_path(filename: str, gid: int, kind: str) -> Optional[str]:
    """Resolve a DB filename only when it is a safe file for this guild and slot."""
    if not isinstance(filename, str) or not filename or os.path.basename(filename) != filename:
        return None
    match = _WELCOME_IMAGE_NAME.fullmatch(filename)
    if not match or int(match.group("gid")) != gid or match.group("kind") != kind:
        return None
    root = os.path.realpath(WELCOME_UPLOAD_DIR)
    path = os.path.realpath(os.path.join(root, filename))
    try:
        if os.path.commonpath((root, path)) != root:
            return None
    except ValueError:
        return None
    return path


async def _welcome_image_filename(gid: int, kind: str) -> str:
    column = _WELCOME_IMAGE_COLUMNS[kind]
    async with aiosqlite.connect(DB_WELCOME) as db:
        cur = await db.execute(
            f"SELECT {column} FROM welcome_config WHERE guild_id=?", (gid,)
        )
        row = await cur.fetchone()
    return str(row[0] or "") if row else ""


def _remove_welcome_image(filename: str, gid: int, kind: str) -> None:
    path = _welcome_image_path(filename, gid, kind)
    if not path:
        return
    try:
        if os.path.isfile(path) and not os.path.islink(path):
            os.remove(path)
    except OSError as exc:
        print(f"[_remove_welcome_image] {exc}")

_MODULE_COGS = {
    "music": "Music", "welcome": "Welcome", "roles": "ReactionRoles",
    "automod": "AutoMod", "moderation": "Moderation", "giveaway": "Giveaway",
    "leveling": "Leveling", "utility": "CommandToggle", "botlog": "BotLog",
    "serverlog": "ServerLog", "general": "General",
}


def _runtime_health() -> dict:
    """A heartbeat is evidence of freshness, not by itself a gateway connection."""
    try:
        with open(os.path.join(BOT_DIR, "health.json"), encoding="utf-8") as f:
            data = json.load(f)
        stamp = float(data.get("updated_at", 0))
        if not math.isfinite(stamp):
            raise ValueError("invalid heartbeat timestamp")
        fresh = 0 <= time.time() - stamp < 90
        state = "stale" if not fresh else (
            "online" if data.get("gateway_connected") is True else
            "offline" if data.get("gateway_connected") is False else "unknown"
        )
        cogs = data.get("cogs")
        return {"state": state, "fresh": fresh, "updated_at": stamp,
                "cogs": cogs if fresh and isinstance(cogs, list) else None,
                "guild_ids": data.get("guild_ids") if fresh else None}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"state": "unknown", "fresh": False, "updated_at": None, "cogs": None, "guild_ids": None}


async def _guild_module_config(slug: str, gid: int) -> str:
    """Read saved configuration without creating a DB or implying live activation."""
    specs = {
        "welcome": (DB_WELCOME, "welcome_config"),
        "automod": (DB_AUTOMOD, "automod_config"),
        "music": (DB_MUSIC, "music_config"),
        "moderation": (DB_MODERATION, "mod_config"),
        "botlog": (DB_BOTLOG, "botlog_config"),
        "serverlog": (DB_SERVERLOG, "serverlog_config"),
    }
    if slug not in specs:
        return "available"
    filename, table = specs[slug]
    default = "default" if slug in {"music", "moderation"} else "unconfigured"
    if not os.path.isfile(filename):
        return default
    try:
        uri = Path(filename).resolve().as_uri() + "?mode=ro"
        async with aiosqlite.connect(uri, uri=True, timeout=2) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(f"SELECT * FROM {table} WHERE guild_id=?", (gid,))
            row = await cur.fetchone()
        if row is None:
            return default
        cfg = dict(row)
        if slug in {"welcome", "automod", "botlog", "serverlog"}:
            if not cfg.get("enabled", 1):
                return "disabled"
            if slug == "welcome" and not (cfg.get("welcome_channel") or cfg.get("farewell_channel") or cfg.get("auto_roles")):
                return "unconfigured"
            if slug in {"botlog", "serverlog"} and not cfg.get("channel_id"):
                return "unconfigured"
            return "enabled"
        return "configured"
    except (aiosqlite.Error, OSError, ValueError):
        return "unknown"


async def ensure_tables():
    """Bot 可能还没跑过，先建好所有表"""
    await storage.enable_wal()
    try:
        async with aiosqlite.connect(DB_WELCOME) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS welcome_config (
                guild_id INTEGER PRIMARY KEY, welcome_channel INTEGER DEFAULT 0,
                farewell_channel INTEGER DEFAULT 0, auto_roles TEXT DEFAULT '',
                welcome_msg TEXT DEFAULT '欢迎 %member% 加入 %server%！🎉',
                farewell_msg TEXT DEFAULT '%member% 离开了我们... 👋',
                show_card INTEGER DEFAULT 0, welcome_title TEXT DEFAULT '',
                author_icon TEXT DEFAULT '', thumbnail_url TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1, image_url TEXT DEFAULT '',
                welcome_image_file TEXT DEFAULT '',
                farewell_image_file TEXT DEFAULT '')""")
            for ddl in (
                "show_card INTEGER DEFAULT 0",
                "welcome_title TEXT DEFAULT ''",
                "author_icon TEXT DEFAULT ''",
                "thumbnail_url TEXT DEFAULT ''",
                "enabled INTEGER DEFAULT 1",
                "image_url TEXT DEFAULT ''",
                "welcome_image_file TEXT DEFAULT ''",
                "farewell_image_file TEXT DEFAULT ''",
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
                ended INTEGER DEFAULT 0, restrict_role INTEGER DEFAULT 0)""")
            try:
                await db.execute(
                    "ALTER TABLE giveaways ADD COLUMN restrict_role INTEGER DEFAULT 0"
                )
            except Exception:
                pass
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


_BOT_GUILDS_TTL = 60  # 秒
_bot_guilds_cache = (0.0, set())  # (时间戳, guild id 集合)


async def fetch_bot_guild_ids() -> set:
    """bot 所在的全部服务器 id（分页获取，缓存 60 秒；出错时返回旧缓存，没有则空集合）。"""
    global _bot_guilds_cache
    ts, cached = _bot_guilds_cache
    if cached and time.time() - ts < _BOT_GUILDS_TTL:
        return set(cached)
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}

    async def fetch_page(after):
        url = "https://discord.com/api/v10/users/@me/guilds?limit=200"
        if after is not None:
            url += f"&after={after}"
        s = await _get_session()
        async with s.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return await resp.json()

    try:
        ids = await collect_guild_ids(fetch_page)
    except Exception as e:
        print(f"[fetch_bot_guild_ids] {e}")
        return set(cached)
    _bot_guilds_cache = (time.time(), ids)
    return set(ids)


async def _notify_bot(module: str, gid) -> None:
    """配置已写库后通知 bot 重载；通知失败只记日志，不影响已成功的保存。"""
    try:
        await sync.notify(module, int(gid))
    except Exception as e:
        print(f"[sync] notify 失败 ({module}, {gid}): {e!r}")


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


async def _validate_guild_resources(
    gid, channel_ids=(), role_ids=(), assignable_roles=False
):
    """Validate IDs supplied by the browser against the target guild."""
    try:
        channel_ids = {int(v) for v in channel_ids if v not in (None, "", 0, "0")}
        role_ids = {int(v) for v in role_ids if v not in (None, "", 0, "0")}
    except (TypeError, ValueError):
        return False

    if channel_ids:
        channels = await discord_api_get(f"/guilds/{int(gid)}/channels")
        if channels is None:
            return None
        available = {
            int(c["id"])
            for c in channels
            if c.get("type") in (0, 5) and c.get("id")
        }
        if not channel_ids.issubset(available):
            return False

    if role_ids:
        roles = await discord_api_get(f"/guilds/{int(gid)}/roles")
        if roles is None:
            return None
        available = {
            int(r["id"])
            for r in roles
            if r.get("id") and r.get("name") != "@everyone"
        }
        if not role_ids.issubset(available):
            return False
        if assignable_roles:
            bot_user = await discord_api_get("/users/@me")
            if not bot_user:
                return None
            bot_member = await discord_api_get(
                f"/guilds/{int(gid)}/members/{bot_user.get('id', 0)}"
            )
            if not bot_member:
                return None
            bot_role_ids = {int(value) for value in bot_member.get("roles", [])}
            bot_positions = [
                int(role.get("position", 0))
                for role in roles
                if int(role.get("id", 0)) in bot_role_ids
            ]
            bot_top_position = max(bot_positions, default=0)
            for role in roles:
                if int(role.get("id", 0)) in role_ids and (
                    role.get("managed") or int(role.get("position", 0)) >= bot_top_position
                ):
                    return False

    return True


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
            bot_user = await discord_api_get("/users/@me")
            bot_id = bot_user.get("id", "0") if bot_user else "0"
            me = await discord_api_get(f"/guilds/{gid}/members/{bot_id}")

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
        health = _runtime_health()
        result = []
        for m in MODULES:
            loaded = (_MODULE_COGS[m["slug"]] in health["cogs"]
                      if health["cogs"] is not None else None)
            result.append(
                {k: v for k, v in m.items() if k != "db"} | {"loaded": loaded}
            )
        return jsonify(result)

    @app.route("/api/guild/<string:gid>/modules")
    async def api_guild_modules(gid):
        if not gid.isascii() or not gid.isdigit() or not await check_guild_access(discord, gid):
            return jsonify({"error": "unauthorized"}), 401
        health = _runtime_health()
        state = health["state"]
        if isinstance(health["guild_ids"], list) and gid not in health["guild_ids"]:
            state = "not_joined"
        configs = await asyncio.gather(*(_guild_module_config(m["slug"], int(gid)) for m in MODULES))
        result = []
        for m, config_state in zip(MODULES, configs):
            loaded = (_MODULE_COGS[m["slug"]] in health["cogs"]
                      if health["cogs"] is not None else None)
            result.append({k:v for k,v in m.items() if k != "db"} |
                          {"loaded": loaded, "config_state": config_state})
        return jsonify({"bot_state": state, "updated_at": health["updated_at"], "modules": result})

    @app.route("/api/stats")
    async def api_stats():
        """首页公开统计：服务器数、功能模块数、可用指令数（带 120s 缓存）"""
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
        commands = 0
        try:
            with open(os.path.join(BOT_DIR, "health.json"), encoding="utf-8") as f:
                command_snapshot = json.load(f).get("commands", [])
            if isinstance(command_snapshot, list):
                commands = len(command_snapshot)
        except (OSError, ValueError, TypeError):
            pass
        data = {"servers": servers, "modules": modules, "commands": commands}
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
                result = dict(row)
                result["has_welcome_image"] = bool(
                    result.pop("welcome_image_file", "")
                )
                result["has_farewell_image"] = bool(
                    result.pop("farewell_image_file", "")
                )
                return jsonify(result)
            return jsonify(
                {
                    "guild_id": g,
                    "welcome_channel": 0,
                    "farewell_channel": 0,
                    "auto_roles": "",
                    "welcome_msg": "欢迎 %member% 加入 %server%！🎉",
                    "farewell_msg": "%member% 离开了我们... 👋",
                    "show_card": 0,
                    "welcome_title": "",
                    "author_icon": "",
                    "thumbnail_url": "",
                    "enabled": 1,
                    "image_url": "",
                    "has_welcome_image": False,
                    "has_farewell_image": False,
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
            if not isinstance(d, dict):
                return jsonify({"error": "请求内容必须是 JSON 对象"}), 400
            g = int(gid)
            auto_roles = [x for x in str(d.get("auto_roles", "")).split(",") if x]
            resources = await _validate_guild_resources(
                g,
                channel_ids=[d.get("welcome_channel", 0), d.get("farewell_channel", 0)],
                role_ids=auto_roles,
                assignable_roles=True,
            )
            if resources is None:
                return jsonify({"error": "无法验证服务器资源"}), 502
            if not resources:
                return jsonify({"error": "频道或身份组不属于当前服务器"}), 400
            try:
                author_icon = _normalize_image_url(d.get("author_icon"))
                thumbnail_url = _normalize_image_url(d.get("thumbnail_url"))
                image_url = _normalize_image_url(d.get("image_url"))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
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
                        author_icon,
                        thumbnail_url,
                        1 if d.get("enabled", True) else 0,
                        image_url,
                        g,
                    ),
                )
                await db.commit()
            await _notify_bot("welcome", g)
            actor = await _resolve_actor(discord)
            audit(g, "欢迎模块配置已更新", **{"操作者": actor})
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[api_welcome_post] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route(
        "/api/guild/<string:gid>/welcome/image/<string:kind>",
        methods=["GET", "POST", "DELETE"],
    )
    async def api_welcome_image(gid, kind):
        if kind not in _WELCOME_IMAGE_COLUMNS:
            return jsonify({"error": "图片类型无效"}), 404
        if not await check_guild_access(discord, gid):
            return jsonify({"error": "unauthorized"}), 401
        try:
            g = int(gid)
        except ValueError:
            return jsonify({"error": "服务器 ID 无效"}), 400

        column = _WELCOME_IMAGE_COLUMNS[kind]
        lock = _welcome_upload_locks.setdefault((g, kind), asyncio.Lock())
        async with lock:
            try:
                old_filename = await _welcome_image_filename(g, kind)

                if request.method == "GET":
                    path = _welcome_image_path(old_filename, g, kind)
                    if not path or not os.path.isfile(path) or os.path.islink(path):
                        return jsonify({"error": "尚未上传图片"}), 404
                    suffix = os.path.splitext(path)[1].lower()
                    mime = next(
                        value[1]
                        for value in _WELCOME_IMAGE_FORMATS.values()
                        if value[0] == suffix
                    )
                    response = await send_file(path, mimetype=mime)
                    response.headers["Cache-Control"] = "private, no-store"
                    response.headers["X-Content-Type-Options"] = "nosniff"
                    return response

                if request.method == "DELETE":
                    async with aiosqlite.connect(DB_WELCOME) as db:
                        await db.execute(
                            "INSERT OR IGNORE INTO welcome_config (guild_id) VALUES (?)",
                            (g,),
                        )
                        await db.execute(
                            f"UPDATE welcome_config SET {column}='' WHERE guild_id=?",
                            (g,),
                        )
                        await db.commit()
                    _remove_welcome_image(old_filename, g, kind)
                    await _notify_bot("welcome", g)
                    actor = await _resolve_actor(discord)
                    audit(
                        g,
                        f"{'迎新' if kind == 'welcome' else '道别'}自定义图片已清除",
                        **{"操作者": actor},
                    )
                    return jsonify({"ok": True, "has_image": False})

                files = await request.files
                uploaded = files.get("image")
                if uploaded is None:
                    return jsonify({"error": "请选择一张图片"}), 400
                raw = uploaded.stream.read(_MAX_WELCOME_IMAGE_BYTES + 1)
                try:
                    suffix, mime = _validate_welcome_image(raw, uploaded.mimetype)
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400

                digest = hashlib.sha256(raw).hexdigest()[:16]
                filename = f"{g}-{kind}-{digest}{suffix}"
                path = _welcome_image_path(filename, g, kind)
                if path is None:
                    raise RuntimeError("无法建立安全的图片路径")
                os.makedirs(WELCOME_UPLOAD_DIR, mode=0o750, exist_ok=True)
                temp_path = os.path.join(
                    WELCOME_UPLOAD_DIR,
                    f".{filename}.{os.getpid()}.{time.time_ns()}.tmp",
                )
                try:
                    with open(temp_path, "xb") as handle:
                        handle.write(raw)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temp_path, path)
                    try:
                        os.chmod(path, 0o640)
                    except OSError:
                        pass
                    async with aiosqlite.connect(DB_WELCOME) as db:
                        await db.execute(
                            "INSERT OR IGNORE INTO welcome_config (guild_id) VALUES (?)",
                            (g,),
                        )
                        await db.execute(
                            f"UPDATE welcome_config SET {column}=? WHERE guild_id=?",
                            (filename, g),
                        )
                        await db.commit()
                except Exception:
                    try:
                        if os.path.isfile(temp_path):
                            os.remove(temp_path)
                        if filename != old_filename and os.path.isfile(path):
                            os.remove(path)
                    except OSError:
                        pass
                    raise

                if old_filename != filename:
                    _remove_welcome_image(old_filename, g, kind)
                await _notify_bot("welcome", g)
                actor = await _resolve_actor(discord)
                audit(
                    g,
                    f"{'迎新' if kind == 'welcome' else '道别'}自定义图片已更新",
                    **{"操作者": actor, "大小": f"{len(raw) / 1024:.1f} KB"},
                )
                return jsonify(
                    {
                        "ok": True,
                        "has_image": True,
                        "image_url": f"/api/guild/{g}/welcome/image/{kind}",
                        "size": len(raw),
                        "mime": mime,
                    }
                )
            except Exception:
                print(f"[api_welcome_image] {traceback.format_exc()}")
                return jsonify({"error": "服务器暂时无法处理图片，请稍后重试"}), 500

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
            resources = await _validate_guild_resources(g, channel_ids=[d.get("log_channel", 0)])
            if resources is None:
                return jsonify({"error": "无法验证日志频道"}), 502
            if not resources:
                return jsonify({"error": "日志频道不属于当前服务器"}), 400
            async with aiosqlite.connect(DB_AUTOMOD) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (g,)
                )
                cur = await db.execute(
                    "SELECT ignored_channels, ignored_roles FROM automod_config WHERE guild_id=?",
                    (g,),
                )
                old = await cur.fetchone()
                old_channels = json.loads(old[0] or "[]") if old else []
                old_roles = json.loads(old[1] or "[]") if old else []
                ignored_channels = d.get("ignored_channels", old_channels)
                ignored_roles = d.get("ignored_roles", old_roles)
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
                        json.dumps(ignored_channels, ensure_ascii=False),
                        json.dumps(ignored_roles, ensure_ascii=False),
                        g,
                    ),
                )
                await db.commit()
            await _notify_bot("automod", g)
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
            resources = await _validate_guild_resources(g, channel_ids=[d.get("log_channel", 0)])
            if resources is None:
                return jsonify({"error": "无法验证日志频道"}), 502
            if not resources:
                return jsonify({"error": "日志频道不属于当前服务器"}), 400
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
            await _notify_bot("moderation", g)
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
            resources = await _validate_guild_resources(
                g,
                channel_ids=[d.get("notify_channel", 0)],
                role_ids=[d.get("dj_role", 0)],
            )
            if resources is None:
                return jsonify({"error": "无法验证音乐配置资源"}), 502
            if not resources:
                return jsonify({"error": "频道或身份组不属于当前服务器"}), 400
            async with aiosqlite.connect(DB_MUSIC) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO music_config (guild_id, dj_role, notify_channel) VALUES (?, ?, ?)",
                    (g, int(d.get("dj_role", 0)), int(d.get("notify_channel", 0))),
                )
                await db.commit()
            await _notify_bot("music", g)
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
            resources = await _validate_guild_resources(g, channel_ids=[d.get("channel_id", 0)])
            if resources is None:
                return jsonify({"error": "无法验证日志频道"}), 502
            if not resources:
                return jsonify({"error": "日志频道不属于当前服务器"}), 400
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
            await _notify_bot("botlog", g)
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
            resources = await _validate_guild_resources(g, channel_ids=[d.get("channel_id", 0)])
            if resources is None:
                return jsonify({"error": "无法验证日志频道"}), 502
            if not resources:
                return jsonify({"error": "日志频道不属于当前服务器"}), 400
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
            await _notify_bot("serverlog", g)
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
            runtime = _runtime_health()
            data["state"] = runtime["state"]
            data["online"] = runtime["state"] == "online"
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
        await _notify_bot("global", 0)
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
        await _notify_bot("global", 0)
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
        await _notify_bot("global", 0)
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
        await _notify_bot("global", 0)
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
            await _notify_bot("global", 0)
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
                await _notify_bot("global", 0)
                return jsonify({"ok": True})
            return (
                jsonify({"error": body.get("message", f"Discord API {status}")}),
                status,
            )
        except Exception as e:
            print(f"[api_bot_username] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/bot/avatar", methods=["GET", "POST"])
    async def api_bot_avatar():
        """Read the current bot avatar or explicitly upload a replacement."""
        try:
            if not await is_owner(discord):
                return jsonify({"error": "unauthorized"}), 401
            if request.method == "GET":
                bot_user = await discord_api_get("/users/@me")
                if not isinstance(bot_user, dict) or not bot_user.get("id"):
                    return jsonify({"error": "暂时没能读取小凛的头像，请稍后重试"}), 503
                avatar_url = _bot_avatar_url(bot_user)
                return jsonify({"avatar_url": avatar_url, "is_fallback": avatar_url.startswith("/")})
            d = await request.get_json()
            if not isinstance(d, dict):
                return jsonify({"error": "请求内容必须是 JSON 对象"}), 400
            avatar_b64 = d.get("avatar")  # expects "data:image/png;base64,..."
            if not avatar_b64:
                return jsonify({"error": "missing avatar data"}), 400
            avatar_error = _validate_avatar_data_uri(avatar_b64)
            if avatar_error:
                return jsonify({"error": avatar_error}), 400
            status, body = await discord_api_patch("/users/@me", {"avatar": avatar_b64})
            if status == 200:
                await _notify_bot("global", 0)
                return jsonify({"ok": True, "avatar_url": _bot_avatar_url(body)})
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

            role_ids = [m.get("role_id") for m in mappings_list]
            resources = await _validate_guild_resources(
                gid,
                channel_ids=[channel_id],
                role_ids=role_ids,
                assignable_roles=True,
            )
            if resources is None:
                return jsonify({"error": "无法验证频道或身份组"}), 502
            if not resources:
                return jsonify({"error": "频道或身份组不属于当前服务器"}), 400

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

            await _notify_bot("reactionroles", g)
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

            if len(prize) > 500:
                return jsonify({"error": "奖品描述最多 500 个字符"}), 400
            if winners_count < 1 or winners_count > 20:
                return jsonify({"error": "中奖人数范围为 1-20"}), 400

            resources = await _validate_guild_resources(
                gid, channel_ids=[channel_id], role_ids=[restrict_role]
            )
            if resources is None:
                return jsonify({"error": "无法验证抽奖资源"}), 502
            if not resources:
                return jsonify({"error": "频道或身份组不属于当前服务器"}), 400

            if end_time <= time.time():
                return jsonify({"error": "结束时间必须在未来"}), 400
            if end_time > time.time() + 365 * 86400:
                return jsonify({"error": "抽奖最长可以设置 365 天"}), 400

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
                "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time, restrict_role) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        g,
                        int(channel_id),
                        int(message_id),
                        host_id,
                        prize,
                        winners_count,
                        end_time,
                        int(restrict_role or 0),
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
        {"name": "search", "desc": "搜索歌曲并选择播放", "cog": "Music"},
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
        {"name": "saveq", "desc": "保存当前播放队列", "cog": "Music"},
        {"name": "loadq", "desc": "载入播放队列存档", "cog": "Music"},
        {"name": "queues", "desc": "查看播放队列存档", "cog": "Music"},
        {"name": "delqueue", "desc": "删除播放队列存档", "cog": "Music"},
        {"name": "rank", "desc": "查看你的等级卡片", "cog": "Leveling"},
        {"name": "leaderboard", "desc": "查看服务器等级排行榜", "cog": "Leveling"},
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
        {"name": "modlog_channel", "desc": "设置管理日志频道", "cog": "Moderation"},
        {"name": "warn_config", "desc": "配置警告自动处罚阈值", "cog": "Moderation"},
        {"name": "status", "desc": "显示服务器详细状态", "cog": "General"},
        {"name": "roll", "desc": "投掷骰子 (默认6面)", "cog": "General"},
        {"name": "avatar", "desc": "查看用户的大图头像", "cog": "General"},
        {"name": "setstatus", "desc": "修改机器人的活动状态", "cog": "General"},
        {"name": "resetstatus", "desc": "重置机器人状态", "cog": "General"},
        {"name": "setbio", "desc": "修改机器人的简介", "cog": "General"},
        {"name": "welcome_setup", "desc": "配置迎新和道别系统", "cog": "Welcome"},
        {"name": "welcome_test", "desc": "测试欢迎图卡效果", "cog": "Welcome"},
        {"name": "welcome_message", "desc": "自定义欢迎/道别消息", "cog": "Welcome"},
        {"name": "welcome_toggle", "desc": "开启或关闭欢迎模块", "cog": "Welcome"},
        {"name": "welcome_image", "desc": "设置欢迎大图", "cog": "Welcome"},
        {"name": "welcome_title", "desc": "设置欢迎卡标题", "cog": "Welcome"},
        {"name": "welcome_icon", "desc": "设置欢迎标题图标", "cog": "Welcome"},
        {"name": "welcome_thumbnail", "desc": "设置欢迎缩略图", "cog": "Welcome"},
        {"name": "welcome_card", "desc": "开启或关闭欢迎卡片", "cog": "Welcome"},
        {"name": "welcome_disable", "desc": "禁用迎新与道别系统", "cog": "Welcome"},
        {"name": "rr_create", "desc": "创建反应身份组面板", "cog": "ReactionRoles"},
        {"name": "rr_add", "desc": "添加 emoji → 身份组映射", "cog": "ReactionRoles"},
        {"name": "rr_remove", "desc": "移除一个 emoji 映射", "cog": "ReactionRoles"},
        {"name": "rr_list", "desc": "列出所有面板", "cog": "ReactionRoles"},
        {"name": "rr_exclusive", "desc": "切换面板的单选/多选模式", "cog": "ReactionRoles"},
        {"name": "rr_delete", "desc": "删除面板", "cog": "ReactionRoles"},
        {"name": "giveaway", "desc": "抽奖管理 (start/end/reroll)", "cog": "Giveaway"},
        {"name": "automod", "desc": "自动审核配置面板", "cog": "AutoMod"},
        {"name": "automod_words", "desc": "管理违禁词列表", "cog": "AutoMod"},
        {"name": "automod_whitelist", "desc": "管理链接白名单", "cog": "AutoMod"},
        {"name": "automod_ignore", "desc": "管理审核忽略列表", "cog": "AutoMod"},
        {"name": "serverlog", "desc": "配置服务器审计日志", "cog": "ServerLog"},
        {"name": "toggle", "desc": "启用/禁用指定指令", "cog": "System"},
        {"name": "togglelist", "desc": "查看已禁用的指令", "cog": "System"},
        {"name": "help", "desc": "打开交互式指令菜单", "cog": "System"},
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
    def _current_command_registry():
        """Prefer the Bot's live command snapshot, with the static list as fallback."""
        try:
            with open(os.path.join(BOT_DIR, "health.json"), encoding="utf-8") as f:
                commands = json.load(f).get("commands")
            if not isinstance(commands, list) or not commands:
                raise ValueError("missing command snapshot")
            cleaned = []
            seen = set()
            for item in commands:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not isinstance(name, str) or not name or name in seen:
                    continue
                seen.add(name)
                cleaned.append(
                    {
                        "name": name,
                        "desc": str(item.get("desc") or "暂无介绍")[:200],
                        "cog": str(item.get("cog") or "Other")[:50],
                    }
                )
            if cleaned:
                return cleaned
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return COMMAND_REGISTRY

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
            for cmd in _current_command_registry():
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
            if not isinstance(d, dict):
                return jsonify({"error": "请求格式无效"}), 400
            name = (d.get("name") or "").strip()
            enabled = d.get("enabled", True)
            if not isinstance(enabled, bool):
                return jsonify({"error": "启用状态格式无效"}), 400
            command_names = {item["name"] for item in _current_command_registry()}
            if name not in command_names:
                return jsonify({"error": "未知指令"}), 400
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
            await _notify_bot("commands", g)
            actor = await _resolve_actor(discord)
            action = "启用" if enabled else "禁用"
            audit(g, f"{action}了指令", **{"操作者": actor, "指令": f"/{name}"})
            return jsonify({"ok": True, "name": name, "enabled": enabled})
        except Exception as e:
            print(f"[api_commands_toggle] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/guild/<string:gid>/commands/bulk-toggle", methods=["POST"])
    async def api_commands_bulk_toggle(gid):
        """Update a command group in one database transaction."""
        try:
            if not await check_guild_access(discord, gid):
                return jsonify({"error": "unauthorized"}), 401
            d = await request.get_json()
            if not isinstance(d, dict):
                return jsonify({"error": "请求格式无效"}), 400
            names = d.get("names")
            enabled = d.get("enabled")
            if not isinstance(names, list) or not names or len(names) > 100:
                return jsonify({"error": "指令列表格式无效"}), 400
            if not isinstance(enabled, bool):
                return jsonify({"error": "启用状态格式无效"}), 400

            if any(not isinstance(name, str) or not name for name in names):
                return jsonify({"error": "指令名格式无效"}), 400
            names = list(dict.fromkeys(names))
            command_names = {item["name"] for item in _current_command_registry()}
            unknown = [name for name in names if name not in command_names]
            protected = [name for name in names if name in PROTECTED]
            if unknown:
                return jsonify({"error": f"未知指令: {', '.join(unknown)}"}), 400
            if protected:
                return jsonify(
                    {"error": f"核心指令不能被禁用: {', '.join(protected)}"}
                ), 400

            g = int(gid)
            async with aiosqlite.connect(DB_CMDTOGGLE) as db:
                if enabled:
                    await db.executemany(
                        "DELETE FROM disabled_commands WHERE guild_id=? AND command_name=?",
                        [(g, name) for name in names],
                    )
                else:
                    await db.executemany(
                        "INSERT OR IGNORE INTO disabled_commands (guild_id, command_name) VALUES (?, ?)",
                        [(g, name) for name in names],
                    )
                await db.commit()

            await _notify_bot("commands", g)
            actor = await _resolve_actor(discord)
            action = "启用" if enabled else "禁用"
            audit(
                g,
                f"批量{action}了指令",
                **{"操作者": actor, "指令": ", ".join(f"/{name}" for name in names)},
            )
            return jsonify({"ok": True, "names": names, "enabled": enabled})
        except Exception as e:
            print(f"[api_commands_bulk_toggle] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500
