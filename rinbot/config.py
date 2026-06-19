TOKEN = BOT_TOKEN = ""

# 开发/测试服务器 ID
DEV_GUILD_ID = 0  # ← 改成你的服务器 ID

# 机器人主人的 Discord 用户 ID（用于网页「全局设置」owner-only 权限）
OWNER_ID = 0  # ← 改成你自己的 Discord 用户 ID

# Spotify 链接支持（留空则禁用，需 pip install spotipy）
SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "default_search": "auto",
    "quiet": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "no_warnings": True,
    "source_address": "0.0.0.0",
    "extract_flat": False,
    # 走 android/ios 客户端，多数情况直接拿到直链、跳过 CPU 密集的签名破解（弱 ARM 提升明显）
    "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
