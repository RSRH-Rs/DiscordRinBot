import os

from quart import Quart
from quart_discord import DiscordOAuth2Session
from config import Config
from routes import setup_routes

app = Quart(__name__)
app.config.from_object(Config)

# 打印关键配置用于调试 (生产环境删除)
print(f"[Config] SECRET_KEY 长度: {len(app.config.get('SECRET_KEY', ''))}")
print(f"[Config] CLIENT_ID: {app.config.get('DISCORD_CLIENT_ID', '未设置')}")
print(f"[Config] REDIRECT_URI: {app.config.get('DISCORD_REDIRECT_URI', '未设置')}")
print(
    f"[Config] COOKIE_SAMESITE: {app.config.get('SESSION_COOKIE_SAMESITE', '未设置')}"
)
print(f"[Config] COOKIE_SECURE: {app.config.get('SESSION_COOKIE_SECURE', '未设置')}")

discord_oauth = DiscordOAuth2Session(app)
setup_routes(app, discord_oauth)

if __name__ == "__main__":
    app.run(
        host=os.getenv("RINBOT_WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("RINBOT_WEB_PORT", "5000")),
        debug=os.getenv("RINBOT_DEBUG", "0") == "1",
    )
