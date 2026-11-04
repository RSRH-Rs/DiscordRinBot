# cogs/reactionroles.py
# RinBot — 反应身份组模块
# 功能：
#   • 新面板在控制台的「领取身份组」里发
#   • /roles list | add | remove | exclusive | delete — 编辑已经发出去的面板（控制台做不到），面板从列表里按标题选
#   • 自动监听 reaction_add / reaction_remove 分配/移除身份组

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import aiohttp
import json
import os
import re
from typing import Optional
from _botlog_helper import audit, check_component
from _perms import require
from _messages import Notice, embed, link_view, send, send_notice
from _inputs import choices, is_zh
from rincore.embeds import build
from rincore import legacy, roles

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reactionroles.db"
)

MAX_BUTTONS = 20  # 和控制台一致（Discord 一条消息最多放 25 个按钮）
DEFAULT_DESCRIPTION = "点击下方按钮领取对应身份组"
EXCLUSIVE_HINT = "*注:只能选一个身份组,选其他会自动替换*"  # 控制台发单选面板时加在说明末尾的同一句
_MESSAGE_LINK = re.compile(r"https://(?:\w+\.)?discord(?:app)?\.com/channels/\d+/\d+/(\d+)")
_CUSTOM_EMOJI = re.compile(r"<a?:(\w+):\d+>")
_ROLE_MENTION = re.compile(r"<@&(\d+)>")

# 重画面板失败时的提示；失败时什么都不存
_REFRESH_NOTICES = {
    "bad_emoji": Notice("error", "这个 emoji 用不了", "填一个 Discord 自带的 emoji，比如 🎮，或者这个服务器的自定义 emoji。"),
    "gone": Notice("error", "面板消息已经不在了", "用 /roles delete 清掉这个面板，再到控制台重新发一个。"),
    "failed": Notice("error", "面板没更新成功", "稍后再试一次。"),
}


def panel_description(current: Optional[str], exclusive: bool) -> str:
    """面板说明：保留原来写的内容，按单选与否加上或去掉末尾的单选提示。"""
    text = (current or "").strip()
    if text.endswith(EXCLUSIVE_HINT):
        text = text[: -len(EXCLUSIVE_HINT)].rstrip()
    text = text or DEFAULT_DESCRIPTION
    return f"{text}\n\n{EXCLUSIVE_HINT}" if exclusive else text


def _emoji_label(emoji: str) -> str:
    """候选列表只显示纯文字：自定义 emoji 显示成 :名字:。"""
    match = _CUSTOM_EMOJI.fullmatch(emoji)
    return f":{match.group(1)}:" if match else emoji


