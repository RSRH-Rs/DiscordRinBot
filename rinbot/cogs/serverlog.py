# cogs/serverlog.py
# RinBot — 服务器审计日志
# 监听 Discord 服务器事件并转发到日志频道（区别于 botlog 的 bot 内部日志）

import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timezone
from typing import Literal, Optional

from _botlog_helper import audit

DB_PATH = "serverlog.db"

# 事件分类元数据（顺序即 status 展示顺序）
CATEGORY_META = {
    "message": {"emoji": "💬", "label": "消息变更", "desc": "删除 / 编辑 / 批量删除"},
    "member": {"emoji": "🚪", "label": "成员进出", "desc": "加入 / 离开 / 被踢"},
    "member_update": {
        "emoji": "✏️",
        "label": "成员更新",
        "desc": "昵称 / 身份组 / 超时",
    },
    "ban": {"emoji": "🔨", "label": "封禁记录", "desc": "封禁 / 解封"},
    "channel": {"emoji": "📁", "label": "频道变更", "desc": "创建 / 删除 / 修改"},
    "role": {"emoji": "🏷️", "label": "身份组变更", "desc": "创建 / 删除 / 修改"},
    "voice": {"emoji": "🔊", "label": "语音活动", "desc": "进入 / 离开 / 移动"},
    "server": {"emoji": "🛠️", "label": "服务器更新", "desc": "服务器设置 / 表情"},
}
# 默认开启的分类（member_update 与 voice 较吵，默认关闭）
DEFAULT_CATEGORIES = {"message", "member", "ban", "channel", "role", "server"}


