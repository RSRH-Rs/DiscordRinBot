# cogs/moderation.py
# RinBot — 管理模块 (Moderation)
# 功能：
#   • /kick        — 踢出成员
#   • /ban         — 永久封禁
#   • /tempban     — 临时封禁 (到期自动解封)
#   • /unban       — 解除封禁
#   • /mute        — 禁言 (Discord Timeout)
#   • /unmute      — 解除禁言
#   • /warn        — 警告成员
#   • /warns       — 查看成员的警告记录
#   • /clearwarns  — 清除成员的所有警告
#   • /delwarn     — 删除指定警告
#   • /purge       — 批量清理消息
#   • /slowmode    — 设置频道慢速模式
#   • /lock        — 锁定频道 (禁止发言)
#   • /unlock      — 解锁频道
#   • /modlog      — 查看管理操作日志
#   • /modlog_channel — 设置管理日志频道
#   • 警告达到阈值自动处罚 (可配置)

import discord
from discord.ext import commands, tasks
import aiosqlite
import datetime
import time
from typing import Literal, Optional

DB_PATH = "moderation.db"


class Moderation(commands.Cog):
    """管理模块 — kick / ban / mute / warn / purge / slowmode / lock"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            # 警告表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    mod_id INTEGER NOT NULL,
                    reason TEXT DEFAULT '未提供原因',
                    created_at REAL NOT NULL
                )
            """)
            # 管理日志表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS mod_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    mod_id INTEGER NOT NULL,
                    reason TEXT DEFAULT '未提供原因',
                    duration TEXT DEFAULT '',
                    created_at REAL NOT NULL
                )
            """)
            # 管理配置表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS mod_config (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel INTEGER DEFAULT 0,
                    warn_kick_threshold INTEGER DEFAULT 0,
                    warn_ban_threshold INTEGER DEFAULT 0,
                    warn_mute_threshold INTEGER DEFAULT 3,
                    warn_mute_duration INTEGER DEFAULT 600
                )
            """)
            # 临时封禁表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tempbans (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    unban_at REAL NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await db.commit()

        if not self.check_tempbans.is_running():
            self.check_tempbans.start()

        print("✅ 管理模块已准备就绪！")

    def cog_unload(self):
        self.check_tempbans.cancel()

    # ═══════════════════════════════════════
    #  内部工具
    # ═══════════════════════════════════════

    async def _get_config(self, guild_id: int) -> dict:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO mod_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM mod_config WHERE guild_id = ?", (guild_id,))
            row = await cursor.fetchone()
            return dict(row) if row else {}

    async def _log_case(self, guild: discord.Guild, action: str, user: discord.User,
                        mod: discord.Member, reason: str, duration: str = ""):
        """记录管理操作到数据库 + 发送到日志频道"""
        now = time.time()
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO mod_cases (guild_id, action, user_id, mod_id, reason, duration, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (guild.id, action, user.id, mod.id, reason, duration, now),
            )
            case_id = cursor.lastrowid
            await db.commit()

        # 发送到日志频道
        config = await self._get_config(guild.id)
        log_ch_id = config.get("log_channel", 0)
        if log_ch_id:
            channel = guild.get_channel(log_ch_id)
            if channel:
                action_emoji = {
                    "kick": "👢", "ban": "🔨", "tempban": "⏳🔨",
                    "unban": "🔓", "mute": "🔇", "unmute": "🔊",
                    "warn": "⚠️", "clearwarns": "🧹", "purge": "🗑",
                }.get(action, "📋")

                embed = discord.Embed(
                    title=f"{action_emoji} {action.upper()} | 案件 #{case_id}",
                    color=discord.Color.red() if action in ("ban", "tempban", "kick") else discord.Color.orange(),
                    timestamp=discord.utils.utcnow(),
                )
                embed.add_field(name="成员", value=f"{user.mention} (`{user.id}`)", inline=True)
                embed.add_field(name="管理员", value=mod.mention, inline=True)
                if duration:
                    embed.add_field(name="时长", value=duration, inline=True)
                embed.add_field(name="原因", value=reason, inline=False)
                embed.set_thumbnail(url=user.display_avatar.url)

                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        return case_id

    async def _check_warn_thresholds(self, guild: discord.Guild, member: discord.Member):
        """检查警告是否达到自动处罚阈值"""
        config = await self._get_config(guild.id)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
                (guild.id, member.id),
            )
            count = (await cursor.fetchone())[0]

        # 封禁阈值（最高优先级）
        ban_threshold = config.get("warn_ban_threshold", 0)
        if ban_threshold > 0 and count >= ban_threshold:
            try:
                await member.ban(reason=f"警告数达到自动封禁阈值 ({count}/{ban_threshold})")
                await self._log_case(guild, "ban", member, guild.me,
                                     f"警告数达到阈值自动封禁 ({count}次警告)")
                return f"🔨 {member.mention} 的警告数已达 {count} 次，已自动封禁。"
            except discord.Forbidden:
                return None

        # 踢出阈值
        kick_threshold = config.get("warn_kick_threshold", 0)
        if kick_threshold > 0 and count >= kick_threshold:
            try:
                await member.kick(reason=f"警告数达到自动踢出阈值 ({count}/{kick_threshold})")
                await self._log_case(guild, "kick", member, guild.me,
                                     f"警告数达到阈值自动踢出 ({count}次警告)")
                return f"👢 {member.mention} 的警告数已达 {count} 次，已自动踢出。"
            except discord.Forbidden:
                return None

        # 禁言阈值
        mute_threshold = config.get("warn_mute_threshold", 3)
        mute_duration = config.get("warn_mute_duration", 600)
        if mute_threshold > 0 and count >= mute_threshold and count % mute_threshold == 0:
            try:
                until = discord.utils.utcnow() + datetime.timedelta(seconds=mute_duration)
                await member.timeout(until, reason=f"警告数达到禁言阈值 ({count}次)")
                await self._log_case(guild, "mute", member, guild.me,
                                     f"警告数达到阈值自动禁言 ({count}次警告)",
                                     f"{mute_duration // 60} 分钟")
                return f"🔇 {member.mention} 的警告数已达 {count} 次，已自动禁言 {mute_duration // 60} 分钟。"
            except discord.Forbidden:
                return None

        return None

    def _parse_duration(self, s: str) -> Optional[int]:
        """解析时长字符串 → 秒数"""
        total = 0
        buf = ""
        for ch in s.lower():
            if ch.isdigit():
                buf += ch
            elif ch in ("d", "h", "m", "s") and buf:
                n = int(buf)
                if ch == "d": total += n * 86400
                elif ch == "h": total += n * 3600
                elif ch == "m": total += n * 60
                elif ch == "s": total += n
                buf = ""
            else:
                return None
        return total if total > 0 else None

    def _format_duration(self, seconds: int) -> str:
        parts = []
        d, rem = divmod(seconds, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        if d: parts.append(f"{d}天")
        if h: parts.append(f"{h}小时")
        if m: parts.append(f"{m}分钟")
        if s and not d: parts.append(f"{s}秒")
        return " ".join(parts) or "0秒"

    def _hierarchy_check(self, ctx, target: discord.Member) -> Optional[str]:
        """权限层级检查，返回错误信息或 None"""
        if target == ctx.author:
            return "❌ 你不能对自己执行此操作。"
        if target == ctx.guild.owner:
            return "❌ 不能对服务器所有者执行此操作。"
        if target.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return "❌ 你不能对身份组等于或高于你的成员执行此操作。"
        if target.top_role >= ctx.guild.me.top_role:
            return "❌ 我的身份组不够高，无法对该成员执行操作。"
        return None

    # ═══════════════════════════════════════
    #  定时任务：检查临时封禁
    # ═══════════════════════════════════════

    @tasks.loop(seconds=30)
    async def check_tempbans(self):
        now = time.time()
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT guild_id, user_id FROM tempbans WHERE unban_at <= ?", (now,))
            expired = await cursor.fetchall()

            for guild_id, user_id in expired:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        await guild.unban(user, reason="临时封禁到期自动解封")
                    except (discord.NotFound, discord.Forbidden):
                        pass
                await db.execute("DELETE FROM tempbans WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            await db.commit()

    @check_tempbans.before_loop
    async def before_check_tempbans(self):
        await self.bot.wait_until_ready()

    # ═══════════════════════════════════════
    #  指令：kick
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="kick", description="踢出成员")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "未提供原因"):
        err = self._hierarchy_check(ctx, member)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        # 尝试 DM 通知
        try:
            embed = discord.Embed(
                title=f"👢 你已被踢出 {ctx.guild.name}",
                description=f"**原因:** {reason}\n**管理员:** {ctx.author}",
                color=discord.Color.orange(),
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

        await member.kick(reason=f"{ctx.author}: {reason}")
        case_id = await self._log_case(ctx.guild, "kick", member, ctx.author, reason)

        await ctx.send(f"👢 **{member}** 已被踢出。(案件 #{case_id})\n📝 原因: {reason}")

    # ═══════════════════════════════════════
    #  指令：ban
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="ban", description="永久封禁成员")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "未提供原因"):
        err = self._hierarchy_check(ctx, member)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        try:
            embed = discord.Embed(
                title=f"🔨 你已被永久封禁于 {ctx.guild.name}",
                description=f"**原因:** {reason}\n**管理员:** {ctx.author}",
                color=discord.Color.red(),
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

        await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=0)
        case_id = await self._log_case(ctx.guild, "ban", member, ctx.author, reason)

        await ctx.send(f"🔨 **{member}** 已被永久封禁。(案件 #{case_id})\n📝 原因: {reason}")

    # ═══════════════════════════════════════
    #  指令：tempban
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="tempban", description="临时封禁成员 (到期自动解封)")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, duration: str, *, reason: str = "未提供原因"):
        """
        duration: 封禁时长 (如 1h, 30m, 7d)
        """
        err = self._hierarchy_check(ctx, member)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        seconds = self._parse_duration(duration)
        if not seconds:
            await ctx.send("❌ 无效的时间格式！示例: `1h`, `30m`, `7d`")
            return

        dur_text = self._format_duration(seconds)

        try:
            embed = discord.Embed(
                title=f"⏳🔨 你已被临时封禁于 {ctx.guild.name}",
                description=f"**时长:** {dur_text}\n**原因:** {reason}\n**管理员:** {ctx.author}",
                color=discord.Color.red(),
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

        await member.ban(reason=f"临时封禁 {dur_text} | {ctx.author}: {reason}", delete_message_days=0)

        unban_at = time.time() + seconds
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO tempbans (guild_id, user_id, unban_at) VALUES (?, ?, ?)",
                (ctx.guild.id, member.id, unban_at),
            )
            await db.commit()

        case_id = await self._log_case(ctx.guild, "tempban", member, ctx.author, reason, dur_text)
        await ctx.send(f"⏳🔨 **{member}** 已被临时封禁 **{dur_text}**。(案件 #{case_id})\n📝 原因: {reason}")

    # ═══════════════════════════════════════
    #  指令：unban
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="unban", description="解除封禁")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str, *, reason: str = "未提供原因"):
        """user_id: 被封禁用户的 ID"""
        await ctx.defer()
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")

            # 清理临时封禁记录
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM tempbans WHERE guild_id = ? AND user_id = ?",
                                 (ctx.guild.id, user.id))
                await db.commit()

            case_id = await self._log_case(ctx.guild, "unban", user, ctx.author, reason)
            await ctx.send(f"🔓 **{user}** 已被解除封禁。(案件 #{case_id})")
        except discord.NotFound:
            await ctx.send("❌ 找不到该用户或该用户未被封禁。")
        except ValueError:
            await ctx.send("❌ 请提供有效的用户 ID。")

    # ═══════════════════════════════════════
    #  指令：mute
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="mute", description="禁言成员 (使用 Discord Timeout)")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str = "10m", *, reason: str = "未提供原因"):
        """
        duration: 禁言时长 (如 10m, 1h, 1d, 最长 28d)
        """
        err = self._hierarchy_check(ctx, member)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        seconds = self._parse_duration(duration)
        if not seconds:
            await ctx.send("❌ 无效的时间格式！示例: `10m`, `1h`, `1d`")
            return

        if seconds > 28 * 86400:
            await ctx.send("❌ Discord Timeout 最长 28 天。")
            return

        dur_text = self._format_duration(seconds)
        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)

        await member.timeout(until, reason=f"{ctx.author}: {reason}")
        case_id = await self._log_case(ctx.guild, "mute", member, ctx.author, reason, dur_text)

        await ctx.send(f"🔇 **{member}** 已被禁言 **{dur_text}**。(案件 #{case_id})\n📝 原因: {reason}")

    # ═══════════════════════════════════════
    #  指令：unmute
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="unmute", description="解除成员禁言")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "未提供原因"):
        if not member.is_timed_out():
            await ctx.send(f"ℹ️ {member.mention} 当前没有被禁言。")
            return

        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        case_id = await self._log_case(ctx.guild, "unmute", member, ctx.author, reason)
        await ctx.send(f"🔊 **{member}** 的禁言已解除。(案件 #{case_id})")

    # ═══════════════════════════════════════
    #  指令：warn
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="warn", description="警告成员")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "未提供原因"):
        err = self._hierarchy_check(ctx, member)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        now = time.time()
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO warnings (guild_id, user_id, mod_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (ctx.guild.id, member.id, ctx.author.id, reason, now),
            )
            warn_id = cursor.lastrowid

            cursor2 = await db.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member.id),
            )
            total = (await cursor2.fetchone())[0]
            await db.commit()

        case_id = await self._log_case(ctx.guild, "warn", member, ctx.author, reason)

        # DM 通知
        try:
            embed = discord.Embed(
                title=f"⚠️ 你在 {ctx.guild.name} 收到了一次警告",
                description=f"**原因:** {reason}\n**管理员:** {ctx.author}\n**累计警告:** {total} 次",
                color=discord.Color.yellow(),
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

        msg = f"⚠️ **{member}** 已被警告。(第 {total} 次 | 案件 #{case_id})\n📝 原因: {reason}"

        # 检查自动处罚
        auto_result = await self._check_warn_thresholds(ctx.guild, member)
        if auto_result:
            msg += f"\n{auto_result}"

        await ctx.send(msg)

    # ═══════════════════════════════════════
    #  指令：warns
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="warns", description="查看成员的警告记录")
    @commands.has_permissions(manage_messages=True)
    async def warns(self, ctx, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, mod_id, reason, created_at FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 20",
                (ctx.guild.id, member.id),
            )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send(f"✅ **{member}** 没有任何警告记录。")
            return

        embed = discord.Embed(
            title=f"⚠️ {member.display_name} 的警告记录",
            color=discord.Color.yellow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for warn_id, mod_id, reason, created_at in rows:
            ts = int(created_at)
            embed.add_field(
                name=f"#{warn_id} — <t:{ts}:R>",
                value=f"管理员: <@{mod_id}>\n原因: {reason}",
                inline=False,
            )

        embed.set_footer(text=f"共 {len(rows)} 条警告")
        await ctx.send(embed=embed)

    # ═══════════════════════════════════════
    #  指令：clearwarns
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="clearwarns", description="清除成员的所有警告")
    @commands.has_permissions(manage_guild=True)
    async def clearwarns(self, ctx, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member.id),
            )
            count = (await cursor.fetchone())[0]

            await db.execute(
                "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member.id),
            )
            await db.commit()

        if count == 0:
            await ctx.send(f"ℹ️ {member.mention} 本来就没有警告记录。")
        else:
            await self._log_case(ctx.guild, "clearwarns", member, ctx.author,
                                 f"清除了 {count} 条警告")
            await ctx.send(f"🧹 已清除 **{member}** 的所有警告 ({count} 条)。")

    # ═══════════════════════════════════════
    #  指令：delwarn
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="delwarn", description="删除指定 ID 的警告")
    @commands.has_permissions(manage_messages=True)
    async def delwarn(self, ctx, warn_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id FROM warnings WHERE id = ? AND guild_id = ?",
                (warn_id, ctx.guild.id),
            )
            row = await cursor.fetchone()
            if not row:
                await ctx.send("❌ 找不到该警告 ID。")
                return

            await db.execute("DELETE FROM warnings WHERE id = ?", (warn_id,))
            await db.commit()

        await ctx.send(f"✅ 已删除警告 #{warn_id}。")

    # ═══════════════════════════════════════
    #  指令：purge
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="purge", aliases=["prune"], description="批量清理消息")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int, member: discord.Member = None):
        """
        amount: 要删除的消息数量 (1-500)
        member: 只删除该成员的消息 (可选)
        """
        if amount < 1 or amount > 500:
            await ctx.send("❌ 数量范围: 1-500")
            return

        await ctx.defer(ephemeral=True)

        if member:
            # 先获取消息再过滤
            deleted = []
            async for msg in ctx.channel.history(limit=amount * 3):
                if msg.author == member and len(deleted) < amount:
                    deleted.append(msg)
            # 批量删除 (只能删 14 天内的)
            for i in range(0, len(deleted), 100):
                batch = deleted[i:i + 100]
                try:
                    await ctx.channel.delete_messages(batch)
                except discord.HTTPException:
                    for msg in batch:
                        try:
                            await msg.delete()
                        except discord.NotFound:
                            pass
            count = len(deleted)
        else:
            deleted = await ctx.channel.purge(limit=amount)
            count = len(deleted)

        await self._log_case(ctx.guild, "purge", ctx.author, ctx.author,
                             f"在 #{ctx.channel.name} 清理了 {count} 条消息"
                             + (f" (来自 {member})" if member else ""))

        await ctx.send(f"🗑 已清理 **{count}** 条消息。", ephemeral=True)

    # ═══════════════════════════════════════
    #  指令：slowmode
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="slowmode", aliases=["slow"], description="设置频道慢速模式")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int = 0):
        """seconds: 慢速间隔秒数 (0=关闭, 最大 21600)"""
        if seconds < 0 or seconds > 21600:
            await ctx.send("❌ 范围: 0-21600 秒 (0=关闭)")
            return

        await ctx.channel.edit(slowmode_delay=seconds)

        if seconds == 0:
            await ctx.send("✅ 已关闭慢速模式。")
        else:
            dur = self._format_duration(seconds)
            await ctx.send(f"🐌 已设置慢速模式: 每 **{dur}** 可发送一条消息。")

    # ═══════════════════════════════════════
    #  指令：lock / unlock
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="lock", description="锁定频道 (禁止普通成员发言)")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason: str = "未提供原因"):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        await ctx.send(f"🔒 {channel.mention} 已被锁定。\n📝 原因: {reason}")

    @commands.hybrid_command(name="unlock", description="解锁频道")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None  # 重置为继承
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(f"🔓 {channel.mention} 已解锁。")

    # ═══════════════════════════════════════
    #  指令：modlog
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="modlog", description="查看管理操作日志")
    @commands.has_permissions(manage_messages=True)
    async def modlog(self, ctx, member: discord.User = None, page: int = 1):
        """查看管理日志，可按成员筛选"""
        items_per_page = 10

        async with aiosqlite.connect(DB_PATH) as db:
            if member:
                cursor = await db.execute(
                    "SELECT id, action, user_id, mod_id, reason, duration, created_at FROM mod_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
                    (ctx.guild.id, member.id),
                )
            else:
                cursor = await db.execute(
                    "SELECT id, action, user_id, mod_id, reason, duration, created_at FROM mod_cases WHERE guild_id = ? ORDER BY created_at DESC",
                    (ctx.guild.id,),
                )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("📭 没有管理日志记录。")
            return

        total_pages = max(1, (len(rows) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * items_per_page
        end = start + items_per_page

        embed = discord.Embed(
            title=f"📋 管理日志" + (f" — {member}" if member else ""),
            color=discord.Color.blue(),
        )

        for case_id, action, user_id, mod_id, reason, duration, created_at in rows[start:end]:
            ts = int(created_at)
            dur_info = f" | 时长: {duration}" if duration else ""
            embed.add_field(
                name=f"#{case_id} | {action.upper()} | <t:{ts}:R>",
                value=f"成员: <@{user_id}> | 管理员: <@{mod_id}>{dur_info}\n原因: {reason[:80]}",
                inline=False,
            )

        embed.set_footer(text=f"第 {page}/{total_pages} 页 | 共 {len(rows)} 条记录")
        await ctx.send(embed=embed)

    # ═══════════════════════════════════════
    #  指令：modlog_channel
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="modlog_channel", description="[管理] 设置管理日志频道")
    @commands.has_permissions(manage_guild=True)
    async def modlog_channel(self, ctx, channel: discord.TextChannel = None):
        """channel: 留空则禁用管理日志"""
        if channel:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR IGNORE INTO mod_config (guild_id) VALUES (?)", (ctx.guild.id,))
                await db.execute("UPDATE mod_config SET log_channel = ? WHERE guild_id = ?",
                                 (channel.id, ctx.guild.id))
                await db.commit()
            await ctx.send(f"✅ 管理日志频道已设为 {channel.mention}", ephemeral=True)
        else:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE mod_config SET log_channel = 0 WHERE guild_id = ?", (ctx.guild.id,))
                await db.commit()
            await ctx.send("✅ 已禁用管理日志频道。", ephemeral=True)

    # ═══════════════════════════════════════
    #  指令：warn_config
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="warn_config", description="[管理] 配置警告自动处罚阈值")
    @commands.has_permissions(manage_guild=True)
    async def warn_config(self, ctx, mute_at: int = 3, kick_at: int = 0, ban_at: int = 0, mute_minutes: int = 10):
        """
        mute_at: 达到几次警告自动禁言 (0=禁用)
        kick_at: 达到几次警告自动踢出 (0=禁用)
        ban_at: 达到几次警告自动封禁 (0=禁用)
        mute_minutes: 自动禁言的时长 (分钟)
        """
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO mod_config (guild_id) VALUES (?)", (ctx.guild.id,))
            await db.execute("""
                UPDATE mod_config SET
                    warn_mute_threshold = ?,
                    warn_kick_threshold = ?,
                    warn_ban_threshold = ?,
                    warn_mute_duration = ?
                WHERE guild_id = ?
            """, (mute_at, kick_at, ban_at, mute_minutes * 60, ctx.guild.id))
            await db.commit()

        lines = []
        if mute_at > 0:
            lines.append(f"🔇 {mute_at} 次警告 → 自动禁言 {mute_minutes} 分钟")
        if kick_at > 0:
            lines.append(f"👢 {kick_at} 次警告 → 自动踢出")
        if ban_at > 0:
            lines.append(f"🔨 {ban_at} 次警告 → 自动封禁")
        if not lines:
            lines.append("所有自动处罚已禁用")

        embed = discord.Embed(
            title="⚙️ 警告自动处罚配置",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, ephemeral=True)

    # ═══════════════════════════════════════
    #  全局错误处理
    # ═══════════════════════════════════════

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await ctx.send(f"🚫 你缺少权限: `{perms}`", ephemeral=True)
        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await ctx.send(f"🚫 我缺少权限: `{perms}`", ephemeral=True)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ 找不到该成员。", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ 参数错误: {error}", ephemeral=True)
        else:
            raise error


async def setup(bot):
    await bot.add_cog(Moderation(bot))