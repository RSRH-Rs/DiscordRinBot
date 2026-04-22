import os
import datetime

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Bot token — used to check which guilds Rin has already joined
BOT_TOKEN = "MTM1MjU1MTYxNjQyNzA2OTQ5Mg.GQckPy.yn7XYEt1gMxDfcsI_yDWJMqGcAoABTAWOw_XFo"


class Config:
    # Must be a plain STRING (not bytes b"...") — bytes breaks itsdangerous → CSRF
    SECRET_KEY = "rin_dashboard_secret_2026_xK9mPq"

    DISCORD_CLIENT_ID = 1352551616427069492
    DISCORD_CLIENT_SECRET = "HEK1epA0C3DADVWxbJBFz2uWEKL3IYr8"
    DISCORD_REDIRECT_URI = "https://rin-bot.com/callback"

    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "rin_session"

    # ⚠️ KEY FIX: make sessions permanent so the cookie survives the OAuth redirect
    # Without this, the session (and OAuth state) is lost when Discord redirects back
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(hours=2)
