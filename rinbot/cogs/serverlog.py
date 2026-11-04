# cogs/serverlog.py
# RinBot — 服务器审计日志
# 监听 Discord 服务器事件并转发到日志频道（区别于 botlog 的 bot 内部日志）
# 开关、日志频道和事件分类在控制台的「服务器事件日志」里改；/serverlog ignore | unignore 管跳过的频道（控制台做不到）

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import os
from datetime import datetime, timezone

from _botlog_helper import audit
from _perms import require
from _messages import embed, send, send_moved
from rincore.embeds import event_kind

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "serverlog.db"
)

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
        await self._load_cache()
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("serverlog", self.reload_guild)
        print("✅ 服务器审计日志模块已准备就绪!")

    def cog_unload(self):
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("serverlog", self.reload_guild)

    async def _load_cache(self):
        cache = {}
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT guild_id, channel_id, enabled, categories, ignored_channels FROM serverlog_config"
            )
            for gid, ch, en, cats, ign in await cursor.fetchall():
                cache[gid] = self._build_entry(ch, en, cats, ign)
        self._cache = cache

    @staticmethod
    def _build_entry(ch, en, cats, ign) -> dict:
        return {
            "channel_id": ch,
            "enabled": bool(en),
            "categories": set(cats.split(",")) if cats else set(),
            "ignored": {int(x) for x in ign.split(",") if x} if ign else set(),
        }

    # 网页仪表盘保存后由变更日志回调：只重读该服务器的一行配置
    async def reload_guild(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT channel_id, enabled, categories, ignored_channels "
                "FROM serverlog_config WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cursor.fetchone()
        if row:
            self._cache[guild_id] = self._build_entry(*row)
        else:
            self._cache.pop(guild_id, None)

    # ─── 配置读写 ───

    def get_config(self, guild_id: int) -> dict:
        return self._cache.get(
            guild_id,
            {"channel_id": 0, "enabled": False, "categories": set(), "ignored": set()},
        )

    # ─── 发送核心 ───

    async def _send(self, guild_id: int, category: str, card: discord.Embed):
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
        card.timestamp = datetime.now(timezone.utc)
        try:
            await channel.send(embed=card)
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
        fields = [("作者", message.author.mention), ("频道", message.channel.mention)]
        if message.attachments:
            fields.append(("附件", "\n".join(a.filename for a in message.attachments)[:1000], False))
        entry = await self._actor(
            message.guild, discord.AuditLogAction.message_delete, message.author.id
        )
        if entry:
            fields.append(("操作者", entry.user.mention))
        card = embed(
            event_kind("message_delete"),
            "消息被删除",
            message.content[:2000] or "*（无文字内容）*",
            fields=fields,
            footer=f"作者 ID: {message.author.id}",
        )
        await self._send(message.guild.id, "message", card)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:  # 嵌入加载等非内容编辑
            return
        if self._is_ignored(after.guild.id, after.channel.id):
            return
        card = embed(
            event_kind("message_edit"),
            "消息被编辑",
            url=after.jump_url,
            fields=[
                ("之前", before.content[:1000] or "*（空）*", False),
                ("之后", after.content[:1000] or "*（空）*", False),
                ("作者", after.author.mention),
                ("频道", after.channel.mention),
            ],
            footer=f"作者 ID: {after.author.id}",
        )
        await self._send(after.guild.id, "message", card)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages or not messages[0].guild:
            return
        ch = messages[0].channel
        if self._is_ignored(messages[0].guild.id, ch.id):
            return
        card = embed(
            event_kind("message_bulk_delete"),
            "批量删除消息",
            f"在 {ch.mention} 删除了 **{len(messages)}** 条消息。",
        )
        await self._send(messages[0].guild.id, "message", card)

    # ───────────── 成员事件 ─────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        card = embed(
            event_kind("member_join"),
            "成员加入",
            f"{member.mention} 加入了服务器",
            fields=[
                ("账号创建于", discord.utils.format_dt(member.created_at, "R")),
                ("当前成员数", str(member.guild.member_count)),
            ],
            footer=f"用户 ID: {member.id}",
        )
        card.set_thumbnail(url=member.display_avatar.url)
        await self._send(member.guild.id, "member", card)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # 若实为封禁，交给 on_member_ban 处理，避免重复
        if await self._actor(member.guild, discord.AuditLogAction.ban, member.id):
            return
        # 尝试区分主动离开与被踢
        entry = await self._actor(member.guild, discord.AuditLogAction.kick, member.id)
        if entry:
            kind, title, text = event_kind("member_kick"), "成员被踢出", f"{member} 被踢出服务器"
            fields = [("操作者", entry.user.mention), ("原因", (entry.reason or "")[:1000])]
        else:
            kind, title, text = event_kind("member_leave"), "成员离开", f"**{member}** 离开了服务器"
            fields = []
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            fields.append(("曾持有身份组", " ".join(roles)[:1000], False))
        card = embed(kind, title, text, fields=fields, footer=f"用户 ID: {member.id}")
        card.set_thumbnail(url=member.display_avatar.url)
        await self._send(member.guild.id, "member", card)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild_id = after.guild.id
        # 昵称
        if before.nick != after.nick:
            card = embed(
                event_kind("nick_change"),
                "昵称变更",
                fields=[
                    ("成员", after.mention, False),
                    ("之前", before.nick or "*（无）*"),
                    ("之后", after.nick or "*（无）*"),
                ],
                footer=f"用户 ID: {after.id}",
            )
            await self._send(guild_id, "member_update", card)
        # 身份组
        if set(before.roles) != set(after.roles):
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            card = embed(
                event_kind("member_roles"),
                "成员身份组变更",
                fields=[
                    ("成员", after.mention, False),
                    ("新增", " ".join(added)[:1000], False),
                    ("移除", " ".join(removed)[:1000], False),
                ],
                footer=f"用户 ID: {after.id}",
            )
            await self._send(guild_id, "member_update", card)
        # 超时（禁言）
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                card = embed(
                    event_kind("member_timeout"),
                    "成员被超时禁言",
                    f"{after.mention} 将被禁言至 {discord.utils.format_dt(after.timed_out_until, 'F')}",
                    footer=f"用户 ID: {after.id}",
                )
            else:
                card = embed(
                    event_kind("member_timeout_end"),
                    "成员超时已解除",
                    f"{after.mention} 的禁言已解除",
                    footer=f"用户 ID: {after.id}",
                )
            await self._send(guild_id, "member_update", card)

    # ───────────── 封禁事件 ─────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user):
        entry = await self._actor(guild, discord.AuditLogAction.ban, user.id)
        fields = [("操作者", entry.user.mention), ("原因", (entry.reason or "")[:1000])] if entry else []
        card = embed(
            event_kind("member_ban"), "成员被封禁", f"**{user}** 被封禁", fields=fields, footer=f"用户 ID: {user.id}"
        )
        await self._send(guild.id, "ban", card)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user):
        entry = await self._actor(guild, discord.AuditLogAction.unban, user.id)
        card = embed(
            event_kind("member_unban"),
            "成员被解封",
            f"**{user}** 被解除封禁",
            fields=[("操作者", entry.user.mention)] if entry else [],
            footer=f"用户 ID: {user.id}",
        )
        await self._send(guild.id, "ban", card)

    # ───────────── 频道事件 ─────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        entry = await self._actor(
            channel.guild, discord.AuditLogAction.channel_create, channel.id
        )
        card = embed(
            event_kind("channel_create"),
            "频道已创建",
            f"{channel.mention}（`{channel.name}`）",
            fields=[("操作者", entry.user.mention)] if entry else [],
        )
        await self._send(channel.guild.id, "channel", card)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        entry = await self._actor(
            channel.guild, discord.AuditLogAction.channel_delete, channel.id
        )
        card = embed(
            event_kind("channel_delete"),
            "频道已删除",
            f"`{channel.name}`",
            fields=[("操作者", entry.user.mention)] if entry else [],
        )
        await self._send(channel.guild.id, "channel", card)

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
        card = embed(event_kind("channel_update"), "频道已修改", f"{after.mention}\n" + "\n".join(changes))
        await self._send(after.guild.id, "channel", card)

    # ───────────── 身份组事件 ─────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        entry = await self._actor(
            role.guild, discord.AuditLogAction.role_create, role.id
        )
        card = embed(
            event_kind("role_create"),
            "身份组已创建",
            f"{role.mention}（`{role.name}`）",
            fields=[("操作者", entry.user.mention)] if entry else [],
        )
        await self._send(role.guild.id, "role", card)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        entry = await self._actor(
            role.guild, discord.AuditLogAction.role_delete, role.id
        )
        card = embed(
            event_kind("role_delete"),
            "身份组已删除",
            f"`{role.name}`",
            fields=[("操作者", entry.user.mention)] if entry else [],
        )
        await self._send(role.guild.id, "role", card)

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
        card = embed(event_kind("role_update"), "身份组已修改", f"{after.mention}\n" + "\n".join(changes))
        await self._send(after.guild.id, "role", card)

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
        card = embed(event_kind("guild_update"), "服务器设置已更新", "\n".join(changes))
        await self._send(after.id, "server", card)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        added = [e for e in after if e not in before]
        removed = [e for e in before if e not in after]
        if not added and not removed:
            return
        card = embed(
            event_kind("emoji_update"),
            "表情已更新",
            fields=[
                ("新增", " ".join(str(e) for e in added)[:1000], False),
                ("移除", ", ".join(e.name for e in removed)[:1000], False),
            ],
        )
        await self._send(guild.id, "server", card)

    # ───────────── 语音事件 ─────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot or before.channel == after.channel:
            return
        if before.channel is None:
            kind, title = event_kind("voice_join"), "加入语音"
            text = f"{member.mention} → {after.channel.mention}"
        elif after.channel is None:
            kind, title = event_kind("voice_leave"), "离开语音"
            text = f"{member.mention} ← {before.channel.mention}"
        else:
            kind, title = event_kind("voice_move"), "切换语音频道"
            text = f"{member.mention}: {before.channel.mention} → {after.channel.mention}"
        card = embed(kind, title, text, footer=f"用户 ID: {member.id}")
        await self._send(member.guild.id, "voice", card)

    # ───────────── 配置指令：忽略的频道 ─────────────

    def _ignored_field(self, guild_id: int) -> tuple:
        ignored = sorted(self.get_config(guild_id)["ignored"])
        return ("现在忽略的频道", " ".join(f"<#{c}>" for c in ignored) or "没有", False)

    async def _current_ignored(self, guild_id: int) -> set[int]:
        # 先从数据库重读：控制台刚保存、重载通知还没到时，缓存可能是旧的
        await self.reload_guild(guild_id)
        return set(self.get_config(guild_id)["ignored"])

    async def _save_ignored(self, guild_id: int, ignored: set[int]):
        """只写忽略列表这一列，控制台存的开关、频道和分类不会被盖掉；还没有配置时按默认值新建。"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO serverlog_config (guild_id, channel_id, enabled, categories, ignored_channels) "
                "VALUES (?, 0, 1, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET ignored_channels = excluded.ignored_channels",
                (guild_id, ",".join(sorted(DEFAULT_CATEGORIES)), ",".join(str(c) for c in sorted(ignored))),
            )
            await db.commit()
        await self.reload_guild(guild_id)

    @commands.hybrid_group(name="serverlog", aliases=["slog"], description="Server event log: channels to skip")
    @commands.guild_only()
    @require(manage_guild=True)
    async def serverlog_group(self, ctx):
        if ctx.invoked_subcommand is None:
            # 旧的 r!serverlog channel 之类：开关、频道和分类已经移到控制台
            if ctx.subcommand_passed and await send_moved(ctx, f"serverlog {ctx.subcommand_passed}"):
                return
            ignored = sorted(await self._current_ignored(ctx.guild.id))
            text = " ".join(f"<#{c}>" for c in ignored) or "没有忽略任何频道。"
            await send(ctx, embed("info", "审计日志忽略的频道", text), private=True)

    @serverlog_group.command(name="ignore", description="Stop logging messages in a channel")
    @app_commands.describe(channel="The channel to skip")
    @commands.guild_only()
    @require(manage_guild=True)
    async def sl_ignore(self, ctx, channel: discord.TextChannel):
        ignored = await self._current_ignored(ctx.guild.id)
        if channel.id in ignored:
            card = embed("info", f"#{channel.name} 已经在忽略列表里了", fields=[self._ignored_field(ctx.guild.id)])
            await send(ctx, card, private=True)
            return
        await self._save_ignored(ctx.guild.id, ignored | {channel.id})
        card = embed(
            "success", f"已忽略 #{channel.name}", "这个频道里删除和编辑的消息不会再记进日志。",
            fields=[self._ignored_field(ctx.guild.id)],
        )
        await send(ctx, card, private=True)
        await audit(
            self.bot, ctx.guild.id, "忽略审计日志频道", **{"操作者": ctx.author.mention, "频道": channel.mention}
        )

    @serverlog_group.command(name="unignore", description="Log messages in a skipped channel again")
    @app_commands.describe(channel="The channel to log again")
    @commands.guild_only()
    @require(manage_guild=True)
    async def sl_unignore(self, ctx, channel: discord.TextChannel):
        ignored = await self._current_ignored(ctx.guild.id)
        if channel.id not in ignored:
            card = embed("info", f"#{channel.name} 本来就没有被忽略", fields=[self._ignored_field(ctx.guild.id)])
            await send(ctx, card, private=True)
            return
        await self._save_ignored(ctx.guild.id, ignored - {channel.id})
        card = embed(
            "success", f"已恢复记录 #{channel.name}", "这个频道里删除和编辑的消息会照常记进日志。",
            fields=[self._ignored_field(ctx.guild.id)],
        )
        await send(ctx, card, private=True)
        await audit(
            self.bot, ctx.guild.id, "恢复审计日志频道", **{"操作者": ctx.author.mention, "频道": channel.mention}
        )


async def setup(bot):
    await bot.add_cog(ServerLog(bot))
