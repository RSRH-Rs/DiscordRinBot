# ⚠️ 重要安全提示：你的 Bot Token 已泄露！
# 此 Token 已出现在公开对话中，请立即前往 Discord Developer Portal 重置它。
# https://discord.com/developers/applications
# 重置后将新 Token 粘贴到下方。

TOKEN = BOT_TOKEN = "MTM1MjU1MTYxNjQyNzA2OTQ5Mg.GQckPy.yn7XYEt1gMxDfcsI_yDWJMqGcAoABTAWOw_XFo"

# 开发/测试服务器 ID
DEV_GUILD_ID = 706994968840896552  # ← 改成你的服务器 ID

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'auto',
    'quiet': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'no_warnings': True,
    'source_address': '0.0.0.0',
    'extract_flat': False,
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
