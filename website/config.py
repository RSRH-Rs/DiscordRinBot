import os
import datetime

# 仅在本地明确允许时使用 HTTP；生产环境必须通过 HTTPS 访问 OAuth。
if os.getenv("RINBOT_ALLOW_HTTP", "0") == "1":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
# 机器人主人的 Discord 用户 ID（用于网页「全局设置」owner-only 权限）
OWNER_ID = 0  # ← 改成你自己的 Discord 用户 ID
BOT_TOKEN = ""


class Config:
    SECRET_KEY = os.getenv("RINBOT_SECRET_KEY", "")

    DISCORD_CLIENT_ID = 0
    DISCORD_CLIENT_SECRET = ""
    DISCORD_REDIRECT_URI = ""

    SESSION_COOKIE_SECURE = os.getenv("RINBOT_COOKIE_SECURE", "1") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "rinbot_session"

    PERMANENT_SESSION_LIFETIME = datetime.timedelta(hours=2)
