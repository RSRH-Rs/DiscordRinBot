import os
import datetime

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
# 机器人主人的 Discord 用户 ID（用于网页「全局设置」owner-only 权限）
OWNER_ID = 0  # ← 改成你自己的 Discord 用户 ID
BOT_TOKEN = ""


class Config:
    SECRET_KEY = ""

    DISCORD_CLIENT_ID = 0
    DISCORD_CLIENT_SECRET = ""
    DISCORD_REDIRECT_URI = ""

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = ""

    PERMANENT_SESSION_LIFETIME = datetime.timedelta(hours=2)
