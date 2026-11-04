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
from discord import app_commands
from discord.ext import commands, tasks
from _perms import require
import aiosqlite
import datetime
import os
import time
from typing import Literal, Optional

from rincore import cases, durations
from rincore.cases import ACTION_NAMES
from rincore.embeds import EVENT_KINDS, event_kind
from _messages import Notice, embed, send_notice
from _inputs import Duration, SlashRange, choices, duration_autocomplete, is_zh

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "moderation.db"
)

DEFAULT_REASON = "未提供原因"


def resolve_ban_args(is_slash: bool, delete_days: int, reason: str) -> tuple[int, str]:
    """前缀命令里 reason 的首个 0-7 数字会被解析成 delete_days；
    为避免误删消息（不可逆），删除消息仅限斜杠命令，前缀模式把数字还给 reason。"""
    if is_slash or not delete_days:
        return delete_days, reason
    if reason == DEFAULT_REASON:
        return 0, str(delete_days)
    return 0, f"{delete_days} {reason}"


class Moderation(commands.Cog):
    """管理模块 — kick / ban / mute / warn / purge / slowmode / lock"""

    def __init__(self, bot):
        self.bot = bot
        self._ban_cache: dict[int, tuple[float, list[tuple[str, str]]]] = {}

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
            # 每服务器案件编号迁移（幂等；网站面板启动时也会执行同一迁移）
            await cases.migrate(db)

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
            await db.execute(
                "INSERT OR IGNORE INTO mod_config (guild_id) VALUES (?)", (guild_id,)
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM mod_config WHERE guild_id = ?", (guild_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else {}

    def _case_embed(self, case: dict, remaining: Optional[datetime.datetime] = None) -> discord.Embed:
        """一个案件的卡片：管理日志和 /case view 共用；remaining 是生效中的处罚的解除时间。"""
        fields = [
            ("成员", f"<@{case['user_id']}>（{case['user_id']}）"),
            ("管理员", f"<@{case['mod_id']}>"),
            ("时长", case["duration"]),
            ("原因", case["reason"], False),
        ]
        if remaining is not None:
            fields.append(("剩余", f"<t:{int(remaining.timestamp())}:R>"))
        return embed(
            EVENT_KINDS.get(case["action"], "log"),
            f"案件 #{case['case_no']}：{ACTION_NAMES.get(case['action'], case['action'])}",
            fields=fields,
            timestamp=datetime.datetime.fromtimestamp(case["created_at"], tz=datetime.timezone.utc),
        )

    async def _send_log(self, guild: discord.Guild, e: discord.Embed) -> None:
        """发到管理日志频道；没设置或发不出去时静默。"""
        config = await self._get_config(guild.id)
        channel = guild.get_channel(config.get("log_channel", 0) or 0)
        if channel is None:
            return
        try:
            await channel.send(embed=e)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _log_case(
        self,
        guild: discord.Guild,
        action: str,
        user: discord.User,
        mod: discord.Member,
        reason: str,
        duration: str = "",
    ):
        """记录管理操作到数据库 + 发送到日志频道"""
        now = time.time()
        async with aiosqlite.connect(DB_PATH) as db:
            # case_id 为本服务器内的案件号 (case_no)，而非全局主键
            case_id = await cases.next_case(
                db, guild.id, action, user.id, mod.id, reason, duration, now
            )

        # 发送到日志频道
        e = self._case_embed(
            {
                "case_no": case_id, "action": action, "user_id": user.id, "mod_id": mod.id,
                "reason": reason, "duration": duration, "created_at": now,
            }
        )
        e.set_thumbnail(url=user.display_avatar.url)
        await self._send_log(guild, e)

        return case_id

    async def _check_warn_thresholds(
        self, guild: discord.Guild, member: discord.Member
    ):
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
                await member.ban(
                    reason=f"警告数达到自动封禁阈值 ({count}/{ban_threshold})"
                )
                await self._log_case(
                    guild,
                    "ban",
                    member,
                    guild.me,
                    f"警告数达到阈值自动封禁 ({count}次警告)",
                )
                return f"🔨 {member.mention} 的警告数已达 {count} 次，已自动封禁。"
            except discord.Forbidden:
                return None

        # 踢出阈值
        kick_threshold = config.get("warn_kick_threshold", 0)
        if kick_threshold > 0 and count >= kick_threshold:
            try:
                await member.kick(
                    reason=f"警告数达到自动踢出阈值 ({count}/{kick_threshold})"
                )
                await self._log_case(
                    guild,
                    "kick",
                    member,
                    guild.me,
                    f"警告数达到阈值自动踢出 ({count}次警告)",
                )
                return f"👢 {member.mention} 的警告数已达 {count} 次，已自动踢出。"
            except discord.Forbidden:
                return None

        # 禁言阈值
        mute_threshold = config.get("warn_mute_threshold", 3)
        mute_duration = config.get("warn_mute_duration", 600)
        if (
            mute_threshold > 0
            and count >= mute_threshold
            and count % mute_threshold == 0
        ):
            try:
                until = discord.utils.utcnow() + datetime.timedelta(
                    seconds=mute_duration
                )
                await member.timeout(until, reason=f"警告数达到禁言阈值 ({count}次)")
                await self._log_case(
                    guild,
                    "mute",
                    member,
                    guild.me,
                    f"警告数达到阈值自动禁言 ({count}次警告)",
                    f"{mute_duration // 60} 分钟",
                )
                return f"🔇 {member.mention} 的警告数已达 {count} 次，已自动禁言 {mute_duration // 60} 分钟。"
            except discord.Forbidden:
                return None

        return None

    def _parse_duration(self, s: str) -> Optional[int]:
        """解析时长字符串 → 秒数（共享实现见 rincore.durations）"""
        return durations.parse_duration(s)

    def _format_duration(self, seconds: int) -> str:
        return durations.format_duration(seconds)

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
            cursor = await db.execute(
                "SELECT guild_id, user_id FROM tempbans WHERE unban_at <= ?", (now,)
            )
            expired = await cursor.fetchall()

            for guild_id, user_id in expired:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        await guild.unban(user, reason="临时封禁到期自动解封")
                    except (discord.NotFound, discord.Forbidden):
                        pass
                await db.execute(
                    "DELETE FROM tempbans WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
            await db.commit()

    @check_tempbans.before_loop
    async def before_check_tempbans(self):
        await self.bot.wait_until_ready()

    # ═══════════════════════════════════════
    #  指令：kick
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Why they are kicked")
    @commands.guild_only()
    @require(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "未提供原因"):
        err = self._hierarchy_check(ctx, member)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        # 尝试 DM 通知
        try:
            e = embed(
                event_kind("kick"),
                f"你已被踢出 {ctx.guild.name}",
                fields=[("原因", reason, False), ("管理员", str(ctx.author))],
            )
            await member.send(embed=e)
        except (discord.Forbidden, discord.HTTPException):
            pass

        await member.kick(reason=f"{ctx.author}: {reason}")
        case_id = await self._log_case(ctx.guild, "kick", member, ctx.author, reason)

        await ctx.send(
            f"👢 **{member}** 已被踢出。(案件 #{case_id})\n📝 原因: {reason}"
        )

    # ═══════════════════════════════════════
    #  指令：ban（填了时长就是临时封禁）
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="ban", description="Ban a member; add a duration for a temporary ban")
    @app_commands.describe(
        member="The member or user ID to ban",
        duration="How long, such as 1d or 7d; leave empty to ban for good",
        delete_days="Also delete their messages from the last 0-7 days",
        reason="Why they are banned",
    )
    @commands.guild_only()
    @require(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        ctx,
        member: discord.User,
        duration: Optional[Duration("ban")] = None,
        delete_days: Optional[SlashRange(0, 7)] = None,
        *,
        reason: str = DEFAULT_REASON,
    ):
        # 前缀调用里时长和删除天数都可以不填：看不懂的词会跳过，留给原因
        delete_days, reason = resolve_ban_args(
            ctx.interaction is not None, delete_days or 0, reason
        )
        # 目标在服务器内才做层级检查与私信；不在服务器的用户（按 ID 封禁）直接封禁
        target = member if isinstance(member, discord.Member) else ctx.guild.get_member(member.id)
        if target is not None:
            err = self._hierarchy_check(ctx, target)
            if err:
                await ctx.send(err, ephemeral=True)
                return

        dur_text = self._format_duration(duration) if duration else ""
        if target is not None:
            try:
                if duration:
                    e = embed(
                        event_kind("tempban"),
                        f"你已被临时封禁：{ctx.guild.name}",
                        fields=[("原因", reason, False), ("时长", dur_text), ("管理员", str(ctx.author))],
                    )
                else:
                    e = embed(
                        event_kind("ban"),
                        f"你已被封禁：{ctx.guild.name}",
                        fields=[("原因", reason, False), ("管理员", str(ctx.author))],
                    )
                await target.send(embed=e)
            except (discord.Forbidden, discord.HTTPException):
                pass

        if not duration:
            await ctx.guild.ban(
                member,
                reason=f"{ctx.author}: {reason}",
                delete_message_seconds=delete_days * 86400,
            )
            case_id = await self._log_case(ctx.guild, "ban", member, ctx.author, reason)
            await ctx.send(
                f"🔨 **{member}** 已被永久封禁。(案件 #{case_id})\n📝 原因: {reason}"
            )
            return

        await ctx.guild.ban(
            member,
            reason=f"临时封禁 {dur_text} | {ctx.author}: {reason}",
            delete_message_seconds=delete_days * 86400,
        )
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO tempbans (guild_id, user_id, unban_at) VALUES (?, ?, ?)",
                (ctx.guild.id, member.id, time.time() + duration),
            )
            await db.commit()
        case_id = await self._log_case(
            ctx.guild, "tempban", member, ctx.author, reason, dur_text
        )
        await ctx.send(
            f"⏳🔨 **{member}** 已被临时封禁 **{dur_text}**。(案件 #{case_id})\n📝 原因: {reason}"
        )

    ban.autocomplete("duration")(duration_autocomplete("ban"))

    # ═══════════════════════════════════════
    #  指令：unban
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="unban", description="Lift a ban")
    @app_commands.describe(user="Who to unban; pick from the ban list or enter a user ID", reason="Why the ban is lifted")
    @commands.guild_only()
    @require(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user: str, *, reason: str = DEFAULT_REASON):
        await ctx.defer()
        user_id = int(user) if user.strip().isdigit() else None
        if user_id is None:
            for label, value in await self._ban_choices(ctx.guild):
                if label.rsplit("（", 1)[0] == user.strip():
                    user_id = int(value)
                    break
        if user_id is None:
            await send_notice(ctx, Notice("error", "找不到这个用户", "检查一下有没有打错，或者直接填用户 ID。"))
            return
        try:
            target = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(target, reason=f"{ctx.author}: {reason}")

            # 清理临时封禁记录
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "DELETE FROM tempbans WHERE guild_id = ? AND user_id = ?",
                    (ctx.guild.id, target.id),
                )
                await db.commit()
            self._ban_cache.pop(ctx.guild.id, None)

            case_id = await self._log_case(ctx.guild, "unban", target, ctx.author, reason)
            await ctx.send(f"🔓 **{target}** 已被解除封禁。(案件 #{case_id})")
        except discord.NotFound:
            await ctx.send("❌ 找不到该用户或该用户未被封禁。")

    async def _ban_choices(self, guild) -> list[tuple[str, str]]:
        """封禁名单 (显示文字, 用户 ID)，每个服务器缓存 60 秒；没有权限或请求失败时为空。"""
        now = time.time()
        hit = self._ban_cache.get(guild.id)
        if hit and now - hit[0] < 60:
            return hit[1]
        try:
            items = [(f"{entry.user}（{entry.user.id}）", str(entry.user.id)) async for entry in guild.bans(limit=1000)]
        except discord.HTTPException:
            return []
        self._ban_cache[guild.id] = (now, items)
        return items

    @unban.autocomplete("user")
    async def _unban_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        return choices(await self._ban_choices(interaction.guild), current)

    # ═══════════════════════════════════════
    #  指令：mute
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="mute", description="Time out a member")
    @app_commands.describe(
        member="The member to time out",
        duration="How long, up to 28 days; default 10 minutes",
        reason="Why they are timed out",
    )
    @commands.guild_only()
    @require(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(
        self,
        ctx,
        member: discord.Member,
        duration: Optional[Duration("mute")] = None,
        *,
        reason: str = DEFAULT_REASON,
    ):
        err = self._hierarchy_check(ctx, member)
        if err:
            await ctx.send(err, ephemeral=True)
            return

        seconds = duration or 600
        dur_text = self._format_duration(seconds)
        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)

        await member.timeout(until, reason=f"{ctx.author}: {reason}")
        case_id = await self._log_case(
            ctx.guild, "mute", member, ctx.author, reason, dur_text
        )

        await ctx.send(
            f"🔇 **{member}** 已被禁言 **{dur_text}**。(案件 #{case_id})\n📝 原因: {reason}"
        )

    mute.autocomplete("duration")(duration_autocomplete("mute"))

    # ═══════════════════════════════════════
    #  指令：unmute
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="unmute", description="Remove a member's timeout")
    @app_commands.describe(member="The member to free", reason="Why the timeout is removed")
    @commands.guild_only()
    @require(moderate_members=True)
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

    @commands.hybrid_command(name="warn", description="Warn a member; enough warnings trigger an automatic punishment")
    @app_commands.describe(member="The member to warn", reason="Why they are warned")
    @commands.guild_only()
    @require(manage_messages=True)
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
            e = embed(
                event_kind("warn"),
                f"你在 {ctx.guild.name} 收到一次警告",
                fields=[("原因", reason, False), ("管理员", str(ctx.author)), ("累计警告", f"{total} 次")],
            )
            await member.send(embed=e)
        except (discord.Forbidden, discord.HTTPException):
            pass

        msg = f"⚠️ **{member}** 已被警告。(第 {total} 次 | 案件 #{case_id})\n📝 原因: {reason}"

        # 检查自动处罚
        auto_result = await self._check_warn_thresholds(ctx.guild, member)
        if auto_result:
            msg += f"\n{auto_result}"

        await ctx.send(msg)

    # ═══════════════════════════════════════
    #  指令：warnings list / remove / clear
    # ═══════════════════════════════════════

    @commands.hybrid_group(name="warnings", description="View and manage warnings")
    @commands.guild_only()
    @require(manage_messages=True)
    async def warnings_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("用法：`r!warnings list <成员>`、`r!warnings remove <警告>`、`r!warnings clear <成员>`")

    @warnings_group.command(name="list", description="Show a member's warnings")
    @app_commands.describe(member="The member to look up")
    @commands.guild_only()
    @require(manage_messages=True)
    async def warnings_list(self, ctx, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, mod_id, reason, created_at FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 20",
                (ctx.guild.id, member.id),
            )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send(f"✅ **{member}** 没有任何警告记录。")
            return

        fields = [
            (f"#{warn_id} — <t:{int(created_at)}:R>", f"管理员: <@{mod_id}>\n原因: {reason}", False)
            for warn_id, mod_id, reason, created_at in rows
        ]
        e = embed("info", f"{member.display_name} 的警告记录", fields=fields, footer=f"共 {len(rows)} 条警告")
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @warnings_group.command(name="remove", description="Delete one warning")
    @app_commands.describe(warning="The warning to delete; pick from the list")
    @commands.guild_only()
    @require(manage_messages=True)
    async def warnings_remove(self, ctx, warning: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id FROM warnings WHERE id = ? AND guild_id = ?",
                (warning, ctx.guild.id),
            )
            row = await cursor.fetchone()
            if not row:
                await ctx.send("❌ 找不到该警告 ID。")
                return

            await db.execute("DELETE FROM warnings WHERE id = ?", (warning,))
            await db.commit()

        await ctx.send(f"✅ 已删除警告 #{warning}。")

    @warnings_remove.autocomplete("warning")
    async def _warning_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT id, user_id, reason FROM warnings WHERE guild_id = ? ORDER BY created_at DESC, id DESC LIMIT 100",
                    (interaction.guild.id,),
                )
                rows = await cursor.fetchall()
        except Exception:
            return []
        items = []
        for warn_id, user_id, reason in rows:
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else str(user_id)
            items.append((f"#{warn_id} {name} {(reason or '')[:40]}", warn_id))
        return choices(items, current)

    @warnings_group.command(name="clear", description="Delete all of a member's warnings")
    @app_commands.describe(member="The member whose warnings are cleared")
    @commands.guild_only()
    @require(manage_messages=True, manage_guild=True)
    async def warnings_clear(self, ctx, member: discord.Member):
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
            await self._log_case(
                ctx.guild, "clearwarns", member, ctx.author, f"清除了 {count} 条警告"
            )
            await ctx.send(f"🧹 已清除 **{member}** 的所有警告 ({count} 条)。")

    # ═══════════════════════════════════════
    #  指令：purge
    # ═══════════════════════════════════════

    @commands.hybrid_command(
        name="purge", aliases=["prune"], description="Delete recent messages in this channel"
    )
    @app_commands.describe(amount="How many messages, 1-500", member="Only delete messages from this member")
    @commands.guild_only()
    @require(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: commands.Range[int, 1, 500], member: discord.Member = None):
        await ctx.defer(ephemeral=True)

        if member:
            # 先获取消息再过滤
            deleted = []
            async for msg in ctx.channel.history(limit=amount * 3):
                if msg.author == member and len(deleted) < amount:
                    deleted.append(msg)
            # 批量删除 (只能删 14 天内的)
            for i in range(0, len(deleted), 100):
                batch = deleted[i : i + 100]
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

        await self._log_case(
            ctx.guild,
            "purge",
            ctx.author,
            ctx.author,
            f"在 #{ctx.channel.name} 清理了 {count} 条消息"
            + (f" (来自 {member})" if member else ""),
        )

        await ctx.send(f"🗑 已清理 **{count}** 条消息。", ephemeral=True)

    # ═══════════════════════════════════════
    #  指令：slowmode
    # ═══════════════════════════════════════

    @commands.hybrid_command(
        name="slowmode", aliases=["slow"], description="Set slow mode for this channel"
    )
    @app_commands.describe(duration="Time between messages, up to 6 hours; 0 turns it off")
    @commands.guild_only()
    @require(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, duration: Optional[Duration("slowmode")] = None):
        seconds = duration or 0
        await ctx.channel.edit(slowmode_delay=seconds)

        if seconds == 0:
            await ctx.send("✅ 已关闭慢速模式。")
        else:
            dur = self._format_duration(seconds)
            await ctx.send(f"🐌 已设置慢速模式: 每 **{dur}** 可发送一条消息。")

    slowmode.autocomplete("duration")(duration_autocomplete("slowmode"))

    # ═══════════════════════════════════════
    #  指令：lock / unlock
    # ═══════════════════════════════════════

    @commands.hybrid_command(name="lock", description="Stop members from sending messages in a channel")
    @app_commands.describe(channel="The channel to lock; default this one", reason="Why it is locked")
    @commands.guild_only()
    @require(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(
        self, ctx, channel: discord.TextChannel = None, *, reason: str = "未提供原因"
    ):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(
            ctx.guild.default_role, overwrite=overwrite, reason=reason
        )
        await ctx.send(f"🔒 {channel.mention} 已被锁定。\n📝 原因: {reason}")

    @commands.hybrid_command(name="unlock", description="Let members send messages in a locked channel again")
    @app_commands.describe(channel="The channel to unlock; default this one")
    @commands.guild_only()
    @require(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None  # 重置为继承
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(f"🔓 {channel.mention} 已解锁。")

    # ═══════════════════════════════════════
    #  指令：case list / view / reason / duration
    # ═══════════════════════════════════════

    async def _get_case(self, guild_id: int, case_no: int) -> Optional[dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            return await cases.get_case(db, guild_id, case_no)

    async def _active_until(self, guild: discord.Guild, case: dict) -> Optional[datetime.datetime]:
        """禁言或临时封禁还在生效时返回解除时间；已到期、成员已离开、已解封或不是最新那次时返回 None。"""
        action = case["action"]
        if action not in ("mute", "tempban"):
            return None
        async with aiosqlite.connect(DB_PATH) as db:
            if await cases.latest_case_no(db, guild.id, case["user_id"], action) != case["case_no"]:
                return None
            if action == "tempban":
                cursor = await db.execute(
                    "SELECT unban_at FROM tempbans WHERE guild_id = ? AND user_id = ?",
                    (guild.id, case["user_id"]),
                )
                row = await cursor.fetchone()
                return datetime.datetime.fromtimestamp(row[0], tz=datetime.timezone.utc) if row else None
        member = guild.get_member(case["user_id"])
        until = getattr(member, "timed_out_until", None)
        return until if until is not None and until > discord.utils.utcnow() else None

    def _case_label(self, guild: discord.Guild, case: dict) -> str:
        member = guild.get_member(case["user_id"])
        name = member.display_name if member else str(case["user_id"])
        action = ACTION_NAMES.get(case["action"], case["action"])
        return f"#{case['case_no']} {action} {name} {(case['reason'] or '')[:30]}"

    @commands.hybrid_group(name="case", description="View and edit moderation cases")
    @commands.guild_only()
    @require(manage_messages=True)
    async def case_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("用法：`r!case list [成员] [页码]`、`r!case view <案件>`、`r!case reason <案件> <原因>`、`r!case duration <案件> <时长>`")

    @case_group.command(name="list", description="List moderation cases, optionally for one member")
    @app_commands.describe(member="Only show cases for this member", page="Which page to show")
    @commands.guild_only()
    @require(manage_messages=True)
    async def case_list(self, ctx, member: discord.User = None, page: commands.Range[int, 1, None] = 1):
        items_per_page = 10

        async with aiosqlite.connect(DB_PATH) as db:
            if member:
                cursor = await db.execute(
                    "SELECT case_no, action, user_id, mod_id, reason, duration, created_at FROM mod_cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
                    (ctx.guild.id, member.id),
                )
            else:
                cursor = await db.execute(
                    "SELECT case_no, action, user_id, mod_id, reason, duration, created_at FROM mod_cases WHERE guild_id = ? ORDER BY created_at DESC",
                    (ctx.guild.id,),
                )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("📭 没有管理日志记录。")
            return

        total_pages = max(1, (len(rows) + items_per_page - 1) // items_per_page)
        page = min(page, total_pages)
        start = (page - 1) * items_per_page
        end = start + items_per_page

        fields = []
        for case_id, action, user_id, mod_id, reason, duration, created_at in rows[start:end]:
            dur_info = f" | 时长: {duration}" if duration else ""
            fields.append(
                (
                    f"#{case_id} {ACTION_NAMES.get(action, action)}（<t:{int(created_at)}:R>）",
                    f"成员: <@{user_id}> | 管理员: <@{mod_id}>{dur_info}\n原因: {reason[:80]}",
                    False,
                )
            )
        e = embed(
            "info",
            f"管理日志：{member}" if member else "管理日志",
            fields=fields,
            footer=f"第 {page}/{total_pages} 页 | 共 {len(rows)} 条记录",
        )
        await ctx.send(embed=e)

    @case_group.command(name="view", description="Show one case")
    @app_commands.describe(case="The case to show; pick from the list")
    @commands.guild_only()
    @require(manage_messages=True)
    async def case_view(self, ctx, case: int):
        row = await self._get_case(ctx.guild.id, case)
        if row is None:
            await send_notice(ctx, Notice("error", f"找不到案件 #{case}"))
            return
        await ctx.send(embed=self._case_embed(row, await self._active_until(ctx.guild, row)))

    @case_group.command(name="reason", description="Change the reason of a case")
    @app_commands.describe(case="The case to change; pick from the list", reason="The new reason")
    @commands.guild_only()
    @require(manage_messages=True)
    async def case_reason(self, ctx, case: int, *, reason: str):
        row = await self._get_case(ctx.guild.id, case)
        if row is None:
            await send_notice(ctx, Notice("error", f"找不到案件 #{case}"))
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await cases.set_reason(db, ctx.guild.id, case, reason)
        await self._send_log(
            ctx.guild,
            embed(
                "warning",
                f"案件 #{case}：原因已更新",
                fields=[("之前", row["reason"], False), ("之后", reason, False), ("管理员", ctx.author.mention)],
                timestamp=discord.utils.utcnow(),
            ),
        )
        await send_notice(ctx, Notice("success", f"案件 #{case} 的原因已更新"))

    @case_group.command(name="duration", description="Change how long an active timeout or temporary ban lasts")
    @app_commands.describe(case="The active timeout or temporary ban; pick from the list", duration="The new length, counted from now")
    @commands.guild_only()
    @require(manage_messages=True)
    async def case_duration(self, ctx, case: int, duration: str):
        row = await self._get_case(ctx.guild.id, case)
        if row is None:
            await send_notice(ctx, Notice("error", f"找不到案件 #{case}"))
            return
        if await self._active_until(ctx.guild, row) is None:
            await send_notice(ctx, Notice("error", "这个案件没有可以修改的时长"))
            return
        mute = row["action"] == "mute"
        needed = "moderate_members" if mute else "ban_members"
        if not getattr(ctx.author.guild_permissions, needed):
            raise commands.MissingPermissions([needed])
        if not getattr(ctx.guild.me.guild_permissions, needed):
            raise commands.BotMissingPermissions([needed])
        seconds = await Duration("mute" if mute else "ban")().convert(ctx, duration)
        new_until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        if mute:
            await ctx.guild.get_member(row["user_id"]).timeout(new_until, reason=f"{ctx.author}: 修改案件 #{case} 的时长")
        else:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE tempbans SET unban_at = ? WHERE guild_id = ? AND user_id = ?",
                    (time.time() + seconds, ctx.guild.id, row["user_id"]),
                )
                await db.commit()
        text = self._format_duration(seconds)
        async with aiosqlite.connect(DB_PATH) as db:
            await cases.set_duration(db, ctx.guild.id, case, text)
        await self._send_log(
            ctx.guild,
            embed(
                "warning",
                f"案件 #{case}：时长已更新",
                fields=[("之前", row["duration"] or "—"), ("之后", text), ("管理员", ctx.author.mention)],
                timestamp=discord.utils.utcnow(),
            ),
        )
        await send_notice(ctx, Notice("success", f"案件 #{case} 将在 <t:{int(new_until.timestamp())}:R> 解除"))

    case_duration.autocomplete("duration")(duration_autocomplete("mute"))

    @case_view.autocomplete("case")
    @case_reason.autocomplete("case")
    async def _case_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                rows = await cases.recent_cases(db, interaction.guild.id)
        except Exception:
            return []
        return choices([(self._case_label(interaction.guild, c), c["case_no"]) for c in rows], current)

    @case_duration.autocomplete("case")
    async def _case_duration_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                rows = await cases.recent_cases(db, interaction.guild.id, limit=50, actions=("mute", "tempban"))
            items = []
            for case in rows:
                until = await self._active_until(interaction.guild, case)
                if until is None:
                    continue
                left = max(60, int((until - discord.utils.utcnow()).total_seconds()) // 60 * 60)
                zh = is_zh(interaction)
                suffix = f" 剩 {durations.label(left, True)}" if zh else f" {durations.label(left, False)} left"
                items.append((self._case_label(interaction.guild, case) + suffix, case["case_no"]))
        except Exception:
            return []
        return choices(items, current)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
