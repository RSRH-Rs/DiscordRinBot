# cogs/general.py
import discord
from discord import app_commands
from discord.ext import commands
from _perms import owner_only
from _messages import embed
import aiosqlite
import time
import random
import os
from typing import Literal

BOTCONFIG_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botconfig.db"
)


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="status", aliases=["stat", "info"], description="Show how the bot is doing"
    )
    async def status(self, ctx):
        # 只给机器人自己的状态；主机的 CPU、内存、磁盘不对外公开
        card = embed(
            "info",
            "小凛的运行状态",
            fields=[
                ("延迟", f"{round(self.bot.latency * 1000)} 毫秒"),
                ("上次启动", f"<t:{int(self.bot.start_time)}:R>"),
                ("服务器", f"{len(self.bot.guilds)} 个"),
            ],
        )
        await ctx.send(embed=card)

    @commands.hybrid_command(
        name="roll", aliases=["dice", "touzi"], description="Roll a die"
    )
    @app_commands.describe(sides="How many sides, 2-1000; default 6")
    async def roll(self, ctx, sides: commands.Range[int, 2, 1000] = 6):
        result = random.randint(1, sides)
        await ctx.send(f"🎲 你掷出了一个 **{sides}** 面骰子，结果是：**{result}**")

    @commands.hybrid_command(
        name="avatar", aliases=["av"], description="Show someone's avatar in full size"
    )
    @app_commands.describe(member="Whose avatar; default yours")
    async def avatar(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        card = embed("info", f"{target.name} 的头像")
        card.set_image(url=target.display_avatar.url)

        button = discord.ui.Button(label="查看原图", url=target.display_avatar.url)
        view = discord.ui.View()
        view.add_item(button)

        await ctx.send(embed=card, view=view)

    @commands.hybrid_command(
        name="setstatus", description="[Owner] 修改机器人的活动状态"
    )
    @owner_only()
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

        atype_map = {
            "Playing": "playing",
            "Watching": "watching",
            "Listening": "listening",
            "Competing": "competing",
            "Custom": "custom",
        }
        atype = atype_map[type]

        # 写 DB,botconfig 是唯一管 presence 的人
        async with aiosqlite.connect(BOTCONFIG_DB) as db:
            await db.execute("INSERT OR IGNORE INTO bot_personalizer (id) VALUES (1)")
            await db.execute(
                "UPDATE bot_personalizer SET activity_type=?, activity_text=?, updated_at=? WHERE id=1",
                (atype, text, time.time()),
            )
            await db.commit()

        # 立刻触发 botconfig 重新读取(不用等同步回调)
        botcfg = self.bot.get_cog("BotConfig")
        if botcfg:
            botcfg._last_hash = None
            await botcfg.apply_presence()

        await ctx.send(f"✅ 状态已更新为: **{type} {text}**")

    @commands.hybrid_command(name="resetstatus", description="[Owner] 重置/清除状态")
    @owner_only()
    async def resetstatus(self, ctx):
        async with aiosqlite.connect(BOTCONFIG_DB) as db:
            await db.execute("INSERT OR IGNORE INTO bot_personalizer (id) VALUES (1)")
            await db.execute(
                "UPDATE bot_personalizer SET activity_type='none', activity_text='', updated_at=? WHERE id=1",
                (time.time(),),
            )
            await db.commit()

        botcfg = self.bot.get_cog("BotConfig")
        if botcfg:
            botcfg._last_hash = None
            await botcfg.apply_presence()

        await ctx.send("✅ 状态已重置")

    @commands.hybrid_command(
        name="setbio", description="[Owner] 修改机器人的简介 (About Me)"
    )
    @owner_only()
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

            await ctx.send(embed=embed("success", "简介已更新", text))

        except discord.HTTPException as e:
            await ctx.send(f"❌ 更新失败: {e}")
        except Exception as e:
            await ctx.send(f"❌ 发生错误: {e}")


async def setup(bot):
    await bot.add_cog(General(bot))
