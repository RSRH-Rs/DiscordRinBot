# cogs/_botlog_helper.py
# 给其他 cog 用的便捷函数,统一 config 等级日志写法


async def audit(bot, guild_id: int, title: str, **fields):
    """写一条 config 等级的系统日志(若未启用 BotLog 或未配置则静默)"""
    cog = bot.get_cog("BotLog")
    if cog:
        await cog.log(guild_id, "config", title, **fields)


async def warn(bot, guild_id: int, title: str, **fields):
    """写一条 warning 等级的系统日志"""
    cog = bot.get_cog("BotLog")
    if cog:
        await cog.log(guild_id, "warning", title, **fields)


async def info(bot, guild_id: int, title: str, **fields):
    """写一条 info 等级的系统日志"""
    cog = bot.get_cog("BotLog")
    if cog:
        await cog.log(guild_id, "info", title, **fields)


async def error(bot, guild_id: int, title: str, **fields):
    """写一条 error 等级的系统日志"""
    cog = bot.get_cog("BotLog")
    if cog:
        await cog.log(guild_id, "error", title, **fields)


async def check_component(bot, interaction) -> bool:
    """按钮/下拉等组件交互的统一拦截：黑名单/维护模式/全局禁用时 ephemeral 拒绝并返回 False。
    GlobalSettings 未加载时放行（与指令侧一致）。"""
    cog = bot.get_cog("GlobalSettings")
    if cog is None:
        return True
    reason = cog.blocked_reason(interaction.user.id)
    if reason is None:
        return True
    text = "❌ 你无法使用此功能。" if reason == "" else reason
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except Exception:
        pass
    return False
