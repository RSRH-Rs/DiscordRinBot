import discord
from discord.ext import commands
from discord.ui import Select, View

# Cog 元数据(emoji + 描述)— 没列在这的 cog 会被隐藏
COG_META = {
    "Music": {
        "emoji": "🎵",
        "label": "音乐系统",
        "desc": "队列、歌单/Spotify、循环、存读队列",
    },
    "Leveling": {
        "emoji": "🏆",
        "label": "等级系统",
        "desc": "聊天累积经验、精美等级卡",
    },
    "Welcome": {"emoji": "👋", "label": "迎新道别", "desc": "欢迎图卡、自动身份组"},
    "ReactionRoles": {
        "emoji": "🏷️",
        "label": "领取身份组",
        "desc": "成员点按钮自助拿角色",
    },
    "AutoMod": {"emoji": "🛡️", "label": "自动审核", "desc": "反刷屏、违禁词、链接过滤"},
    "Moderation": {
        "emoji": "⚖️",
        "label": "管理工具",
        "desc": "kick / ban / mute / warn / purge",
    },
    "Giveaway": {"emoji": "🎉", "label": "抽奖管理", "desc": "倒计时自动开奖,公正透明"},
    "CommandToggle": {
        "emoji": "🔘",
        "label": "指令开关",
        "desc": "按需启用/禁用每个指令",
    },
    "BotLog": {"emoji": "📜", "label": "系统日志", "desc": "Bot 活动转发到指定频道"},
    "ServerLog": {
        "emoji": "🗃️",
        "label": "审计日志",
        "desc": "消息/成员/频道/身份组/封禁记录",
    },
    "General": {
        "emoji": "🛠️",
        "label": "通用工具",
        "desc": "status / avatar / roll 等",
    },
}

# 隐藏:开发者 cog / 纯后台 cog
HIDDEN_COGS = {"Help", "Dev", "BotConfig", "MusicConfig"}


def _format_command(cmd) -> str:
    desc = cmd.description or "暂无介绍"
    return f"**`/{cmd.qualified_name}`** — {desc}"


def _collect_commands(cog) -> list:
    """收集 cog 下所有可见命令(展开 hybrid group 的子命令)"""
    lines = []
    for cmd in cog.get_commands():
        if cmd.hidden:
            continue
        if isinstance(cmd, commands.HybridGroup) or isinstance(cmd, commands.Group):
            for sub in cmd.commands:
                if not sub.hidden:
                    lines.append(_format_command(sub))
        else:
            lines.append(_format_command(cmd))
    return lines


class HelpDropdown(Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label="🏠 首页", description="回到功能概览", value="home"
            )
        ]

        for cog_name, meta in COG_META.items():
            if cog_name in HIDDEN_COGS:
                continue
            cog = bot.get_cog(cog_name)
            if not cog:
                continue
            if not _collect_commands(cog):
                continue
            options.append(
                discord.SelectOption(
                    label=meta["label"],
                    description=meta["desc"][:100],
                    value=cog_name,
                    emoji=meta["emoji"],
                )
            )

        super().__init__(
            placeholder="👇 选择你想查看的功能模块…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]

        if value == "home":
            embed = _build_home_embed(self.bot)
        else:
            cog = self.bot.get_cog(value)
            meta = COG_META.get(value, {"emoji": "📂", "label": value, "desc": ""})
            if cog:
                lines = _collect_commands(cog)
                embed = discord.Embed(
                    title=f"{meta['emoji']} {meta['label']}",
                    description=(
                        meta["desc"] + "\n\n" + "\n".join(lines)
                        if lines
                        else "该模块暂时没有可用指令。"
                    ),
                    color=discord.Color.pink(),
                )
                embed.set_footer(text=f"共 {len(lines)} 个指令")
            else:
                embed = discord.Embed(
                    title="❌ 错误",
                    description="找不到该模块。",
                    color=discord.Color.red(),
                )

        await interaction.response.edit_message(embed=embed)


def _build_home_embed(bot):
    embed = discord.Embed(
        title="✨ 小凛 RinBot 指令中心",
        description=(
            "你的全能 Discord 小助手 (´• ω •`)ﾉ\n" "下方菜单选择模块查看详细指令。\n"
        ),
        color=discord.Color.pink(),
    )
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    available = []
    for cog_name, meta in COG_META.items():
        if cog_name in HIDDEN_COGS:
            continue
        cog = bot.get_cog(cog_name)
        if cog and _collect_commands(cog):
            available.append(f"{meta['emoji']} **{meta['label']}** — *{meta['desc']}*")

    if available:
        embed.add_field(
            name="📦 已加载的模块",
            value="\n".join(available),
            inline=False,
        )

    embed.set_footer(text=f"共 {len(available)} 个模块 · 菜单 120 秒后失效")
    return embed


class HelpView(View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.add_item(HelpDropdown(bot))


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="打开交互式指令菜单")
    async def help(self, ctx):
        embed = _build_home_embed(self.bot)
        view = HelpView(self.bot)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
