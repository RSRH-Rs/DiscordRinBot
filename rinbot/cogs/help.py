from typing import Optional

import discord
from discord.ext import commands
from discord.ui import Select, View

from _messages import Notice, embed, send_notice
from _perms import is_owner_only, required_permissions

# Cog 元数据(emoji + 描述)— 没列在这的 cog 会被隐藏
COG_META = {
    "Music": {
        "emoji": "🎵",
        "label": "音乐系统",
        "desc": "先进入语音频道，再用 /play 点歌；常用 /queue、/skip、/stop",
    },
    "Netease": {
        "emoji": "🎧",
        "label": "网易云音乐",
        "desc": "网易云搜索、单曲/歌单链接和个人主页公开歌单",
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


def _command_is_disabled(bot, guild_id, cmd) -> bool:
    if not guild_id:
        return False
    toggle = bot.get_cog("CommandToggle")
    root_name = cmd.qualified_name.split()[0]
    return bool(toggle and toggle.is_disabled(guild_id, root_name))


def visible(command, perms: Optional[discord.Permissions]) -> bool:
    """这个人能不能看到这条指令：主人指令谁都不列；需要权限的指令要有全部这些权限（私信里一律不列）。"""
    if is_owner_only(command):
        return False
    required = required_permissions(command)
    if required is None:
        return True
    return perms is not None and perms >= required


def _collect_commands(cog, bot, guild_id=None, perms=None) -> list:
    """收集 cog 下这个人能用的命令(展开 hybrid group 的子命令)"""
    lines = []
    for cmd in cog.get_commands():
        if cmd.hidden or _command_is_disabled(bot, guild_id, cmd) or not visible(cmd, perms):
            continue
        if isinstance(cmd, commands.HybridGroup) or isinstance(cmd, commands.Group):
            for sub in cmd.commands:
                if not sub.hidden and visible(sub, perms):
                    lines.append(_format_command(sub))
        else:
            lines.append(_format_command(cmd))
    return lines


class HelpDropdown(Select):
    def __init__(self, bot, guild_id=None, perms=None):
        self.bot = bot
        self.guild_id = guild_id
        self.perms = perms
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
            if not _collect_commands(cog, bot, guild_id, perms):
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
            card = _build_home_embed(self.bot, interaction.guild_id, self.perms)
        else:
            cog = self.bot.get_cog(value)
            if not cog:
                await send_notice(interaction, Notice("error", "找不到这个模块"))
                return
            meta = COG_META.get(value, {"emoji": "📂", "label": value, "desc": ""})
            lines = _collect_commands(cog, self.bot, interaction.guild_id, self.perms)
            card = embed(
                "info",
                meta["label"],
                meta["desc"] + "\n\n" + "\n".join(lines) if lines else "该模块暂时没有可用指令。",
                footer=f"共 {len(lines)} 个指令",
            )

        await interaction.response.edit_message(embed=card)


def _build_home_embed(bot, guild_id=None, perms=None):
    available = []
    for cog_name, meta in COG_META.items():
        if cog_name in HIDDEN_COGS:
            continue
        cog = bot.get_cog(cog_name)
        if cog and _collect_commands(cog, bot, guild_id, perms):
            available.append(f"**{meta['label']}** — {meta['desc']}")

    card = embed(
        "info",
        "小凛 RinBot 指令中心",
        "你的全能 Discord 小助手 (´• ω •`)ﾉ\n下方菜单选择模块查看详细指令。",
        fields=[("已加载的模块", "\n".join(available), False)],
        footer="菜单 2 分钟后失效",
    )
    if bot.user:
        card.set_thumbnail(url=bot.user.display_avatar.url)
    return card


class HelpView(View):
    def __init__(self, bot, guild_id=None, perms=None, owner_id=None, owner_name=""):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.add_item(HelpDropdown(bot, guild_id, perms))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # 前缀调用的菜单发在频道里，只让打开它的人操作
        if self.owner_id is not None and interaction.user.id != self.owner_id:
            await send_notice(
                interaction,
                Notice("warning", f"这个菜单是 {self.owner_name} 打开的", "你可以自己输入 /help。"),
            )
            return False
        return True


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="打开交互式指令菜单")
    async def help(self, ctx):
        guild_id = ctx.guild.id if ctx.guild else None
        perms = ctx.author.guild_permissions if ctx.guild else None
        card = _build_home_embed(self.bot, guild_id, perms)
        view = HelpView(self.bot, guild_id, perms, ctx.author.id, ctx.author.display_name)
        await ctx.send(embed=card, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
