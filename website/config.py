import os
import datetime

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = ""

# Bot token — used to check which guilds Rin has already joined
BOT_TOKEN = ""


class Config:
    # Must be a plain STRING (not bytes b"...") — bytes breaks itsdangerous → CSRF
    SECRET_KEY = ""

    DISCORD_CLIENT_ID = 0
    DISCORD_CLIENT_SECRET = ""
    DISCORD_REDIRECT_URI = ""

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = ""
    SESSION_COOKIE_NAME = ""

    PERMANENT_SESSION_LIFETIME = datetime.timedelta(hours=2)
