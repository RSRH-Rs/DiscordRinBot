# cogs/reactionroles.py
# RinBot — 反应身份组模块
# 功能：
#   • /rr_create — 创建一个反应身份组面板（支持多组 emoji-角色 映射）
#   • /rr_add    — 向已有面板添加 emoji-角色 映射
#   • /rr_remove — 从面板移除一个映射
#   • /rr_list   — 列出当前服务器所有反应身份组面板
#   • /rr_delete — 删除一个面板
#   • 自动监听 reaction_add / reaction_remove 分配/移除身份组

import discord
from discord.ext import commands
from discord.ui import View, Button, RoleSelect
import aiosqlite
import json
from typing import Optional

DB_PATH = "reactionroles.db"


class ReactionRoles(commands.Cog):
    """反应身份组 — 点击 Emoji 自助获取/移除身份组"""

    def __init__(self, bot):
        self.bot = bot
        # 内存缓存: {message_id: {emoji_str: role_id}}
        self._cache: dict[int, dict[str, int]] = {}

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS rr_panels (
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    title TEXT DEFAULT '身份组选择',
                    mappings TEXT DEFAULT '{}'
                )
            """)
            await db.commit()

            # 加载缓存
            cursor = await db.execute("SELECT message_id, mappings FROM rr_panels")
            rows = await cursor.fetchall()
            for msg_id, mappings_json in rows:
                try:
                    self._cache[msg_id] = json.loads(mappings_json)
                except json.JSONDecodeError:
                    self._cache[msg_id] = {}

        print("✅ 反应身份组系统已准备就绪！")

    async def _save_mappings(self, message_id: int, mappings: dict):
        self._cache[message_id] = mappings
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE rr_panels SET mappings = ? WHERE message_id = ?",
                (json.dumps(mappings), message_id),
            )
            await db.commit()

    async def _rebuild_embed(self, message: discord.Message, title: str, mappings: dict, guild: discord.Guild):
        """重建面板 Embed"""
        lines = []
        for emoji_str, role_id in mappings.items():
            role = guild.get_role(role_id)
            if role:
                lines.append(f"{emoji_str} → {role.mention}")
        embed = discord.Embed(
            title=f"🏷 {title}",
            description="\n".join(lines) if lines else "暂无映射，使用 `/rr_add` 添加。",
            color=discord.Color.teal(),
        )
        embed.set_footer(text="点击下方反应获取对应身份组 | 再次点击移除")
        await message.edit(embed=embed)

    # ─── 指令：rr_create ───

    @commands.hybrid_command(name="rr_create", description="[管理] 创建一个反应身份组面板")
    @commands.has_permissions(manage_roles=True)
    async def rr_create(self, ctx, title: str = "身份组选择", *, description: str = "点击下方的表情来获取对应身份组！"):
        """
        title: 面板标题
        description: 面板说明文字
        """
        await ctx.defer()

        embed = discord.Embed(
            title=f"🏷 {title}",
            description=f"{description}\n\n*使用 `/rr_add` 来添加 emoji-身份组 映射*",
            color=discord.Color.teal(),
        )
        embed.set_footer(text="点击下方反应获取对应身份组 | 再次点击移除")

        msg = await ctx.send(embed=embed)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO rr_panels (message_id, channel_id, guild_id, title, mappings) VALUES (?, ?, ?, ?, ?)",
                (msg.id, ctx.channel.id, ctx.guild.id, title, "{}"),
            )
            await db.commit()

        self._cache[msg.id] = {}
        await ctx.send(f"✅ 面板已创建！消息 ID: `{msg.id}`\n用 `/rr_add {msg.id} <emoji> <@角色>` 添加映射。", ephemeral=True)

    # ─── 指令：rr_add ───

    @commands.hybrid_command(name="rr_add", description="[管理] 向面板添加 emoji → 身份组 映射")
    @commands.has_permissions(manage_roles=True)
    async def rr_add(self, ctx, message_id: str, emoji: str, role: discord.Role):
        """
        message_id: 面板消息 ID
        emoji: 要使用的 emoji
        role: 对应的身份组
        """
        await ctx.defer(ephemeral=True)
        msg_id = int(message_id)

        if msg_id not in self._cache:
            await ctx.send("❌ 找不到该面板，请确认消息 ID 正确。", ephemeral=True)
            return

        # 权限检查
        if role >= ctx.guild.me.top_role:
            await ctx.send("❌ 该身份组高于或等于我的最高身份组，无法分配。", ephemeral=True)
            return

        mappings = self._cache[msg_id]
        mappings[emoji] = role.id
        await self._save_mappings(msg_id, mappings)

        # 获取面板消息并更新
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT channel_id, title FROM rr_panels WHERE message_id = ?", (msg_id,))
            row = await cursor.fetchone()

        if row:
            channel = ctx.guild.get_channel(row[0])
            if channel:
                try:
                    message = await channel.fetch_message(msg_id)
                    await self._rebuild_embed(message, row[1], mappings, ctx.guild)
                    await message.add_reaction(emoji)
                except discord.NotFound:
                    pass

        await ctx.send(f"✅ 已添加: {emoji} → {role.mention}", ephemeral=True)

    # ─── 指令：rr_remove ───

    @commands.hybrid_command(name="rr_remove", description="[管理] 从面板移除一个 emoji 映射")
    @commands.has_permissions(manage_roles=True)
    async def rr_remove(self, ctx, message_id: str, emoji: str):
        await ctx.defer(ephemeral=True)
        msg_id = int(message_id)

        if msg_id not in self._cache:
            await ctx.send("❌ 找不到该面板。", ephemeral=True)
            return

        mappings = self._cache[msg_id]
        if emoji not in mappings:
            await ctx.send("❌ 该 emoji 不在面板映射中。", ephemeral=True)
            return

        del mappings[emoji]
        await self._save_mappings(msg_id, mappings)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT channel_id, title FROM rr_panels WHERE message_id = ?", (msg_id,))
            row = await cursor.fetchone()
        if row:
            channel = ctx.guild.get_channel(row[0])
            if channel:
                try:
                    message = await channel.fetch_message(msg_id)
                    await self._rebuild_embed(message, row[1], mappings, ctx.guild)
                    await message.clear_reaction(emoji)
                except (discord.NotFound, discord.Forbidden):
                    pass

        await ctx.send(f"✅ 已移除: {emoji}", ephemeral=True)

    # ─── 指令：rr_list ───

    @commands.hybrid_command(name="rr_list", description="[管理] 列出所有反应身份组面板")
    @commands.has_permissions(manage_roles=True)
    async def rr_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT message_id, channel_id, title, mappings FROM rr_panels WHERE guild_id = ?",
                (ctx.guild.id,),
            )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("📭 当前服务器没有反应身份组面板。")
            return

        embed = discord.Embed(title="🏷 反应身份组面板列表", color=discord.Color.teal())
        for msg_id, ch_id, title, mappings_json in rows:
            mappings = json.loads(mappings_json)
            channel = ctx.guild.get_channel(ch_id)
            ch_name = channel.mention if channel else f"#{ch_id}"
            count = len(mappings)
            embed.add_field(
                name=f"{title}",
                value=f"频道: {ch_name}\n消息 ID: `{msg_id}`\n映射数量: {count}",
                inline=False,
            )

        await ctx.send(embed=embed)

    # ─── 指令：rr_delete ───

    @commands.hybrid_command(name="rr_delete", description="[管理] 删除一个反应身份组面板")
    @commands.has_permissions(manage_roles=True)
    async def rr_delete(self, ctx, message_id: str):
        await ctx.defer(ephemeral=True)
        msg_id = int(message_id)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT channel_id FROM rr_panels WHERE message_id = ? AND guild_id = ?",
                (msg_id, ctx.guild.id),
            )
            row = await cursor.fetchone()
            if not row:
                await ctx.send("❌ 找不到该面板。", ephemeral=True)
                return

            await db.execute("DELETE FROM rr_panels WHERE message_id = ?", (msg_id,))
            await db.commit()

        self._cache.pop(msg_id, None)

        # 尝试删除原消息
        channel = ctx.guild.get_channel(row[0])
        if channel:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        await ctx.send("✅ 面板已删除。", ephemeral=True)

    # ─── 反应监听 ───

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member and payload.member.bot:
            return

        mappings = self._cache.get(payload.message_id)
        if not mappings:
            # DB fallback — pick up panels created via web dashboard
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    cur = await db.execute("SELECT mappings FROM rr_panels WHERE message_id=?", (payload.message_id,))
                    row = await cur.fetchone()
                    if row:
                        mappings = json.loads(row[0])
                        self._cache[payload.message_id] = mappings
                    else:
                        return
            except Exception:
                return

        emoji_str = str(payload.emoji)
        role_id = mappings.get(emoji_str)
        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role = guild.get_role(role_id)
        member = payload.member or guild.get_member(payload.user_id)

        if role and member:
            try:
                await member.add_roles(role, reason="反应身份组")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        mappings = self._cache.get(payload.message_id)
        if not mappings:
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    cur = await db.execute("SELECT mappings FROM rr_panels WHERE message_id=?", (payload.message_id,))
                    row = await cur.fetchone()
                    if row:
                        mappings = json.loads(row[0])
                        self._cache[payload.message_id] = mappings
                    else:
                        return
            except Exception:
                return

        emoji_str = str(payload.emoji)
        role_id = mappings.get(emoji_str)
        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)

        if role and member and not member.bot:
            try:
                await member.remove_roles(role, reason="反应身份组移除")
            except discord.Forbidden:
                pass


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
