import os

from quart import Quart, request
from quart_discord import DiscordOAuth2Session
from config import Config
from routes import setup_routes


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


app = Quart(__name__)
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("RINBOT_MAX_CONTENT_LENGTH", str(8 * 1024 * 1024))
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _env_bool("RINBOT_COOKIE_SECURE", True)


@app.after_request
async def add_security_headers(response):
    """Apply browser hardening without breaking the existing inline UI."""
    headers = response.headers
    headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    headers.setdefault(
        "Content-Security-Policy",
        "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
    )
    headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    if request.path.startswith(("/dashboard", "/api/guild/", "/api/bot/")):
        headers.setdefault("Cache-Control", "no-store")
    return response

discord_oauth = DiscordOAuth2Session(app)
setup_routes(app, discord_oauth)

if __name__ == "__main__":
    app.run(
        host=os.getenv("RINBOT_WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("RINBOT_WEB_PORT", "5000")),
        debug=os.getenv("RINBOT_DEBUG", "0") == "1",
    )
