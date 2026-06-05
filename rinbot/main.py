# main.py
import discord
from discord.ext import commands
import os
import sys
import time
from config import TOKEN

# cogs/ 里的辅助模块（如 _botlog_helper）用绝对导入，需把 cogs 目录加进 sys.path
COGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cogs")
if COGS_DIR not in sys.path:
    sys.path.insert(0, COGS_DIR)


class HybridBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # 必须：迎新/道别系统需要成员事件

        super().__init__(command_prefix="r!", intents=intents, help_command=None)
        self.start_time = time.time()

    async def setup_hook(self):
        print("--- 开始加载插件 ---")
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print(f"✅ 已加载: {filename}")
                except Exception as e:
                    print(f"❌ 加载失败 {filename}: {e}")
        print("--- 插件加载完毕 ---")

    async def on_ready(self):
        print(f"Login: {self.user} (ID: {self.user.id})")
        print(f"已连接到 {len(self.guilds)} 个服务器")
        print("Bot is ready and running!")

        activity = discord.Activity(
            type=discord.ActivityType.watching, name="正在偷看你的聊天记录|rin-bot.com"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)


bot = HybridBot()

# hot_update / clear_commands / sync 等开发者指令已全部移至 cogs/dev.py
# 不要在这里重复定义，否则会产生 CommandRegistrationError

bot.run(TOKEN)