def _match_button(mappings: dict, text: str, guild) -> Optional[str]:
    """/roles remove 的参数（表情、身份组提及、ID 或名字）→ 面板里对应的表情；找不到返回 None。"""
    text = text.strip()
    if text in mappings:
        return text
    mention = _ROLE_MENTION.fullmatch(text)
    role_id = int(mention.group(1)) if mention else int(text) if text.isdigit() else None
    for emoji, mapped in mappings.items():
        if mapped == role_id:
            return emoji
    for emoji, mapped in mappings.items():
        role = guild.get_role(mapped)
        if role is not None and role.name.casefold() == text.casefold():
            return emoji
    return None


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

    async def _panels(self, guild_id: int) -> list[dict]:
        """本服务器的面板，按发出的先后排；直接读数据库（控制台刚发的面板也在）。"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT message_id, channel_id, title, mappings, exclusive FROM rr_panels "
                "WHERE guild_id = ? ORDER BY message_id",
                (guild_id,),
            )
            rows = await cursor.fetchall()
        panels = []
        for message_id, channel_id, title, mappings_json, exclusive in rows:
            entry = self._build_entry(guild_id, mappings_json, exclusive)
            panels.append({
                "message_id": message_id, "channel_id": channel_id, "title": title or "身份组选择",
                "mappings": entry["mappings"], "exclusive": entry["exclusive"],
            })
        return panels

    async def _find_panel(self, guild_id: int, text: str):
        """按消息 ID、消息链接或标题（不分大小写）找本服务器的面板；返回 (面板, None) 或 (None, 提示)。"""
        text = (text or "").strip()
        link = _MESSAGE_LINK.fullmatch(text)
        key = link.group(1) if link else text
        panels = await self._panels(guild_id)
        found = [p for p in panels if key.isdigit() and p["message_id"] == int(key)]
        if not found and not link and text:
            found = [p for p in panels if p["title"].casefold() == text.casefold()]
        if len(found) == 1:
            return found[0], None
        if found:
            return None, Notice("error", f"有 {len(found)} 个面板都叫「{text}」", "从列表里选，或者填面板的消息 ID。")
        return None, Notice("error", "找不到这个面板", "从列表里选一个面板，或者用 /roles list 查看。")

    async def _store(self, guild_id: int, message_id: int, mappings: dict, exclusive: bool):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE rr_panels SET mappings = ?, exclusive = ? WHERE message_id = ? AND guild_id = ?",
                (json.dumps(mappings, ensure_ascii=False), int(exclusive), message_id, guild_id),
            )
            await db.commit()
        await self.reload_guild(guild_id)

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
        """重建面板:embed + 按钮(用 raw aiohttp 绕过 discord.py http 限制)；返回 Discord 的状态码，没发出去时返回 0"""
        panel = build("info", title, description or DEFAULT_DESCRIPTION)
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
                    return resp.status
        except Exception as e:
            print(f"[RR rebuild] {e}")
            return 0

    async def _refresh_panel(self, guild, panel: dict, mappings: dict, exclusive: bool) -> str:
        """按新的身份组和模式重画面板消息，保留原来的说明文字；返回 ok、bad_emoji、gone 或 failed。"""
        channel = guild.get_channel_or_thread(panel["channel_id"])
        if channel is None:
            return "gone"
        try:
            message = await channel.fetch_message(panel["message_id"])
        except discord.NotFound:
            return "gone"
        except discord.HTTPException:
            return "failed"
        current = message.embeds[0].description if message.embeds else None
        status = await self._rebuild_panel(
            message, panel["title"], mappings, guild, panel_description(current, exclusive)
        )
        if 200 <= status < 300:
            return "ok"
        return {400: "bad_emoji", 404: "gone"}.get(status, "failed")

    async def _apply(self, ctx, panel: dict, mappings: dict, exclusive: bool) -> bool:
        """先改 Discord 上的面板消息，成功了再存；改不了就说明原因，什么都不存。"""
        result = await self._refresh_panel(ctx.guild, panel, mappings, exclusive)
        if result != "ok":
            await send_notice(ctx, _REFRESH_NOTICES[result])
            return False
        await self._store(ctx.guild.id, panel["message_id"], mappings, exclusive)
        return True

    # ─── 指令：/roles（新面板在控制台的「领取身份组」里发）───

    @commands.hybrid_group(name="roles", description="Edit role panels that are already posted")
    @commands.guild_only()
    @require(manage_roles=True)
    async def roles_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._list(ctx)

    @roles_group.command(name="list", description="List this server's role panels")
    @commands.guild_only()
    @require(manage_roles=True)
    async def roles_list(self, ctx):
        await self._list(ctx)

    async def _list(self, ctx):
        panels = await self._panels(ctx.guild.id)
        if not panels:
            await send(
                ctx,
                embed("info", "还没有身份组面板", "在控制台的「领取身份组」里发一个。"),
                view=link_view("打开控制台", legacy.dashboard_url(ctx.guild.id, "roles")),
            )
            return
        fields = []
        for panel in panels[:25]:
            channel = ctx.guild.get_channel(panel["channel_id"])
            mode = "单选" if panel["exclusive"] else "多选"
            value = f"{channel.mention if channel else '频道已删除'}，{len(panel['mappings'])} 个身份组，{mode}"
            if channel:
                value += f"\n[跳到面板](https://discord.com/channels/{ctx.guild.id}/{panel['channel_id']}/{panel['message_id']})"
            fields.append((panel["title"], value, False))
        more = len(panels) - len(fields)
        await send(ctx, embed("info", "身份组面板", fields=fields, footer=f"还有 {more} 个面板没列出来" if more else None))

    @roles_group.command(name="add", description="Add a role button to a panel")
    @app_commands.describe(
        panel="The panel to change; pick from the list",
        emoji="The emoji on the button, such as 🎮",
        role="The role members get from the button",
    )
    @commands.guild_only()
    @require(manage_roles=True)
    async def roles_add(self, ctx, panel: str, emoji: str, role: discord.Role):
        await ctx.defer(ephemeral=True)
        found, notice = await self._find_panel(ctx.guild.id, panel)
        if notice:
            await send_notice(ctx, notice)
            return
        if role.is_default() or role.managed:
            await send_notice(ctx, Notice("error", f"「{role.name}」不能用来领取", "机器人和集成自带的身份组、@everyone 都不能放进面板。"))
            return
        if role >= ctx.guild.me.top_role:
            await send_notice(ctx, Notice("error", f"我分配不了「{role.name}」", f"把小凛的身份组拖到「{role.name}」上面，再试一次。"))
            return
        emoji = emoji.strip()
        # 同一个身份组只放一个按钮：已经在面板上就换成新的 emoji
        mappings = {e: r for e, r in found["mappings"].items() if r != role.id}
        mappings[emoji] = role.id
        if len(mappings) > MAX_BUTTONS:
            await send_notice(ctx, Notice(
                "error", f"这个面板已经有 {MAX_BUTTONS} 个身份组了", f"一个面板最多 {MAX_BUTTONS} 个身份组，先去掉一个再加。"
            ))
            return
        if not await self._apply(ctx, found, mappings, found["exclusive"]):
            return
        await send(ctx, embed(
            "success", "面板已更新", f"{emoji} {role.mention} 已加到「{found['title']}」，现在有 {len(mappings)} 个身份组。"
        ), private=True)
        await audit(
            self.bot,
            ctx.guild.id,
            "添加身份组映射",
            **{"操作者": ctx.author.mention, "面板": found["title"], "Emoji": emoji, "身份组": role.mention},
        )

    @roles_group.command(name="remove", description="Take a role button off a panel")
    @app_commands.describe(panel="The panel to change; pick from the list", role="The role to take off; pick from the list")
    @commands.guild_only()
    @require(manage_roles=True)
    async def roles_remove(self, ctx, panel: str, *, role: str):
        await ctx.defer(ephemeral=True)
        found, notice = await self._find_panel(ctx.guild.id, panel)
        if notice:
            await send_notice(ctx, notice)
            return
        emoji = _match_button(found["mappings"], role, ctx.guild)
        if emoji is None:
            await send_notice(ctx, Notice("error", "面板上没有这个身份组", "从列表里选一个要去掉的身份组。"))
            return
        if len(found["mappings"]) == 1:
            await send_notice(ctx, Notice("error", "面板至少要留一个身份组", "要整个删掉，用 /roles delete。"))
            return
        removed = ctx.guild.get_role(found["mappings"][emoji])
        mappings = {e: r for e, r in found["mappings"].items() if e != emoji}
        if not await self._apply(ctx, found, mappings, found["exclusive"]):
            return
        role_text = removed.mention if removed else "已删除的身份组"
        await send(ctx, embed(
            "success", "面板已更新", f"已从「{found['title']}」去掉 {emoji} {role_text}，还剩 {len(mappings)} 个身份组。"
        ), private=True)
        await audit(
            self.bot,
            ctx.guild.id,
            "移除身份组映射",
            **{"操作者": ctx.author.mention, "面板": found["title"], "Emoji": emoji},
        )

    @roles_group.command(name="exclusive", description="Let members pick one role or several on a panel")
    @app_commands.describe(panel="The panel to change; pick from the list", enabled="True lets members keep only one role")
    @commands.guild_only()
    @require(manage_roles=True)
    async def roles_exclusive(self, ctx, panel: str, enabled: bool):
        await ctx.defer(ephemeral=True)
        found, notice = await self._find_panel(ctx.guild.id, panel)
        if notice:
            await send_notice(ctx, notice)
            return
        title, mode = found["title"], "单选" if enabled else "多选"
        if found["exclusive"] == enabled:
            await send(ctx, embed("info", f"「{title}」本来就是{mode}"), private=True)
            return
        if not await self._apply(ctx, found, found["mappings"], enabled):
            return
        detail = "成员只能领一个身份组，换选时自动替换。" if enabled else "成员可以同时领多个身份组。"
        await send(ctx, embed("success", f"「{title}」改成了{mode}", detail), private=True)
        await audit(
            self.bot,
            ctx.guild.id,
            "切换面板模式",
            **{"操作者": ctx.author.mention, "面板": title, "新模式": mode},
        )

    @roles_group.command(name="delete", description="Delete a role panel and its message")
    @app_commands.describe(panel="The panel to delete; pick from the list")
    @commands.guild_only()
    @require(manage_roles=True)
    async def roles_delete(self, ctx, panel: str):
        await ctx.defer(ephemeral=True)
        found, notice = await self._find_panel(ctx.guild.id, panel)
        if notice:
            await send_notice(ctx, notice)
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM rr_panels WHERE message_id = ? AND guild_id = ?", (found["message_id"], ctx.guild.id)
            )
            await db.commit()
        self._cache.pop(found["message_id"], None)

        note = None
        channel = ctx.guild.get_channel_or_thread(found["channel_id"])
        if channel is not None:
            try:
                await channel.get_partial_message(found["message_id"]).delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                note = "我没有权限删掉面板消息，请手动删除。"
            except discord.HTTPException:
                note = "面板消息没删掉，请手动删除。"
        await send(ctx, embed("success", f"已删除面板「{found['title']}」", note), private=True)
        await audit(
            self.bot,
            ctx.guild.id,
            "删除身份组面板",
            **{"操作者": ctx.author.mention, "面板": found["title"], "消息 ID": str(found["message_id"])},
        )

    @roles_add.autocomplete("panel")
    async def _panel_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            panels = await self._panels(interaction.guild.id)
        except Exception:
            return []
        zh, items = is_zh(interaction), []
        for panel in panels:
            channel = interaction.guild.get_channel(panel["channel_id"])
            count = len(panel["mappings"])
            if zh:
                where = f"#{channel.name}" if channel else "频道已删除"
                items.append((f"{panel['title']}（{where}，{count} 个身份组）", str(panel["message_id"])))
            else:
                where = f"#{channel.name}" if channel else "deleted channel"
                items.append((f"{panel['title']} ({where}, {count} role{'' if count == 1 else 's'})", str(panel["message_id"])))
        return choices(items, current)

    roles_remove.autocomplete("panel")(_panel_autocomplete)
    roles_exclusive.autocomplete("panel")(_panel_autocomplete)
    roles_delete.autocomplete("panel")(_panel_autocomplete)

    @roles_remove.autocomplete("role")
    async def _button_autocomplete(self, interaction: discord.Interaction, current: str):
        """列出选中面板上的身份组；面板还没选或选得不唯一时不给候选。"""
        panel_text = getattr(getattr(interaction, "namespace", None), "panel", None)
        if interaction.guild is None or not panel_text:
            return []
        try:
            panel, _ = await self._find_panel(interaction.guild.id, str(panel_text))
        except Exception:
            return []
        if panel is None:
            return []
        zh, items = is_zh(interaction), []
        for emoji, role_id in panel["mappings"].items():
            role = interaction.guild.get_role(role_id)
            name = role.name if role else ("身份组已删除" if zh else "deleted role")
            items.append((f"{_emoji_label(emoji)} {name}", emoji))
        return choices(items, current)

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
