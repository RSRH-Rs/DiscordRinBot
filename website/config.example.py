import os
import datetime

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

BOT_TOKEN = ""  # same token as rinbot/config.py
OWNER_ID = 0
# 隐私政策和服务条款里写的联系邮箱（删除数据的请求发到这里）；留空就改为指向 GitHub issues
CONTACT_EMAIL = ""

class Config:
    # Must be a plain STRING (not bytes b"...") — bytes breaks itsdangerous → CSRF
    SECRET_KEY = ""

    DISCORD_CLIENT_ID = 0
    DISCORD_CLIENT_SECRET = ""
    DISCORD_REDIRECT_URI = "https://your-domain/callback"

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "rinbot_session"

    # ⚠️ KEY FIX: make sessions permanent so the cookie survives the OAuth redirect
    # Without this, the session (and OAuth state) is lost when Discord redirects back
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(hours=2)
