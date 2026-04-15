import os

# 开发环境允许 HTTP (生产环境删掉这行，用 HTTPS)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

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
    app.run(host='0.0.0.0', port=5000, debug=True)
