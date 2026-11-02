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
