# cogs/reactionroles.py
# RinBot — 反应身份组模块
# 功能：
#   • 面板在控制台的「领取身份组」里创建和编辑（原来的 rr_* 指令已移到控制台）
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
from _messages import embed
from rincore.embeds import build
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
        panel = build("info", title, description or "点击下方按钮领取对应身份组")
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
                        "embeds": [panel],
                        "components": components,
                    },
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        print(f"[RR rebuild] Discord {resp.status}: {body[:300]}")
        except Exception as e:
            print(f"[RR rebuild] {e}")

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
