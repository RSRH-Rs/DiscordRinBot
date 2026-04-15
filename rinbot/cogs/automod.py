# cogs/automod.py
# RinBot — 自动审核模块
# 功能：
#   • 反刷屏（短时间内发大量消息自动 mute）
#   • 违禁词过滤（可自定义词库）
#   • 链接过滤（可设置白名单域名）
#   • 大写字母轰炸过滤
#   • 重复消息过滤
#   • /automod — 开关及配置面板
#   • /automod_log — 设置日志频道
#   • /automod_words — 管理违禁词
#   • /automod_whitelist — 管理链接白名单
#   • /automod_ignore — 忽略指定频道/身份组

import discord
from discord.ext import commands
import aiosqlite
import json
import time
import re
from collections import defaultdict
from typing import Literal

DB_PATH = "automod.db"


class AutoMod(commands.Cog):
    """自动审核 — 社区风纪委员小凛"""

    def __init__(self, bot):
        self.bot = bot
        # 刷屏检测缓存: {guild_id: {user_id: [timestamp, ...]}}
        self._msg_cache: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
        # 重复消息缓存: {guild_id: {user_id: [(content, timestamp), ...]}}
        self._repeat_cache: dict[int, dict[int, list[tuple]]] = defaultdict(lambda: defaultdict(list))
        # 配置缓存
        self._config_cache: dict[int, dict] = {}

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS automod_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    log_channel INTEGER DEFAULT 0,
                    anti_spam INTEGER DEFAULT 1,
                    spam_threshold INTEGER DEFAULT 5,
                    spam_interval INTEGER DEFAULT 5,
                    anti_badword INTEGER DEFAULT 1,
                    badwords TEXT DEFAULT '[]',
                    anti_link INTEGER DEFAULT 0,
                    link_whitelist TEXT DEFAULT '[]',
                    anti_caps INTEGER DEFAULT 1,
                    caps_threshold INTEGER DEFAULT 70,
                    caps_min_length INTEGER DEFAULT 10,
                    anti_repeat INTEGER DEFAULT 1,
                    repeat_threshold INTEGER DEFAULT 3,
                    mute_duration INTEGER DEFAULT 300,
                    ignored_channels TEXT DEFAULT '[]',
                    ignored_roles TEXT DEFAULT '[]'
                )
            """)
            await db.commit()

            # 预加载所有配置
            cursor = await db.execute("SELECT * FROM automod_config")
            columns = [d[0] for d in cursor.description]
            for row in await cursor.fetchall():
                cfg = dict(zip(columns, row))
                self._config_cache[cfg["guild_id"]] = cfg

        print("✅ 自动审核系统已准备就绪！")

    async def _get_config(self, guild_id: int) -> dict:
        if guild_id in self._config_cache:
            return self._config_cache[guild_id]
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,))
            row = await cursor.fetchone()
            if row:
                cfg = dict(row)
                self._config_cache[guild_id] = cfg
                return cfg
        return None

    async def _update_config(self, guild_id: int, **kwargs):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (guild_id,))
            for key, val in kwargs.items():
                await db.execute(f"UPDATE automod_config SET {key} = ? WHERE guild_id = ?", (val, guild_id))
            await db.commit()
        # 刷新缓存
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,))
            row = await cursor.fetchone()
            if row:
                self._config_cache[guild_id] = dict(row)

    async def _log_action(self, guild: discord.Guild, embed: discord.Embed):
        cfg = await self._get_config(guild.id)
        if not cfg or not cfg.get("log_channel"):
            return
        channel = guild.get_channel(cfg["log_channel"])
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    async def _mute_user(self, member: discord.Member, reason: str, duration: int):
        """使用 Discord 原生 timeout 功能"""
        try:
            import datetime
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
            await member.timeout(until, reason=reason)
        except discord.Forbidden:
            pass

    def _is_ignored(self, cfg: dict, channel_id: int, member: discord.Member) -> bool:
        """检查频道或身份组是否在忽略列表中"""
        try:
            ignored_channels = json.loads(cfg.get("ignored_channels", "[]"))
            ignored_roles = json.loads(cfg.get("ignored_roles", "[]"))
        except json.JSONDecodeError:
            return False

        if channel_id in ignored_channels:
            return True
        member_role_ids = {r.id for r in member.roles}
        if member_role_ids & set(ignored_roles):
            return True
        return False

    # ─── 消息监听 ───

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if message.author.guild_permissions.manage_messages:
            return  # 不审核管理员

        cfg = await self._get_config(message.guild.id)
        if not cfg or not cfg.get("enabled"):
            return

        if self._is_ignored(cfg, message.channel.id, message.author):
            return

        guild_id = message.guild.id
        user_id = message.author.id
        now = time.time()

        # ── 1. 反刷屏 ──
        if cfg.get("anti_spam"):
            threshold = cfg.get("spam_threshold", 5)
            interval = cfg.get("spam_interval", 5)

            self._msg_cache[guild_id][user_id].append(now)
            # 清理过期记录
            self._msg_cache[guild_id][user_id] = [
                t for t in self._msg_cache[guild_id][user_id] if now - t < interval
            ]

            if len(self._msg_cache[guild_id][user_id]) >= threshold:
                self._msg_cache[guild_id][user_id].clear()
                mute_dur = cfg.get("mute_duration", 300)
                await self._mute_user(message.author, "刷屏", mute_dur)
                try:
                    await message.channel.send(
                        f"🔇 {message.author.mention} 因刷屏被小凛禁言 {mute_dur // 60} 分钟。",
                        delete_after=10,
                    )
                except discord.Forbidden:
                    pass
                embed = discord.Embed(
                    title="🚨 刷屏检测",
                    description=f"**用户:** {message.author.mention}\n**频道:** {message.channel.mention}\n**处理:** 禁言 {mute_dur // 60} 分钟",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow(),
                )
                await self._log_action(message.guild, embed)
                return

        # ── 2. 重复消息检测 ──
        if cfg.get("anti_repeat"):
            repeat_threshold = cfg.get("repeat_threshold", 3)
            cache = self._repeat_cache[guild_id][user_id]
            cache.append((message.content.lower().strip(), now))
            # 只保留最近 30 秒的消息
            cache[:] = [(c, t) for c, t in cache if now - t < 30]

            content = message.content.lower().strip()
            same_count = sum(1 for c, _ in cache if c == content)

            if same_count >= repeat_threshold and content:
                cache.clear()
                try:
                    await message.delete()
                    await message.channel.send(
                        f"⚠️ {message.author.mention} 请不要发送重复消息。",
                        delete_after=8,
                    )
                except discord.Forbidden:
                    pass
                embed = discord.Embed(
                    title="🔁 重复消息",
                    description=f"**用户:** {message.author.mention}\n**频道:** {message.channel.mention}\n**内容:** {content[:100]}",
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow(),
                )
                await self._log_action(message.guild, embed)
                return

        # ── 3. 违禁词过滤 ──
        if cfg.get("anti_badword"):
            try:
                badwords = json.loads(cfg.get("badwords", "[]"))
            except json.JSONDecodeError:
                badwords = []

            msg_lower = message.content.lower()
            for word in badwords:
                if word.lower() in msg_lower:
                    try:
                        await message.delete()
                        await message.channel.send(
                            f"⚠️ {message.author.mention} 你的消息包含违禁内容，已被小凛删除。",
                            delete_after=8,
                        )
                    except discord.Forbidden:
                        pass
                    embed = discord.Embed(
                        title="🚫 违禁词",
                        description=f"**用户:** {message.author.mention}\n**频道:** {message.channel.mention}\n**触发词:** ||{word}||",
                        color=discord.Color.red(),
                        timestamp=discord.utils.utcnow(),
                    )
                    await self._log_action(message.guild, embed)
                    return

        # ── 4. 链接过滤 ──
        if cfg.get("anti_link"):
            url_pattern = re.compile(r"https?://\S+", re.IGNORECASE)
            urls = url_pattern.findall(message.content)

            if urls:
                try:
                    whitelist = json.loads(cfg.get("link_whitelist", "[]"))
                except json.JSONDecodeError:
                    whitelist = []

                for url in urls:
                    is_whitelisted = any(domain in url.lower() for domain in whitelist)
                    if not is_whitelisted:
                        try:
                            await message.delete()
                            await message.channel.send(
                                f"🔗 {message.author.mention} 不允许在此发送链接。",
                                delete_after=8,
                            )
                        except discord.Forbidden:
                            pass
                        embed = discord.Embed(
                            title="🔗 链接过滤",
                            description=f"**用户:** {message.author.mention}\n**频道:** {message.channel.mention}\n**链接:** {url[:100]}",
                            color=discord.Color.orange(),
                            timestamp=discord.utils.utcnow(),
                        )
                        await self._log_action(message.guild, embed)
                        return

        # ── 5. 大写字母轰炸 ──
        if cfg.get("anti_caps"):
            min_len = cfg.get("caps_min_length", 10)
            threshold = cfg.get("caps_threshold", 70)
            text = message.content
            alpha_chars = [c for c in text if c.isalpha()]
            if len(alpha_chars) >= min_len:
                upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) * 100
                if upper_ratio >= threshold:
                    try:
                        await message.delete()
                        await message.channel.send(
                            f"📢 {message.author.mention} 请不要使用过多大写字母。",
                            delete_after=8,
                        )
                    except discord.Forbidden:
                        pass
                    return

    # ─── 配置指令 ───

    @commands.hybrid_group(name="automod", description="自动审核管理")
    @commands.has_permissions(manage_guild=True)
    async def automod_group(self, ctx):
        if ctx.invoked_subcommand is None:
            cfg = await self._get_config(ctx.guild.id)
            if not cfg:
                await ctx.send("⚠️ 自动审核尚未启用。使用 `/automod enable` 启用。")
                return

            status_emoji = lambda v: "🟢" if v else "🔴"
            embed = discord.Embed(
                title="🛡 自动审核配置面板",
                color=discord.Color.blue(),
            )
            embed.add_field(name="总开关", value=status_emoji(cfg["enabled"]), inline=True)
            embed.add_field(name="反刷屏", value=f"{status_emoji(cfg['anti_spam'])} ({cfg['spam_threshold']}条/{cfg['spam_interval']}秒)", inline=True)
            embed.add_field(name="违禁词", value=f"{status_emoji(cfg['anti_badword'])} ({len(json.loads(cfg.get('badwords','[]')))}个词)", inline=True)
            embed.add_field(name="链接过滤", value=status_emoji(cfg["anti_link"]), inline=True)
            embed.add_field(name="大写过滤", value=f"{status_emoji(cfg['anti_caps'])} (>{cfg['caps_threshold']}%)", inline=True)
            embed.add_field(name="重复消息", value=f"{status_emoji(cfg['anti_repeat'])} ({cfg['repeat_threshold']}次触发)", inline=True)

            log_ch = ctx.guild.get_channel(cfg.get("log_channel", 0))
            embed.add_field(name="日志频道", value=log_ch.mention if log_ch else "未设置", inline=True)
            embed.add_field(name="禁言时长", value=f"{cfg.get('mute_duration', 300) // 60} 分钟", inline=True)

            embed.set_footer(text="使用 /automod enable|disable|toggle 子指令来配置")
            await ctx.send(embed=embed)

    @automod_group.command(name="enable", description="启用自动审核系统")
    @commands.has_permissions(manage_guild=True)
    async def am_enable(self, ctx):
        await self._update_config(ctx.guild.id, enabled=1)
        await ctx.send("✅ 自动审核已启用！小凛开始值班了。", ephemeral=True)

    @automod_group.command(name="disable", description="禁用自动审核系统")
    @commands.has_permissions(manage_guild=True)
    async def am_disable(self, ctx):
        await self._update_config(ctx.guild.id, enabled=0)
        await ctx.send("✅ 自动审核已禁用。", ephemeral=True)

    @automod_group.command(name="toggle", description="开关指定功能")
    @commands.has_permissions(manage_guild=True)
    async def am_toggle(self, ctx, feature: Literal["spam", "badword", "link", "caps", "repeat"]):
        key_map = {
            "spam": "anti_spam",
            "badword": "anti_badword",
            "link": "anti_link",
            "caps": "anti_caps",
            "repeat": "anti_repeat",
        }
        key = key_map[feature]
        cfg = await self._get_config(ctx.guild.id) or {}
        new_val = 0 if cfg.get(key, 1) else 1
        await self._update_config(ctx.guild.id, **{key: new_val})
        status = "开启" if new_val else "关闭"
        await ctx.send(f"✅ **{feature}** 功能已{status}。", ephemeral=True)

    @automod_group.command(name="log", description="设置审核日志频道")
    @commands.has_permissions(manage_guild=True)
    async def am_log(self, ctx, channel: discord.TextChannel):
        await self._update_config(ctx.guild.id, log_channel=channel.id)
        await ctx.send(f"✅ 审核日志将发送到 {channel.mention}", ephemeral=True)

    @automod_group.command(name="mute_duration", description="设置刷屏禁言时长（分钟）")
    @commands.has_permissions(manage_guild=True)
    async def am_mute_dur(self, ctx, minutes: int):
        if minutes < 1 or minutes > 1440:
            await ctx.send("❌ 禁言时长范围: 1-1440 分钟")
            return
        await self._update_config(ctx.guild.id, mute_duration=minutes * 60)
        await ctx.send(f"✅ 刷屏禁言时长已设为 {minutes} 分钟。", ephemeral=True)

    @automod_group.command(name="spam_config", description="配置反刷屏参数")
    @commands.has_permissions(manage_guild=True)
    async def am_spam_cfg(self, ctx, threshold: int = 5, interval: int = 5):
        """
        threshold: 触发阈值（条数）
        interval: 检测窗口（秒）
        """
        await self._update_config(ctx.guild.id, spam_threshold=threshold, spam_interval=interval)
        await ctx.send(f"✅ 反刷屏配置: {interval} 秒内发送 {threshold} 条消息触发。", ephemeral=True)

    # ─── 违禁词管理 ───

    @commands.hybrid_command(name="automod_words", description="[管理] 管理违禁词列表")
    @commands.has_permissions(manage_guild=True)
    async def am_words(self, ctx, action: Literal["add", "remove", "list"], *, word: str = ""):
        cfg = await self._get_config(ctx.guild.id)
        if not cfg:
            await self._update_config(ctx.guild.id)
            cfg = await self._get_config(ctx.guild.id)

        try:
            words = json.loads(cfg.get("badwords", "[]"))
        except json.JSONDecodeError:
            words = []

        if action == "list":
            if words:
                display = ", ".join(f"||{w}||" for w in words)
                await ctx.send(f"📝 违禁词列表 ({len(words)} 个): {display}", ephemeral=True)
            else:
                await ctx.send("📝 违禁词列表为空。", ephemeral=True)
            return

        if not word:
            await ctx.send("❌ 请提供一个词语。")
            return

        if action == "add":
            if word.lower() not in [w.lower() for w in words]:
                words.append(word)
                await self._update_config(ctx.guild.id, badwords=json.dumps(words, ensure_ascii=False))
                await ctx.send(f"✅ 已添加违禁词: ||{word}||", ephemeral=True)
            else:
                await ctx.send("⚠️ 该词已在列表中。", ephemeral=True)

        elif action == "remove":
            words_lower = [w.lower() for w in words]
            if word.lower() in words_lower:
                idx = words_lower.index(word.lower())
                words.pop(idx)
                await self._update_config(ctx.guild.id, badwords=json.dumps(words, ensure_ascii=False))
                await ctx.send(f"✅ 已移除违禁词: ||{word}||", ephemeral=True)
            else:
                await ctx.send("⚠️ 该词不在列表中。", ephemeral=True)

    # ─── 链接白名单管理 ───

    @commands.hybrid_command(name="automod_whitelist", description="[管理] 管理链接白名单")
    @commands.has_permissions(manage_guild=True)
    async def am_whitelist(self, ctx, action: Literal["add", "remove", "list"], domain: str = ""):
        cfg = await self._get_config(ctx.guild.id)
        if not cfg:
            await self._update_config(ctx.guild.id)
            cfg = await self._get_config(ctx.guild.id)

        try:
            whitelist = json.loads(cfg.get("link_whitelist", "[]"))
        except json.JSONDecodeError:
            whitelist = []

        if action == "list":
            if whitelist:
                await ctx.send(f"✅ 链接白名单: {', '.join(whitelist)}", ephemeral=True)
            else:
                await ctx.send("📝 链接白名单为空（所有链接都会被过滤）。", ephemeral=True)
            return

        if not domain:
            await ctx.send("❌ 请提供域名（如 youtube.com）。")
            return

        if action == "add":
            if domain.lower() not in whitelist:
                whitelist.append(domain.lower())
                await self._update_config(ctx.guild.id, link_whitelist=json.dumps(whitelist))
                await ctx.send(f"✅ 已添加白名单域名: `{domain}`", ephemeral=True)
            else:
                await ctx.send("⚠️ 该域名已在白名单中。", ephemeral=True)

        elif action == "remove":
            if domain.lower() in whitelist:
                whitelist.remove(domain.lower())
                await self._update_config(ctx.guild.id, link_whitelist=json.dumps(whitelist))
                await ctx.send(f"✅ 已移除白名单域名: `{domain}`", ephemeral=True)
            else:
                await ctx.send("⚠️ 该域名不在白名单中。", ephemeral=True)

    # ─── 忽略频道/身份组 ───

    @commands.hybrid_command(name="automod_ignore", description="[管理] 添加/移除审核忽略的频道或身份组")
    @commands.has_permissions(manage_guild=True)
    async def am_ignore(
        self,
        ctx,
        action: Literal["add", "remove", "list"],
        channel: discord.TextChannel = None,
        role: discord.Role = None,
    ):
        cfg = await self._get_config(ctx.guild.id)
        if not cfg:
            await self._update_config(ctx.guild.id)
            cfg = await self._get_config(ctx.guild.id)

        try:
            ignored_channels = json.loads(cfg.get("ignored_channels", "[]"))
            ignored_roles = json.loads(cfg.get("ignored_roles", "[]"))
        except json.JSONDecodeError:
            ignored_channels, ignored_roles = [], []

        if action == "list":
            ch_text = ", ".join(f"<#{cid}>" for cid in ignored_channels) or "无"
            role_text = ", ".join(f"<@&{rid}>" for rid in ignored_roles) or "无"
            embed = discord.Embed(title="🔕 审核忽略列表", color=discord.Color.greyple())
            embed.add_field(name="频道", value=ch_text, inline=False)
            embed.add_field(name="身份组", value=role_text, inline=False)
            await ctx.send(embed=embed, ephemeral=True)
            return

        if action == "add":
            if channel and channel.id not in ignored_channels:
                ignored_channels.append(channel.id)
            if role and role.id not in ignored_roles:
                ignored_roles.append(role.id)
        elif action == "remove":
            if channel and channel.id in ignored_channels:
                ignored_channels.remove(channel.id)
            if role and role.id in ignored_roles:
                ignored_roles.remove(role.id)

        await self._update_config(
            ctx.guild.id,
            ignored_channels=json.dumps(ignored_channels),
            ignored_roles=json.dumps(ignored_roles),
        )
        await ctx.send("✅ 忽略列表已更新。", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