class ServerLog(commands.Cog):
    """服务器审计日志 — 记录消息/成员/频道/身份组/封禁等事件"""

    def __init__(self, bot):
        self.bot = bot
        # 缓存: {guild_id: {"channel_id": int, "enabled": bool,
        #                   "categories": set[str], "ignored": set[int]}}
        self._cache: dict[int, dict] = {}

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS serverlog_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                categories TEXT DEFAULT '',
                ignored_channels TEXT DEFAULT ''
            )""")
            await db.commit()

            cursor = await db.execute(
                "SELECT guild_id, channel_id, enabled, categories, ignored_channels FROM serverlog_config"
            )
            for gid, ch, en, cats, ign in await cursor.fetchall():
                self._cache[gid] = {
                    "channel_id": ch,
                    "enabled": bool(en),
                    "categories": set(cats.split(",")) if cats else set(),
                    "ignored": {int(x) for x in ign.split(",") if x} if ign else set(),
                }
        print("✅ 服务器审计日志模块已准备就绪!")

    # ─── 配置读写 ───

    def get_config(self, guild_id: int) -> dict:
        return self._cache.get(
            guild_id,
            {"channel_id": 0, "enabled": False, "categories": set(), "ignored": set()},
        )

    async def _save(self, guild_id: int):
        cfg = self._cache[guild_id]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO serverlog_config "
                "(guild_id, channel_id, enabled, categories, ignored_channels) VALUES (?, ?, ?, ?, ?)",
                (
                    guild_id,
                    cfg["channel_id"],
                    int(cfg["enabled"]),
                    ",".join(sorted(cfg["categories"])),
                    ",".join(str(x) for x in cfg["ignored"]),
                ),
            )
            await db.commit()

    def _ensure(self, guild_id: int) -> dict:
        if guild_id not in self._cache:
            self._cache[guild_id] = {
                "channel_id": 0,
                "enabled": True,
                "categories": set(DEFAULT_CATEGORIES),
                "ignored": set(),
            }
        return self._cache[guild_id]

    # ─── 发送核心 ───

    async def _send(self, guild_id: int, category: str, embed: discord.Embed):
        cfg = self.get_config(guild_id)
        if not cfg["enabled"] or not cfg["channel_id"]:
            return
        if category not in cfg["categories"]:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(cfg["channel_id"])
        if not channel:
            return
        embed.timestamp = datetime.now(timezone.utc)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    def _is_ignored(self, guild_id: int, channel_id: int) -> bool:
        cfg = self.get_config(guild_id)
        # 跳过被忽略的频道，以及日志频道自身（防回环）
        return channel_id in cfg["ignored"] or channel_id == cfg["channel_id"]

    async def _actor(self, guild, action, target_id=None):
        """尽力从审计日志反查操作者（需 View Audit Log 权限，10 秒内的最近条目）"""
        me = guild.me
        if not me or not me.guild_permissions.view_audit_log:
            return None
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                tgt = getattr(entry.target, "id", None)
                if target_id is None or tgt == target_id:
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                        return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    # ───────────── 消息事件 ─────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if self._is_ignored(message.guild.id, message.channel.id):
            return
        embed = discord.Embed(
            title="💬 消息被删除",
            description=message.content[:2000] or "*（无文字内容）*",
            color=0xE24B4A,
        )
        embed.add_field(name="作者", value=message.author.mention, inline=True)
        embed.add_field(name="频道", value=message.channel.mention, inline=True)
        if message.attachments:
            embed.add_field(
                name="附件",
                value="\n".join(a.filename for a in message.attachments)[:1000],
                inline=False,
            )
        entry = await self._actor(
            message.guild, discord.AuditLogAction.message_delete, message.author.id
        )
        if entry:
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
        embed.set_footer(text=f"作者 ID: {message.author.id}")
        await self._send(message.guild.id, "message", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:  # 嵌入加载等非内容编辑
            return
        if self._is_ignored(after.guild.id, after.channel.id):
            return
        embed = discord.Embed(title="✏️ 消息被编辑", color=0xEF9F27, url=after.jump_url)
        embed.add_field(
            name="之前", value=(before.content[:1000] or "*（空）*"), inline=False
        )
        embed.add_field(
            name="之后", value=(after.content[:1000] or "*（空）*"), inline=False
        )
        embed.add_field(name="作者", value=after.author.mention, inline=True)
        embed.add_field(name="频道", value=after.channel.mention, inline=True)
        embed.set_footer(text=f"作者 ID: {after.author.id}")
        await self._send(after.guild.id, "message", embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages or not messages[0].guild:
            return
        ch = messages[0].channel
        if self._is_ignored(messages[0].guild.id, ch.id):
            return
        embed = discord.Embed(
            title="🧹 批量删除消息",
            description=f"在 {ch.mention} 删除了 **{len(messages)}** 条消息。",
            color=0x992D22,
        )
        await self._send(messages[0].guild.id, "message", embed)

    # ───────────── 成员事件 ─────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="🚪 成员加入",
            description=f"{member.mention} 加入了服务器",
            color=0x57F287,
        )
        embed.add_field(
            name="账号创建于",
            value=discord.utils.format_dt(member.created_at, "R"),
            inline=True,
        )
        embed.add_field(
            name="当前成员数", value=str(member.guild.member_count), inline=True
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"用户 ID: {member.id}")
        await self._send(member.guild.id, "member", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # 若实为封禁，交给 on_member_ban 处理，避免重复
        if await self._actor(member.guild, discord.AuditLogAction.ban, member.id):
            return
        # 尝试区分主动离开与被踢
        entry = await self._actor(member.guild, discord.AuditLogAction.kick, member.id)
        if entry:
            embed = discord.Embed(
                title="👢 成员被踢出",
                description=f"{member} 被踢出服务器",
                color=0xE67E22,
            )
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
            if entry.reason:
                embed.add_field(name="原因", value=entry.reason[:1000], inline=True)
        else:
            embed = discord.Embed(
                title="🚪 成员离开",
                description=f"**{member}** 离开了服务器",
                color=0x95A5A6,
            )
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(
                name="曾持有身份组", value=" ".join(roles)[:1000], inline=False
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"用户 ID: {member.id}")
        await self._send(member.guild.id, "member", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild_id = after.guild.id
        # 昵称
        if before.nick != after.nick:
            embed = discord.Embed(title="✏️ 昵称变更", color=0x5865F2)
            embed.add_field(name="成员", value=after.mention, inline=False)
            embed.add_field(name="之前", value=before.nick or "*（无）*", inline=True)
            embed.add_field(name="之后", value=after.nick or "*（无）*", inline=True)
            embed.set_footer(text=f"用户 ID: {after.id}")
            await self._send(guild_id, "member_update", embed)
        # 身份组
        if set(before.roles) != set(after.roles):
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            embed = discord.Embed(title="🏷️ 成员身份组变更", color=0x5865F2)
            embed.add_field(name="成员", value=after.mention, inline=False)
            if added:
                embed.add_field(name="新增", value=" ".join(added)[:1000], inline=False)
            if removed:
                embed.add_field(
                    name="移除", value=" ".join(removed)[:1000], inline=False
                )
            embed.set_footer(text=f"用户 ID: {after.id}")
            await self._send(guild_id, "member_update", embed)
        # 超时（禁言）
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                embed = discord.Embed(
                    title="⏳ 成员被超时禁言",
                    description=f"{after.mention} 将被禁言至 {discord.utils.format_dt(after.timed_out_until, 'F')}",
                    color=0xE67E22,
                )
            else:
                embed = discord.Embed(
                    title="✅ 成员超时已解除",
                    description=f"{after.mention} 的禁言已解除",
                    color=0x57F287,
                )
            embed.set_footer(text=f"用户 ID: {after.id}")
            await self._send(guild_id, "member_update", embed)

    # ───────────── 封禁事件 ─────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user):
        embed = discord.Embed(
            title="🔨 成员被封禁", description=f"**{user}** 被封禁", color=0xE24B4A
        )
        entry = await self._actor(guild, discord.AuditLogAction.ban, user.id)
        if entry:
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
            if entry.reason:
                embed.add_field(name="原因", value=entry.reason[:1000], inline=True)
        embed.set_footer(text=f"用户 ID: {user.id}")
        await self._send(guild.id, "ban", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user):
        embed = discord.Embed(
            title="🕊️ 成员被解封", description=f"**{user}** 被解除封禁", color=0x57F287
        )
        entry = await self._actor(guild, discord.AuditLogAction.unban, user.id)
        if entry:
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
        embed.set_footer(text=f"用户 ID: {user.id}")
        await self._send(guild.id, "ban", embed)

    # ───────────── 频道事件 ─────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = discord.Embed(
            title="📁 频道已创建",
            description=f"{channel.mention}（`{channel.name}`）",
            color=0x57F287,
        )
        entry = await self._actor(
            channel.guild, discord.AuditLogAction.channel_create, channel.id
        )
        if entry:
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
        await self._send(channel.guild.id, "channel", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = discord.Embed(
            title="🗑️ 频道已删除", description=f"`{channel.name}`", color=0xE24B4A
        )
        entry = await self._actor(
            channel.guild, discord.AuditLogAction.channel_delete, channel.id
        )
        if entry:
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
        await self._send(channel.guild.id, "channel", embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"名称: `{before.name}` → `{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append("主题已修改")
        if getattr(before, "slowmode_delay", None) != getattr(
            after, "slowmode_delay", None
        ):
            changes.append(f"慢速: {getattr(after, 'slowmode_delay', 0)}s")
        if getattr(before, "nsfw", None) != getattr(after, "nsfw", None):
            changes.append(f"NSFW: {getattr(after, 'nsfw', False)}")
        if not changes:
            return
        embed = discord.Embed(
            title="📂 频道已修改",
            description=f"{after.mention}\n" + "\n".join(changes),
            color=0xEF9F27,
        )
        await self._send(after.guild.id, "channel", embed)

    # ───────────── 身份组事件 ─────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = discord.Embed(
            title="🏷️ 身份组已创建",
            description=f"{role.mention}（`{role.name}`）",
            color=0x57F287,
        )
        entry = await self._actor(
            role.guild, discord.AuditLogAction.role_create, role.id
        )
        if entry:
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
        await self._send(role.guild.id, "role", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = discord.Embed(
            title="🗑️ 身份组已删除", description=f"`{role.name}`", color=0xE24B4A
        )
        entry = await self._actor(
            role.guild, discord.AuditLogAction.role_delete, role.id
        )
        if entry:
            embed.add_field(name="操作者", value=entry.user.mention, inline=True)
        await self._send(role.guild.id, "role", embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name != after.name:
            changes.append(f"名称: `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"颜色: {before.color} → {after.color}")
        if before.hoist != after.hoist:
            changes.append(f"单独显示: {after.hoist}")
        if before.mentionable != after.mentionable:
            changes.append(f"可被提及: {after.mentionable}")
        if before.permissions != after.permissions:
            changes.append("权限已修改")
        if not changes:
            return
        embed = discord.Embed(
            title="🏷️ 身份组已修改",
            description=f"{after.mention}\n" + "\n".join(changes),
            color=0xEF9F27,
        )
        await self._send(after.guild.id, "role", embed)

    # ───────────── 服务器事件 ─────────────

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"名称: `{before.name}` → `{after.name}`")
        if before.owner_id != after.owner_id:
            changes.append(f"所有者已转移给 <@{after.owner_id}>")
        if before.icon != after.icon:
            changes.append("服务器图标已更换")
        if not changes:
            return
        embed = discord.Embed(
            title="🛠️ 服务器设置已更新",
            description="\n".join(changes),
            color=0x85B7EB,
        )
        await self._send(after.id, "server", embed)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        added = [e for e in after if e not in before]
        removed = [e for e in before if e not in after]
        if not added and not removed:
            return
        embed = discord.Embed(title="😀 表情已更新", color=0x85B7EB)
        if added:
            embed.add_field(
                name="新增", value=" ".join(str(e) for e in added)[:1000], inline=False
            )
        if removed:
            embed.add_field(
                name="移除",
                value=", ".join(e.name for e in removed)[:1000],
                inline=False,
            )
        await self._send(guild.id, "server", embed)

    # ───────────── 语音事件 ─────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot or before.channel == after.channel:
            return
        if before.channel is None:
            embed = discord.Embed(
                title="🔊 加入语音",
                description=f"{member.mention} → {after.channel.mention}",
                color=0x57F287,
            )
        elif after.channel is None:
            embed = discord.Embed(
                title="🔇 离开语音",
                description=f"{member.mention} ← {before.channel.mention}",
                color=0x95A5A6,
            )
        else:
            embed = discord.Embed(
                title="🔀 切换语音频道",
                description=f"{member.mention}: {before.channel.mention} → {after.channel.mention}",
                color=0x9B59B6,
            )
        embed.set_footer(text=f"用户 ID: {member.id}")
        await self._send(member.guild.id, "voice", embed)

    # ───────────── 配置指令 ─────────────

    @commands.hybrid_group(
        name="serverlog", aliases=["slog"], description="服务器审计日志配置"
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def serverlog(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send(
                "用法: `/serverlog status | channel | toggle | enable | disable | ignore`",
                ephemeral=True,
            )

    @serverlog.command(name="channel", description="[管理] 设置日志频道并开启记录")
    @commands.has_permissions(manage_guild=True)
    async def sl_channel(self, ctx, channel: discord.TextChannel):
        cfg = self._ensure(ctx.guild.id)
        cfg["channel_id"] = channel.id
        cfg["enabled"] = True
        await self._save(ctx.guild.id)
        await audit(
            self.bot,
            ctx.guild.id,
            "设置审计日志频道",
            **{"操作者": ctx.author.mention, "频道": channel.mention},
        )
        await ctx.send(f"✅ 审计日志已开启，记录到 {channel.mention}", ephemeral=True)

    @serverlog.command(name="toggle", description="[管理] 开关某个事件分类")
    @commands.has_permissions(manage_guild=True)
    async def sl_toggle(
        self,
        ctx,
        category: Literal[
            "message",
            "member",
            "member_update",
            "ban",
            "channel",
            "role",
            "voice",
            "server",
        ],
    ):
        cfg = self._ensure(ctx.guild.id)
        if category in cfg["categories"]:
            cfg["categories"].discard(category)
            state = "关闭"
        else:
            cfg["categories"].add(category)
            state = "开启"
        await self._save(ctx.guild.id)
        meta = CATEGORY_META[category]
        await ctx.send(
            f"{meta['emoji']} **{meta['label']}** 记录已{state}。", ephemeral=True
        )

    @serverlog.command(name="enable", description="[管理] 启用审计日志")
    @commands.has_permissions(manage_guild=True)
    async def sl_enable(self, ctx):
        cfg = self._ensure(ctx.guild.id)
        if not cfg["channel_id"]:
            await ctx.send(
                "❌ 请先用 `/serverlog channel` 设置日志频道。", ephemeral=True
            )
            return
        cfg["enabled"] = True
        await self._save(ctx.guild.id)
        await ctx.send("✅ 审计日志已启用。", ephemeral=True)

    @serverlog.command(name="disable", description="[管理] 停用审计日志")
    @commands.has_permissions(manage_guild=True)
    async def sl_disable(self, ctx):
        cfg = self._ensure(ctx.guild.id)
        cfg["enabled"] = False
        await self._save(ctx.guild.id)
        await ctx.send("🛑 审计日志已停用（配置保留）。", ephemeral=True)

    @serverlog.command(name="ignore", description="[管理] 忽略某个频道的日志")
    @commands.has_permissions(manage_guild=True)
    async def sl_ignore(self, ctx, channel: discord.TextChannel):
        cfg = self._ensure(ctx.guild.id)
        cfg["ignored"].add(channel.id)
        await self._save(ctx.guild.id)
        await ctx.send(f"🙈 已忽略 {channel.mention} 的消息日志。", ephemeral=True)

    @serverlog.command(name="unignore", description="[管理] 取消忽略某个频道")
    @commands.has_permissions(manage_guild=True)
    async def sl_unignore(self, ctx, channel: discord.TextChannel):
        cfg = self._ensure(ctx.guild.id)
        cfg["ignored"].discard(channel.id)
        await self._save(ctx.guild.id)
        await ctx.send(f"👀 已恢复 {channel.mention} 的消息日志。", ephemeral=True)

    @serverlog.command(name="status", description="查看当前审计日志配置")
    @commands.has_permissions(manage_guild=True)
    async def sl_status(self, ctx):
        cfg = self.get_config(ctx.guild.id)
        ch = ctx.guild.get_channel(cfg["channel_id"]) if cfg["channel_id"] else None
        embed = discord.Embed(
            title="🗃️ 服务器审计日志配置",
            color=(
                discord.Color.green() if cfg["enabled"] else discord.Color.light_grey()
            ),
        )
        embed.add_field(
            name="状态", value="🟢 开启" if cfg["enabled"] else "⚪ 关闭", inline=True
        )
        embed.add_field(
            name="日志频道", value=ch.mention if ch else "未设置", inline=True
        )
        lines = []
        for key, meta in CATEGORY_META.items():
            mark = "✅" if key in cfg["categories"] else "⬜"
            lines.append(f"{mark} {meta['emoji']} **{meta['label']}** — {meta['desc']}")
        embed.add_field(name="事件分类", value="\n".join(lines), inline=False)
        if cfg["ignored"]:
            embed.add_field(
                name="忽略的频道",
                value=" ".join(f"<#{c}>" for c in cfg["ignored"])[:1000],
                inline=False,
            )
        embed.set_footer(text="用 /serverlog toggle <分类> 开关单项")
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ServerLog(bot))
