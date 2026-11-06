# cogs/guildcleanup.py
# 机器人被移出服务器满 30 天后自动删除该服务器的数据；30 天内重新邀请则全部保留
# 具体删哪些表、哪些文件见 rincore/guild_cleanup.py

from discord.ext import commands, tasks
from rincore import guild_cleanup


class GuildCleanup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self._daily.is_running():
            self._daily.start()

    def cog_unload(self):
        self._daily.cancel()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        try:
            await guild_cleanup.mark_removed(guild.id)
        except Exception as e:
            print(f"[guild_cleanup] 记录服务器 {guild.id} 被移出失败: {e!r}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        try:
            await guild_cleanup.clear_removed(guild.id)
        except Exception as e:
            print(f"[guild_cleanup] 清除服务器 {guild.id} 的待删记录失败: {e!r}")

    async def run_once(self):
        """先按机器人现在所在的服务器校正待删记录（离线时错过的移出 / 重新邀请），再删到期的。"""
        await guild_cleanup.reconcile(g.id for g in self.bot.guilds)
        await guild_cleanup.purge_due()

    @tasks.loop(hours=24)
    async def _daily(self):
        try:
            await self.run_once()
        except Exception as e:
            print(f"[guild_cleanup] 定时清理失败: {e!r}")

    @_daily.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GuildCleanup(bot))
