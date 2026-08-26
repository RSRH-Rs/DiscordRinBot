# cogs/health.py
# 定时把 bot 运行状态写入 health.json，供网页「全局设置」健康面板读取
# （bot 与网站是两个进程，靠这个共享文件传递状态）

import discord
from discord.ext import commands, tasks
import json
import os
import time
import platform

HEALTH_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "health.json"
)


class Health(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.started_at = time.time()

    async def cog_load(self):
        if not self._write.is_running():
            self._write.start()

    def cog_unload(self):
        self._write.cancel()

    def _command_snapshot(self) -> list[dict]:
        """Export the real top-level command list for the web dashboard."""
        cog_labels = {"CommandToggle": "System", "Help": "System"}
        hidden_cogs = {"Dev", "BotConfig", "MusicConfig"}
        result = []
        for command in self.bot.commands:
            cog_name = command.cog_name or "Other"
            if command.hidden or cog_name in hidden_cogs:
                continue
            result.append(
                {
                    "name": command.name,
                    "desc": command.description or "暂无介绍",
                    "cog": cog_labels.get(cog_name, cog_name),
                }
            )
        return sorted(result, key=lambda item: (item["cog"], item["name"]))

    @tasks.loop(seconds=30)
    async def _write(self):
        try:
            lat = self.bot.latency  # 未连接时为 nan
            latency_ms = (
                round(lat * 1000)
                if lat and lat == lat and lat != float("inf")
                else None
            )
            data = {
                "started_at": self.started_at,
                "updated_at": time.time(),
                "gateway_connected": self.bot.is_ready() and not self.bot.is_closed(),
                "guild_ids": [str(g.id) for g in self.bot.guilds],
                "latency_ms": latency_ms,
                "guild_count": len(self.bot.guilds),
                "user_count": sum((g.member_count or 0) for g in self.bot.guilds),
                "cogs": sorted(self.bot.cogs.keys()),
                "commands": self._command_snapshot(),
                "py": platform.python_version(),
                "dpy": discord.__version__,
            }
            temp_path = HEALTH_PATH + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(temp_path, HEALTH_PATH)
        except Exception as e:
            print(f"[health] 写入失败: {e}")

    @_write.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Health(bot))
