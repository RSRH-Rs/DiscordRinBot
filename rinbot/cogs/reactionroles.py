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
import aiohttp
import json
import os
from typing import Optional
from _botlog_helper import audit, check_component
from _perms import require
from rincore import roles

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reactionroles.db"
)


class ReactionRoles(commands.Cog):
    """反应身份组 — 点击 Emoji 自助获取/移除身份组"""

    def __init__(self, bot):
        self.bot = bot
        # 内存缓存(权威): {message_id: {"mappings": {emoji: role_id}, "exclusive": bool, "guild_id": int}}
        self._cache: dict[int, dict] = {}

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS rr_panels (
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    title TEXT DEFAULT '身份组选择',
                    mappings TEXT DEFAULT '{}',
                    exclusive INTEGER DEFAULT 0
                )
            """)
            # 兼容旧 schema:加 exclusive 列(如果不存在)
            try:
                await db.execute(
                    "ALTER TABLE rr_panels ADD COLUMN exclusive INTEGER DEFAULT 0"
                )
            except Exception:
                pass
            await db.commit()

            # 加载缓存
            cursor = await db.execute(
                "SELECT message_id, guild_id, mappings, exclusive FROM rr_panels"
            )
            rows = await cursor.fetchall()
            for row in rows:
                self._cache[row[0]] = self._build_entry(*row[1:])

        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("reactionroles", self.reload_guild)
        print("✅ 反应身份组系统已准备就绪！")

    def cog_unload(self):
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("reactionroles", self.reload_guild)

    @staticmethod
    def _build_entry(guild_id, mappings_json, exclusive) -> dict:
        try:
            mappings = json.loads(mappings_json)
        except (json.JSONDecodeError, TypeError):
            return {"mappings": {}, "exclusive": False, "guild_id": guild_id}
        return {"mappings": mappings, "exclusive": bool(exclusive), "guild_id": guild_id}

    async def reload_guild(self, guild_id: int):
        """网页创建/删除面板后由变更日志回调：用数据库重建该服务器的全部缓存条目"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT message_id, mappings, exclusive FROM rr_panels WHERE guild_id = ?",
                (guild_id,),
            )
            rows = await cursor.fetchall()
        fresh = {
            msg_id: self._build_entry(guild_id, mappings_json, exclusive)
            for msg_id, mappings_json, exclusive in rows
        }
        # 先建好新条目再替换：丢弃该服务器已不存在的面板，保留其他服务器的缓存
        for msg_id in [
            m for m, e in self._cache.items() if e.get("guild_id") == guild_id
        ]:
            if msg_id not in fresh:
                self._cache.pop(msg_id, None)
        self._cache.update(fresh)

    async def _panel_for(self, ctx, msg_id: int) -> Optional[dict]:
        """按消息 ID 取本服务器的面板缓存条目；不存在或属于其他服务器时返回 None"""
        if msg_id not in self._cache:
            # 缓存未命中：可能是网页刚建的面板（同步回调还没到），先重载该服务器再判断
            await self.reload_guild(ctx.guild.id)
        entry = self._cache.get(msg_id)
        if entry is None or entry.get("guild_id") != ctx.guild.id:
            return None
        return entry

    async def _save_mappings(self, message_id: int, mappings: dict):
        entry = self._cache.get(message_id, {"mappings": {}, "exclusive": False})
        entry["mappings"] = mappings
        self._cache[message_id] = entry
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE rr_panels SET mappings = ? WHERE message_id = ?",
                (json.dumps(mappings), message_id),
            )
            await db.commit()

    async def _set_exclusive(self, message_id: int, exclusive: bool):
        entry = self._cache.get(message_id, {"mappings": {}, "exclusive": False})
        entry["exclusive"] = exclusive
        self._cache[message_id] = entry
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE rr_panels SET exclusive = ? WHERE message_id = ?",
                (int(exclusive), message_id),
            )
            await db.commit()
            await db.commit()

    def _build_components(self, mappings: dict, guild: discord.Guild) -> list:
        """从 mappings 构造按钮 components"""
        rows = []
        current = {"type": 1, "components": []}
        for emoji_str, role_id in mappings.items():
            role = guild.get_role(role_id)
            if not role:
                continue

            # 解析 emoji:Unicode / <:name:id> / <a:name:id>
            emoji_obj = None
            if emoji_str.startswith("<") and emoji_str.endswith(">"):
                inner = emoji_str.strip("<>")
                parts = inner.split(":")
                if len(parts) == 3:
                    emoji_obj = {
                        "name": parts[1],
                        "id": parts[2],
                        "animated": inner.startswith("a:"),
                    }
            else:
                emoji_obj = {"name": emoji_str}

            btn = {
                "type": 2,
                "style": 2,
                "label": role.name[:80],
                "custom_id": f"rr:{role.id}",
            }
            if emoji_obj:
                btn["emoji"] = emoji_obj

            if len(current["components"]) >= 5:
                rows.append(current)
                current = {"type": 1, "components": []}
            current["components"].append(btn)

        if current["components"]:
            rows.append(current)
        return rows

    async def _rebuild_panel(
        self,
        message: discord.Message,
        title: str,
        mappings: dict,
        guild: discord.Guild,
        description: str = "",
    ):
        """重建面板:embed + 按钮(用 raw aiohttp 绕过 discord.py http 限制)"""
        embed = discord.Embed(
            title=f"🏷 {title}",
            description=description or "点击下方按钮领取对应身份组",
            color=discord.Color.teal(),
        )
        components = self._build_components(mappings, guild)
        token = self.bot.http.token
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"https://discord.com/api/v10/channels/{message.channel.id}/messages/{message.id}",
                    headers={
                        "Authorization": f"Bot {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "embeds": [embed.to_dict()],
                        "components": components,
                    },
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        print(f"[RR rebuild] Discord {resp.status}: {body[:300]}")
        except Exception as e:
            print(f"[RR rebuild] {e}")

    # ─── 指令：rr_create ───

    @commands.hybrid_command(
        name="rr_create", description="[管理] 创建一个反应身份组面板"
    )
    @commands.guild_only()
    @require(manage_roles=True)
    async def rr_create(
        self,
        ctx,
        title: str = "身份组选择",
        exclusive: bool = False,
        *,
        description: str = "点击下方的按钮来领取身分组",
    ):
        """
        title: 面板标题
        exclusive: 单选模式(只能选一个角色,选其他会自动替换)
        description: 面板说明文字
        """
        await ctx.defer()

        full_desc = description
        if exclusive:
            full_desc = f"{description}\n\n*注:只能选一个身份组,选其他会自动替换*"
        embed = discord.Embed(
            title=f"🏷 {title}",
            description=f"{full_desc}\n\n*使用 `/rr_add` 添加身份组按钮*",
            color=discord.Color.teal(),
        )

        msg = await ctx.send(embed=embed)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO rr_panels (message_id, channel_id, guild_id, title, mappings, exclusive) VALUES (?, ?, ?, ?, ?, ?)",
                (msg.id, ctx.channel.id, ctx.guild.id, title, "{}", int(exclusive)),
            )
            await db.commit()

        self._cache[msg.id] = {
            "mappings": {},
            "exclusive": exclusive,
            "guild_id": ctx.guild.id,
        }
        await audit(
            self.bot,
            ctx.guild.id,
            "创建身份组面板",
            **{
                "操作者": ctx.author.mention,
                "频道": ctx.channel.mention,
                "标题": title,
                "单选模式": "是" if exclusive else "否",
            },
        )
        mode_hint = "(单选模式)" if exclusive else ""
        await ctx.send(
            f"✅ 面板已创建{mode_hint}!消息 ID: `{msg.id}`\n用 `/rr_add {msg.id} <emoji> <@角色>` 添加按钮。",
            ephemeral=True,
        )

    # ─── 指令：rr_add ───

    @commands.hybrid_command(
        name="rr_add", description="[管理] 向面板添加 emoji → 身份组 映射"
    )
    @commands.guild_only()
    @require(manage_roles=True)
    async def rr_add(self, ctx, message_id: str, emoji: str, role: discord.Role):
        """
        message_id: 面板消息 ID
        emoji: 要使用的 emoji
        role: 对应的身份组
        """
        await ctx.defer(ephemeral=True)
        msg_id = int(message_id)

        entry = await self._panel_for(ctx, msg_id)
        if entry is None:
            await ctx.send("❌ 找不到该面板，请确认消息 ID 正确。", ephemeral=True)
            return

        # 权限检查
        if role >= ctx.guild.me.top_role:
            await ctx.send(
                "❌ 该身份组高于或等于我的最高身份组，无法分配。", ephemeral=True
            )
            return

        mappings = entry["mappings"]
        mappings[emoji] = role.id
        await self._save_mappings(msg_id, mappings)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT channel_id, title FROM rr_panels WHERE message_id = ?",
                (msg_id,),
            )
            row = await cursor.fetchone()

        if row:
            channel = ctx.guild.get_channel(row[0])
            if channel:
                try:
                    message = await channel.fetch_message(msg_id)
                    await self._rebuild_panel(message, row[1], mappings, ctx.guild)
                except discord.NotFound:
                    pass

        await ctx.send(f"✅ 已添加按钮: {emoji} {role.mention}", ephemeral=True)
        await audit(
            self.bot,
            ctx.guild.id,
            "添加身份组映射",
            **{
                "操作者": ctx.author.mention,
                "面板": str(msg_id),
                "Emoji": emoji,
                "身份组": role.mention,
            },
        )

    # ─── 指令：rr_remove ───

    @commands.hybrid_command(
        name="rr_remove", description="[管理] 从面板移除一个 emoji 映射"
    )
    @commands.guild_only()
    @require(manage_roles=True)
    async def rr_remove(self, ctx, message_id: str, emoji: str):
        await ctx.defer(ephemeral=True)
        msg_id = int(message_id)

        entry = await self._panel_for(ctx, msg_id)
        if entry is None:
            await ctx.send("❌ 找不到该面板。", ephemeral=True)
            return

        mappings = entry["mappings"]
        if emoji not in mappings:
            await ctx.send("❌ 该 emoji 不在面板映射中。", ephemeral=True)
            return

        del mappings[emoji]
        await self._save_mappings(msg_id, mappings)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT channel_id, title FROM rr_panels WHERE message_id = ?",
                (msg_id,),
            )
            row = await cursor.fetchone()
        if row:
            channel = ctx.guild.get_channel(row[0])
            if channel:
                try:
                    message = await channel.fetch_message(msg_id)
                    await self._rebuild_panel(message, row[1], mappings, ctx.guild)
                except (discord.NotFound, discord.Forbidden):
                    pass

        await ctx.send(f"✅ 已移除: {emoji}", ephemeral=True)
        await audit(
            self.bot,
            ctx.guild.id,
            "移除身份组映射",
            **{"操作者": ctx.author.mention, "面板": str(msg_id), "Emoji": emoji},
        )

    # ─── 指令：rr_list ───

    @commands.hybrid_command(
        name="rr_list", description="[管理] 列出所有反应身份组面板"
    )
    @commands.guild_only()
    @require(manage_roles=True)
    async def rr_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT message_id, channel_id, title, mappings, exclusive FROM rr_panels WHERE guild_id = ?",
                (ctx.guild.id,),
            )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("📭 当前服务器没有反应身份组面板。")
            return

        embed = discord.Embed(title="🏷 反应身份组面板列表", color=discord.Color.teal())
        for msg_id, ch_id, title, mappings_json, exclusive in rows:
            mappings = json.loads(mappings_json)
            channel = ctx.guild.get_channel(ch_id)
            ch_name = channel.mention if channel else f"#{ch_id}"
            count = len(mappings)
            mode = "🔘 单选" if exclusive else "☑️ 多选"
            embed.add_field(
                name=f"{title}",
                value=f"频道: {ch_name}\n消息 ID: `{msg_id}`\n映射数量: {count} | 模式: {mode}",
                inline=False,
            )

        await ctx.send(embed=embed)

    # ─── 指令:rr_exclusive ───

    @commands.hybrid_command(
        name="rr_exclusive", description="[管理] 切换面板的单选/多选模式"
    )
    @commands.guild_only()
    @require(manage_roles=True)
    async def rr_exclusive(self, ctx, message_id: str, enabled: bool):
        """
        message_id: 面板消息 ID
        enabled: True=单选模式(只能选一个),False=多选模式
        """
        await ctx.defer(ephemeral=True)
        msg_id = int(message_id)

        if await self._panel_for(ctx, msg_id) is None:
            await ctx.send("❌ 找不到该面板。", ephemeral=True)
            return

        await self._set_exclusive(msg_id, enabled)
        mode = "🔘 单选" if enabled else "☑️ 多选"
        await ctx.send(
            f"✅ 已切换为 {mode} 模式。\n*提示:Discord 端的面板提示文字不会自动更新,如需更新请重建面板。*",
            ephemeral=True,
        )

        await audit(
            self.bot,
            ctx.guild.id,
            "切换面板模式",
            **{"操作者": ctx.author.mention, "面板": str(msg_id), "新模式": mode},
        )

    # ─── 指令：rr_delete ───

    @commands.hybrid_command(
        name="rr_delete", description="[管理] 删除一个反应身份组面板"
    )
    @commands.guild_only()
    @require(manage_roles=True)
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
        await audit(
            self.bot,
            ctx.guild.id,
            "删除身份组面板",
            **{"操作者": ctx.author.mention, "消息 ID": str(msg_id)},
        )

    # ─── 反应监听 ───

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member and payload.member.bot:
            return

        entry = self._cache.get(payload.message_id)
        if not entry:
            return

        mappings = entry["mappings"]
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
            if entry.get("exclusive"):
                await self._exclusive_reaction(payload, guild, member, role, entry)
                return
            try:
                await member.add_roles(role, reason="反应身份组")
            except discord.Forbidden:
                pass

    async def _exclusive_reaction(self, payload, guild, member, role, entry):
        """单选面板的反应添加：换走同面板其他身份组，并尽力撤掉该用户的其他映射反应"""
        mappings = entry["mappings"]
        to_add, to_remove = roles.exclusive_changes(
            {r.id for r in member.roles}, set(mappings.values()), role.id
        )
        old_roles = [r for r in (guild.get_role(i) for i in to_remove) if r]
        try:
            if old_roles:
                await member.remove_roles(*old_roles, reason="反应身份组 - 单选互斥")
            if to_add:
                await member.add_roles(role, reason="反应身份组")
        except (discord.Forbidden, discord.HTTPException):
            pass

        # 撤掉其他表情上的反应（需要“管理消息”权限，失败忽略）。映射到同一身份组的表情不能撤，
        # 否则 on_raw_reaction_remove 会把刚领到的身份组又移除
        channel = guild.get_channel_or_thread(payload.channel_id)
        if channel is None:
            return
        message = channel.get_partial_message(payload.message_id)
        for other_emoji, other_role_id in mappings.items():
            if other_emoji == str(payload.emoji) or other_role_id == role.id:
                continue
            try:
                await message.remove_reaction(other_emoji, member)
            except discord.Forbidden:
                return  # 没有“管理消息”权限，后面的也不会成功
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        entry = self._cache.get(payload.message_id)
        if not entry:
            return

        mappings = entry["mappings"]

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

    # ─── 按钮监听(Web 端新面板使用)───

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("rr:"):
            return
        if not await check_component(self.bot, interaction):
            return
        if not interaction.guild:
            return

        try:
            role_id = int(custom_id.split(":", 1)[1])
        except (ValueError, IndexError):
            return

        role = interaction.guild.get_role(role_id)
        member = interaction.user
        if not role:
            await interaction.response.send_message(
                "❌ 该身份组已不存在,请联系管理员重建面板。", ephemeral=True
            )
            return
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ 该身份组高于我的最高身份组,我无法分配。", ephemeral=True
            )
            return

        # 单选模式检测:从缓存拿当前面板的 exclusive 状态(缓存未命中视为无条目)
        message_id = interaction.message.id if interaction.message else 0
        entry = self._cache.get(message_id)
        exclusive = entry.get("exclusive", False) if entry else False
        panel_role_ids = set(entry["mappings"].values()) if entry else set()

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="身份组按钮 - 取消")
                await interaction.response.send_message(
                    f"✅ 已移除身份组 {role.mention}", ephemeral=True
                )
            else:
                # 单选模式:移除该面板里其他已拥有的角色
                if exclusive:
                    _, remove_ids = roles.exclusive_changes(
                        {r.id for r in member.roles}, panel_role_ids, role.id
                    )
                    to_remove = [r for r in member.roles if r.id in remove_ids]
                    if to_remove:
                        try:
                            await member.remove_roles(
                                *to_remove, reason="身份组按钮 - 单选互斥"
                            )
                        except discord.Forbidden:
                            pass
                await member.add_roles(role, reason="身份组按钮 - 领取")
                if exclusive:
                    await interaction.response.send_message(
                        f"✅ 已切换到身份组 {role.mention}", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"✅ 已获得身份组 {role.mention}", ephemeral=True
                    )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 我没有权限分配此身份组。", ephemeral=True
            )
        except Exception as e:
            print(f"[RR button] {e}")
            try:
                await interaction.response.send_message(
                    "❌ 操作失败,请联系管理员。", ephemeral=True
                )
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
