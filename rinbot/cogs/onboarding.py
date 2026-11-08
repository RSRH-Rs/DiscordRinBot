# cogs/onboarding.py
# 机器人加入服务器时在一个能发言的频道发一张问候卡，按钮指向该服务器的控制台

import discord
from discord.ext import commands

from rincore import guild_config
from _inputs import ZH_LOCALES
import _messages

DASHBOARD_URL = "https://rin-bot.com/dashboard/server/{guild_id}"

COPY = {
    "zh": ("小凛来了",
           "我能放歌、迎新、拦刷屏和记日志。打开控制台，想用哪个就开哪个。",
           "打开控制台"),
    "en": ("Rin is here",
           "I play music, welcome new members, stop spam and keep logs. "
           "Open the dashboard and turn on what you need.",
           "Open dashboard"),
}


def pick_channel(guild):
    """系统频道优先，其次按位置排序的文字频道；取第一个能看、能发言、能发嵌入的。"""
    me = guild.me
    if me is None:
        return None
    candidates = []
    if guild.system_channel is not None:
        candidates.append(guild.system_channel)
    candidates += [c for c in sorted(guild.text_channels, key=lambda c: c.position)
                   if c is not guild.system_channel]
    for ch in candidates:
        p = ch.permissions_for(me)
        if p.view_channel and p.send_messages and p.embed_links:
            return ch
    return None


def build_greeting(guild):
    title, description, label = COPY["zh" if guild.preferred_locale in ZH_LOCALES else "en"]
    card = _messages.embed("info", title=title, description=description)
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label=label, url=DASHBOARD_URL.format(guild_id=guild.id)))
    return card, view


class Onboarding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        try:
            if await guild_config.has_config(guild.id):
                return
        except Exception as e:
            print(f"[onboarding] 查询服务器 {guild.id} 的配置失败: {e!r}")
            return
        channel = pick_channel(guild)
        if channel is None:
            print(f"[onboarding] 服务器 {guild.id} 没有可发问候的频道")
            return
        card, view = build_greeting(guild)
        try:
            await channel.send(embed=card, view=view,
                               allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            print(f"[onboarding] 向服务器 {guild.id} 发送问候失败: {e!r}")


async def setup(bot):
    await bot.add_cog(Onboarding(bot))
