# cogs/general.py
import discord
from discord.ext import commands
import platform
import psutil
import time
import datetime
import random
from typing import Literal


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="status", aliases=["stat", "info"], description="显示服务器详细状态"
    )
    async def status(self, ctx):
        # 获取 main.py 里 bot 实例的数据
        latency = round(self.bot.latency * 1000, 2)
        current_time = time.time()

        # 确保 bot 有 start_time 属性
        if hasattr(self.bot, "start_time"):
            uptime_seconds = int(current_time - self.bot.start_time)
            uptime = str(datetime.timedelta(seconds=uptime_seconds))
        else:
            uptime = "未知"

        cpu_usage = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        os_info = f"{platform.system()} {platform.release()}"

        embed = discord.Embed(title="📊 服务器状态监控", color=discord.Color.random())
        embed.add_field(name="📶 延迟 (Ping)", value=f"`{latency} ms`", inline=True)
        embed.add_field(name="⏱️ 运行时间", value=f"`{uptime}`", inline=True)
        embed.add_field(
            name="🌐 服务群组", value=f"`{len(self.bot.guilds)} 个服务器`", inline=True
        )
        embed.add_field(name="💻 CPU 使用率", value=f"`{cpu_usage}%`", inline=True)
        embed.add_field(
            name="🧠 内存使用",
            value=f"`{memory.percent}%` ({round(memory.used/1024/1024/1024, 1)}GB / {round(memory.total/1024/1024/1024, 1)}GB)",
            inline=True,
        )
        embed.add_field(name="💾 磁盘使用", value=f"`{disk.percent}%`", inline=True)
        embed.add_field(name="🖥️ 操作系统", value=f"`{os_info}`", inline=False)
        embed.set_footer(
            text=f"请求者: {ctx.author.name}", icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="roll", aliases=["dice", "touzi"], description="投掷骰子 (默认6面)"
    )
    async def roll(self, ctx, sides: int = 6):
        if sides < 2:
            await ctx.send("❌ 骰子至少要有 2 个面！")
            return
        result = random.randint(1, sides)
        await ctx.send(f"🎲 你掷出了一个 **{sides}** 面骰子，结果是：**{result}**")

    @commands.hybrid_command(
        name="avatar", aliases=["av"], description="查看用户的大图头像"
    )
    async def avatar(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        embed = discord.Embed(
            title=f"{target.name} 的头像", color=discord.Color.random()
        )
        embed.set_image(url=target.display_avatar.url)

        button = discord.ui.Button(
            label="Full size", url=target.display_avatar.url, emoji="🖼️"
        )
        view = discord.ui.View()
        view.add_item(button)

        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(
        name="setstatus", description="[Owner] 修改机器人的活动状态"
    )
    @commands.is_owner()
    async def setstatus(
        self,
        ctx,
        type: Literal["Playing", "Watching", "Listening", "Competing", "Custom"],
        *,
        text: str,
    ):
        """
        type: 状态类型 (Custom = 纯文字状态)
        text: 显示的内容
        """
        await ctx.defer()

        activity = None

        if type == "Playing":
            activity = discord.Game(name=text)
        elif type == "Watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        elif type == "Listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=text)
        elif type == "Competing":
            activity = discord.Activity(type=discord.ActivityType.competing, name=text)
        elif type == "Custom":
            # 👇 这里就是纯文字状态的关键
            activity = discord.CustomActivity(name=text)

        await self.bot.change_presence(status=discord.Status.online, activity=activity)

        await ctx.send(f"✅ 状态已更新为: **{type} {text}**")

    @commands.hybrid_command(name="resetstatus", description="[Owner] 重置/清除状态")
    @commands.is_owner()
    async def resetstatus(self, ctx):
        await self.bot.change_presence(activity=None, status=discord.Status.online)
        await ctx.send("✅ 状态已重置")

    @commands.hybrid_command(
        name="setbio", description="[Owner] 修改机器人的简介 (About Me)"
    )
    @commands.is_owner()
    async def setbio(self, ctx, *, text: str):
        """
        text: 新的简介内容
        """
        await ctx.defer()

        try:
            # 确保获取到应用信息
            if not self.bot.application:
                await self.bot.application_info()

            # 修改 Application 的 description
            await self.bot.application.edit(description=text)

            embed = discord.Embed(
                title="✅ 简介更新成功", description=text, color=discord.Color.green()
            )
            await ctx.send(embed=embed)

        except discord.HTTPException as e:
            await ctx.send(f"❌ 更新失败: {e}")
        except Exception as e:
            await ctx.send(f"❌ 发生错误: {e}")


async def setup(bot):
    await bot.add_cog(General(bot))