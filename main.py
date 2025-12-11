import discord
from discord.ext import commands
import platform
import psutil
import time
import datetime
from config import TOKEN
import random
from discord import app_commands
TEST_GUILD_ID = discord.Object(id=0) # 填入你的测试服务器ID

class HybridBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix='r!', 
            intents=intents,
            help_command=None 
        )
        self.start_time = None 

    async def setup_hook(self):
        self.tree.copy_global_to(guild=TEST_GUILD_ID)
        await self.tree.sync(guild=TEST_GUILD_ID)

    async def on_ready(self):
        if self.start_time is None:
            self.start_time = time.time()
        print(f'Login: {self.user} (ID: {self.user.id})')

bot = HybridBot()

# --- Hybrid Command ---
@bot.hybrid_command(name="status",aliases=["stat", "info", "s"], description="显示服务器详细状态")
async def status(ctx):
    # Ping
    latency = round(bot.latency * 1000, 2)
    
    # Uptime
    current_time = time.time()
    uptime_seconds = int(current_time - bot.start_time)
    uptime = str(datetime.timedelta(seconds=uptime_seconds))
    
    # Sys infos
    cpu_usage = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # OS
    os_info = f"{platform.system()} {platform.release()}"
    
    # Embed
    embed = discord.Embed(title="📊 服务器状态监控", color=discord.Color.random())
    
    embed.add_field(name="📶 延迟 (Ping)", value=f"`{latency} ms`", inline=True)
    embed.add_field(name="⏱️ 运行时间", value=f"`{uptime}`", inline=True)
    embed.add_field(name="🌐 服务群组", value=f"`{len(bot.guilds)} 个服务器`", inline=True)
    
    embed.add_field(name="💻 CPU 使用率", value=f"`{cpu_usage}%`", inline=True)
    embed.add_field(name="🧠 内存使用", value=f"`{memory.percent}%` ({round(memory.used/1024/1024/1024, 1)}GB / {round(memory.total/1024/1024/1024, 1)}GB)", inline=True)
    embed.add_field(name="💾 磁盘使用", value=f"`{disk.percent}%`", inline=True)
    
    embed.add_field(name="🖥️ 操作系统", value=f"`{os_info}`", inline=False)
    
    # Footer
    embed.set_footer(text=f"请求者: {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="roll", aliases=["dice", "touzi","r"], description="投掷骰子 (默认6面)")
async def roll(ctx, sides: int = 6):
    if sides < 2:
        await ctx.send("❌ 骰子至少要有 2 个面！")
        return

    result = random.randint(1, sides)
    
    await ctx.send(f"🎲 你掷出了一个 **{sides}** 面骰子，结果是：**{result}**")

@bot.hybrid_command(name="avatar", aliases=["av" ], description="查看用户的大图头像")
async def avatar(ctx, member: discord.Member = None):
    target = member or ctx.author
    
    embed = discord.Embed(title=f"{target.name} 的头像", color=discord.Color.random())
    embed.set_image(url=target.display_avatar.url)
    
    # 创建按钮
    # label: 按钮上的字
    # url: 点击后跳转的地址
    # emoji: 按钮前面的图标
    button = discord.ui.Button(
        label="Full size", 
        url=target.display_avatar.url, 
        emoji="🖼️" 
    )
    
    view = discord.ui.View()
    view.add_item(button)
    
    await ctx.send(embed=embed, view=view)







bot.run(TOKEN)