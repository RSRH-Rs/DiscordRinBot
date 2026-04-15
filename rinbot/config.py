TOKEN = BOT_TOKEN = ""

# 开发/测试服务器 ID
DEV_GUILD_ID = 0  # ← 改成你的服务器 ID

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
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
