import discord
from discord.ext import commands
import aiosqlite
import json
import os
import time
from collections import defaultdict
from typing import Literal

from discord.ext import tasks

from _botlog_helper import audit
from _perms import require
from _messages import embed, send_moved
from _inputs import choices
from discord import app_commands
from rincore.embeds import event_kind
from rincore.textmatch import find_badword, find_links, host_of, is_whitelisted

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "automod.db"
)

# 调试开关：排查「自动审核没反应」时设 True，控制台会打印检测过程与失败原因；查完改回 False
AUTOMOD_DEBUG = False


class AutoMod(commands.Cog):
    """自动审核 — 社区风纪委员小凛"""

    def __init__(self, bot):
        self.bot = bot
        # 刷屏检测缓存: {guild_id: {user_id: [(timestamp, channel_id, message_id), ...]}}
        self._msg_cache: dict[int, dict[int, list[tuple[float, int, int]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # 重复消息缓存: {guild_id: {user_id: [(content, timestamp), ...]}}
        self._repeat_cache: dict[int, dict[int, list[tuple]]] = defaultdict(
            lambda: defaultdict(list)
        )
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

        await self._load_all_config()
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("automod", self.reload_guild)
        if not self._prune_caches.is_running():
            self._prune_caches.start()
        print("✅ 自动审核系统已准备就绪！")

    def cog_unload(self):
        self._prune_caches.cancel()
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("automod", self.reload_guild)

    async def _load_all_config(self):
        cache = {}
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM automod_config")
            for row in await cursor.fetchall():
                d = dict(row)
                cache[d["guild_id"]] = d
        self._config_cache = cache
        if AUTOMOD_DEBUG:
            print(f"[automod] DB 路径: {os.path.abspath(DB_PATH)}")
            print(f"[automod] 配置已加载/刷新，共 {len(cache)} 个服务器")
            for gid, c in cache.items():
                print(
                    f"  guild={gid} enabled={c.get('enabled')} "
                    f"log_channel={c.get('log_channel')} "
                    f"anti_spam={c.get('anti_spam')} anti_repeat={c.get('anti_repeat')}"
                )

    @staticmethod
    def _prune_cache(cache: dict, ts_index: int, cutoff: float):
        """删除最近一条记录早于 cutoff 的用户条目，以及清空后的服务器条目。"""
        for guild_id in list(cache):
            users = cache[guild_id]
            for user_id in list(users):
                entries = users[user_id]
                if not entries or entries[-1][ts_index] < cutoff:
                    del users[user_id]
            if not users:
                del cache[guild_id]

    @tasks.loop(minutes=10)
    async def _prune_caches(self):
        cutoff = time.time() - 60
        self._prune_cache(self._msg_cache, 0, cutoff)
        self._prune_cache(self._repeat_cache, 1, cutoff)

    async def _delete_spam_messages(self, guild: discord.Guild, entries, current_channel):
        """按频道批量删除刷屏窗口内的消息；批量失败则逐条尽力删除。"""
        by_channel = defaultdict(list)
        for _, channel_id, message_id in entries:
            by_channel[channel_id].append(message_id)
        for channel_id, message_ids in by_channel.items():
            if current_channel.id == channel_id:
                channel = current_channel
            else:
                channel = guild.get_channel_or_thread(channel_id)
            if channel is None:
                continue
            # delete_messages 单次最多 100 条；不足 2 条的批次走逐条删除
            for start in range(0, len(message_ids), 100):
                batch = message_ids[start : start + 100]
                if len(batch) >= 2:
                    try:
                        await channel.delete_messages(
                            [discord.Object(id=mid) for mid in batch]
                        )
                        continue
                    except discord.HTTPException:
                        pass  # 含 Forbidden；回退为逐条删除
                    except Exception as e:
                        print(f"[automod] 刷屏批量删除异常：{e!r}")
                        continue
                for mid in batch:
                    try:
                        await channel.get_partial_message(mid).delete()
                    except discord.Forbidden:
                        break
                    except discord.HTTPException:
                        pass
                    except Exception as e:
                        print(f"[automod] 刷屏逐条删除异常：{e!r}")
                        break

    # 网页仪表盘保存后由变更日志回调：只重读该服务器的一行配置
    async def reload_guild(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)
            )
            row = await cursor.fetchone()
        if row:
            self._config_cache[guild_id] = dict(row)
        else:
            self._config_cache.pop(guild_id, None)

    async def _get_config(self, guild_id: int) -> dict:
        if guild_id in self._config_cache:
            return self._config_cache[guild_id]
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)
            )
            row = await cursor.fetchone()
            if row:
                cfg = dict(row)
                self._config_cache[guild_id] = cfg
                return cfg
        return None

    async def _update_config(self, guild_id: int, **kwargs):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)",
                (guild_id,),
            )
            for key, val in kwargs.items():
                await db.execute(
                    f"UPDATE automod_config SET {key} = ? WHERE guild_id = ?",
                    (val, guild_id),
                )
            await db.commit()
        # 刷新缓存
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)
            )
            row = await cursor.fetchone()
            if row:
                self._config_cache[guild_id] = dict(row)

    async def _log_action(self, guild: discord.Guild, e: discord.Embed):
        cfg = await self._get_config(guild.id)
        if not cfg or not cfg.get("log_channel"):
            if AUTOMOD_DEBUG:
                print(f"[automod] _log_action: guild={guild.id} 未设置 log_channel")
            return
        channel = guild.get_channel(cfg["log_channel"])
        if not channel:
            print(
                f"[automod] 日志发送失败：找不到频道 {cfg['log_channel']}（bot 看不到该频道，或频道已删）"
            )
            return
        try:
            await channel.send(embed=e)
        except discord.Forbidden:
            print(f"[automod] 日志发送失败：bot 在频道 {channel.id} 无发送权限")

    async def _mute_user(self, member: discord.Member, reason: str, duration: int):
        """使用 Discord 原生 timeout 功能"""
        try:
            import datetime

            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
            await member.timeout(until, reason=reason)
        except discord.Forbidden:
            print(
                "[automod] 禁言失败：bot 缺少『超时成员(Moderate Members)』权限，或 bot 身份组层级低于该成员"
            )

    def _is_ignored(self, cfg: dict, channel_id: int, member: discord.Member) -> bool:
        """检查频道或身份组是否在忽略列表中"""
        try:
            ignored_channels = json.loads(cfg.get("ignored_channels", "[]"))
            ignored_roles = json.loads(cfg.get("ignored_roles", "[]"))
        except json.JSONDecodeError:
            return False

        try:
            ignored_channels = {int(value) for value in ignored_channels}
            ignored_roles = {int(value) for value in ignored_roles}
        except (TypeError, ValueError):
            return False

        if channel_id in ignored_channels:
            return True
        member_role_ids = {r.id for r in member.roles}
        if member_role_ids & ignored_roles:
            return True
        return False

    # ─── 消息监听 ───

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if message.author.guild_permissions.manage_messages:
            if AUTOMOD_DEBUG:
                print(f"[automod] 跳过：{message.author} 有『管理消息』权限，被豁免")
            return  # 不审核管理员

        cfg = await self._get_config(message.guild.id)
        if not cfg or not cfg.get("enabled"):
            if AUTOMOD_DEBUG:
                print(
                    f"[automod] 跳过：guild={message.guild.id} 未启用 (cfg={'无' if not cfg else cfg.get('enabled')})"
                )
            return

        if self._is_ignored(cfg, message.channel.id, message.author):
            if AUTOMOD_DEBUG:
                print(
                    f"[automod] 跳过：频道/身份组在忽略列表 (channel={message.channel.id})"
                )
            return

        guild_id = message.guild.id
        user_id = message.author.id
        now = time.time()

        # ── 1. 反刷屏 ──
        if cfg.get("anti_spam"):
            threshold = cfg.get("spam_threshold", 5)
            interval = cfg.get("spam_interval", 5)

            self._msg_cache[guild_id][user_id].append(
                (now, message.channel.id, message.id)
            )
            # 清理过期记录
            self._msg_cache[guild_id][user_id] = [
                e for e in self._msg_cache[guild_id][user_id] if now - e[0] < interval
            ]

            if len(self._msg_cache[guild_id][user_id]) >= threshold:
                spam_entries = self._msg_cache[guild_id][user_id]
                self._msg_cache[guild_id][user_id] = []
                try:
                    await self._delete_spam_messages(
                        message.guild, spam_entries, message.channel
                    )
                except Exception as e:
                    # 清理失败也不能跳过后面的禁言与日志
                    print(f"[automod] 刷屏消息清理失败：{e!r}")
                mute_dur = cfg.get("mute_duration", 300)
                await self._mute_user(message.author, "刷屏", mute_dur)
                try:
                    await message.channel.send(
                        f"🔇 {message.author.mention} 因刷屏被小凛禁言 {mute_dur // 60} 分钟。",
                        delete_after=10,
                    )
                except discord.Forbidden:
                    print("[automod] 刷屏提示发送失败：bot 在该频道无发送权限")
                e = embed(
                    event_kind("automod"),
                    "自动审核：刷屏",
                    fields=[
                        ("成员", message.author.mention),
                        ("频道", message.channel.mention),
                        ("处理", f"禁言 {mute_dur // 60} 分钟"),
                    ],
                    timestamp=discord.utils.utcnow(),
                )
                await self._log_action(message.guild, e)
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

            if AUTOMOD_DEBUG:
                print(
                    f"[automod] 重复检查 guild={guild_id} user={user_id} "
                    f"content={content!r} 相同计数={same_count}/{repeat_threshold}"
                )

            if same_count >= repeat_threshold and content:
                cache.clear()
                try:
                    await message.delete()
                    await message.channel.send(
                        f"⚠️ {message.author.mention} 请不要发送重复消息。",
                        delete_after=8,
                    )
                except discord.Forbidden:
                    print(
                        "[automod] 重复消息处理失败：bot 缺少『管理消息』权限（无法删除消息）"
                    )
                e = embed(
                    event_kind("automod"),
                    "自动审核：重复消息",
                    fields=[
                        ("成员", message.author.mention),
                        ("频道", message.channel.mention),
                        ("内容", content[:100], False),
                    ],
                    timestamp=discord.utils.utcnow(),
                )
                await self._log_action(message.guild, e)
                return

        # ── 3. 违禁词过滤 ──
        if cfg.get("anti_badword"):
            try:
                badwords = json.loads(cfg.get("badwords", "[]"))
            except json.JSONDecodeError:
                badwords = []

            word = find_badword(message.content, badwords)
            if word is not None:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"⚠️ {message.author.mention} 你的消息包含违禁内容，已被小凛删除。",
                        delete_after=8,
                    )
                except discord.Forbidden:
                    pass
                e = embed(
                    event_kind("automod"),
                    "自动审核：违禁词",
                    fields=[
                        ("成员", message.author.mention),
                        ("频道", message.channel.mention),
                        ("触发词", f"||{word}||"),
                    ],
                    timestamp=discord.utils.utcnow(),
                )
                await self._log_action(message.guild, e)
                return

        # ── 4. 链接过滤 ──
        if cfg.get("anti_link"):
            urls = find_links(message.content)

            if urls:
                try:
                    whitelist = json.loads(cfg.get("link_whitelist", "[]"))
                except json.JSONDecodeError:
                    whitelist = []

                for url in urls:
                    if not is_whitelisted(host_of(url), whitelist):
                        try:
                            await message.delete()
                            await message.channel.send(
                                f"🔗 {message.author.mention} 不允许在此发送链接。",
                                delete_after=8,
                            )
                        except discord.Forbidden:
                            pass
                        e = embed(
                            event_kind("automod"),
                            "自动审核：链接",
                            fields=[
                                ("成员", message.author.mention),
                                ("频道", message.channel.mention),
                                ("链接", url[:100], False),
                            ],
                            timestamp=discord.utils.utcnow(),
                        )
                        await self._log_action(message.guild, e)
                        return

        # ── 5. 大写字母轰炸 ──
        if cfg.get("anti_caps"):
            min_len = cfg.get("caps_min_length", 10)
            threshold = cfg.get("caps_threshold", 70)
            text = message.content
            alpha_chars = [c for c in text if c.isalpha()]
            if len(alpha_chars) >= min_len:
                upper_ratio = (
                    sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) * 100
                )
                if upper_ratio >= threshold:
                    try:
                        await message.delete()
                        await message.channel.send(
                            f"📢 {message.author.mention} 请不要使用过多大写字母。",
                            delete_after=8,
                        )
                    except discord.Forbidden:
                        pass
                    e = embed(
                        event_kind("automod"),
                        "自动审核：大写",
                        fields=[
                            ("成员", message.author.mention),
                            ("频道", message.channel.mention),
                            ("内容", text[:100], False),
                        ],
                        timestamp=discord.utils.utcnow(),
                    )
                    await self._log_action(message.guild, e)
                    return

    # ─── 配置指令（开关和参数在控制台的「自动审核」里改）───

    async def _show_status(self, ctx):
        cfg = await self._get_config(ctx.guild.id)
        if not cfg:
            await ctx.send("⚠️ 自动审核尚未启用。在控制台的「自动审核」里开启。")
            return

        status_emoji = lambda v: "🟢" if v else "🔴"
        log_ch = ctx.guild.get_channel(cfg.get("log_channel", 0))
        e = embed(
            "info",
            "自动审核设置",
            fields=[
                ("总开关", status_emoji(cfg["enabled"])),
                ("反刷屏", f"{status_emoji(cfg['anti_spam'])} ({cfg['spam_threshold']}条/{cfg['spam_interval']}秒)"),
                ("违禁词", f"{status_emoji(cfg['anti_badword'])} ({len(json.loads(cfg.get('badwords','[]')))}个词)"),
                ("链接过滤", status_emoji(cfg["anti_link"])),
                ("大写过滤", f"{status_emoji(cfg['anti_caps'])} (>{cfg['caps_threshold']}%)"),
                ("重复消息", f"{status_emoji(cfg['anti_repeat'])} ({cfg['repeat_threshold']}次触发)"),
                ("日志频道", log_ch.mention if log_ch else "未设置"),
                ("禁言时长", f"{cfg.get('mute_duration', 300) // 60} 分钟"),
            ],
            footer="开关和参数在控制台的「自动审核」里修改",
        )
        await ctx.send(embed=e)

    @commands.hybrid_group(name="automod", description="Automatic moderation: status and lists")
    @commands.guild_only()
    @require(manage_guild=True)
    async def automod_group(self, ctx):
        if ctx.invoked_subcommand is None:
            # 旧的 r!automod enable 之类：开关和参数已经移到控制台
            if ctx.subcommand_passed and await send_moved(ctx, f"automod {ctx.subcommand_passed}"):
                return
            await self._show_status(ctx)

    @automod_group.command(name="status", description="Show the automatic moderation settings")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_status(self, ctx):
        await self._show_status(ctx)

    # ─── 违禁词管理 ───

    async def _words(
        self, ctx, action: Literal["add", "remove", "list"], *, word: str = ""
    ):
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
                await ctx.send(
                    f"📝 违禁词列表 ({len(words)} 个): {display}", ephemeral=True
                )
            else:
                await ctx.send("📝 违禁词列表为空。", ephemeral=True)
            return

        if not word:
            await ctx.send("❌ 请提供一个词语。")
            return

        if action == "add":
            if word.lower() not in [w.lower() for w in words]:
                words.append(word)
                await self._update_config(
                    ctx.guild.id, badwords=json.dumps(words, ensure_ascii=False)
                )
                await audit(
                    self.bot,
                    ctx.guild.id,
                    "添加违禁词",
                    **{"操作者": ctx.author.mention, "词": f"||{word}||"},
                )
                await ctx.send(f"✅ 已添加违禁词: ||{word}||", ephemeral=True)
            else:
                await ctx.send("⚠️ 该词已在列表中。", ephemeral=True)

        elif action == "remove":
            words_lower = [w.lower() for w in words]
            if word.lower() in words_lower:
                idx = words_lower.index(word.lower())
                words.pop(idx)
                await self._update_config(
                    ctx.guild.id, badwords=json.dumps(words, ensure_ascii=False)
                )
                await audit(
                    self.bot,
                    ctx.guild.id,
                    "移除违禁词",
                    **{"操作者": ctx.author.mention, "词": f"||{word}||"},
                )
                await ctx.send(f"✅ 已移除违禁词: ||{word}||", ephemeral=True)
            else:
                await ctx.send("⚠️ 该词不在列表中。", ephemeral=True)

    # ─── 链接白名单管理 ───

    async def _whitelist(
        self, ctx, action: Literal["add", "remove", "list"], domain: str = ""
    ):
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
                await ctx.send(
                    "📝 链接白名单为空（所有链接都会被过滤）。", ephemeral=True
                )
            return

        if not domain:
            await ctx.send("❌ 请提供域名（如 youtube.com）。")
            return

        if action == "add":
            if domain.lower() not in whitelist:
                whitelist.append(domain.lower())
                await self._update_config(
                    ctx.guild.id, link_whitelist=json.dumps(whitelist)
                )
                await audit(
                    self.bot,
                    ctx.guild.id,
                    "添加链接白名单",
                    **{"操作者": ctx.author.mention, "域名": domain},
                )
                await ctx.send(f"✅ 已添加白名单域名: `{domain}`", ephemeral=True)
            else:
                await ctx.send("⚠️ 该域名已在白名单中。", ephemeral=True)

        elif action == "remove":
            if domain.lower() in whitelist:
                whitelist.remove(domain.lower())
                await self._update_config(
                    ctx.guild.id, link_whitelist=json.dumps(whitelist)
                )
                await audit(
                    self.bot,
                    ctx.guild.id,
                    "移除链接白名单",
                    **{"操作者": ctx.author.mention, "域名": domain},
                )
                await ctx.send(f"✅ 已移除白名单域名: `{domain}`", ephemeral=True)
            else:
                await ctx.send("⚠️ 该域名不在白名单中。", ephemeral=True)

    # ─── 忽略频道/身份组 ───

    async def _ignore(
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
            e = embed("info", "自动审核忽略列表", fields=[("频道", ch_text, False), ("身份组", role_text, False)])
            await ctx.send(embed=e, ephemeral=True)
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

        if channel or role:
            target = channel.mention if channel else role.mention
            verb = "添加" if action == "add" else "移除"
            await audit(
                self.bot,
                ctx.guild.id,
                f"{verb}审核忽略对象",
                **{"操作者": ctx.author.mention, "对象": target},
            )

    # ─── 违禁词 / 链接白名单 / 忽略列表：/automod words|whitelist|ignore add|remove|list ───

    @automod_group.group(name="words", description="Manage the banned word list")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_words(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._words(ctx, "list")

    @am_words.command(name="add", description="Add a banned word")
    @app_commands.describe(word="The word to ban")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_words_add(self, ctx, *, word: str):
        await self._words(ctx, "add", word=word)

    @am_words.command(name="remove", description="Remove a banned word")
    @app_commands.describe(word="The word to remove; pick from the list")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_words_remove(self, ctx, *, word: str):
        await self._words(ctx, "remove", word=word)

    @am_words.command(name="list", description="Show the banned words")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_words_list(self, ctx):
        await self._words(ctx, "list")

    @automod_group.group(name="whitelist", description="Manage the domains links may point to")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_whitelist(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._whitelist(ctx, "list")

    @am_whitelist.command(name="add", description="Allow links to a domain")
    @app_commands.describe(domain="A domain such as youtube.com")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_whitelist_add(self, ctx, domain: str):
        await self._whitelist(ctx, "add", domain)

    @am_whitelist.command(name="remove", description="Stop allowing links to a domain")
    @app_commands.describe(domain="The domain to remove; pick from the list")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_whitelist_remove(self, ctx, domain: str):
        await self._whitelist(ctx, "remove", domain)

    @am_whitelist.command(name="list", description="Show the allowed domains")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_whitelist_list(self, ctx):
        await self._whitelist(ctx, "list")

    @automod_group.group(name="ignore", description="Manage channels and roles automatic moderation skips")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_ignore(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._ignore(ctx, "list")

    @am_ignore.command(name="add", description="Skip a channel or role")
    @app_commands.describe(channel="A channel to skip", role="A role to skip")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_ignore_add(self, ctx, channel: discord.TextChannel = None, role: discord.Role = None):
        await self._ignore(ctx, "add", channel, role)

    @am_ignore.command(name="remove", description="Stop skipping a channel or role")
    @app_commands.describe(channel="The channel to stop skipping", role="The role to stop skipping")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_ignore_remove(self, ctx, channel: discord.TextChannel = None, role: discord.Role = None):
        await self._ignore(ctx, "remove", channel, role)

    @am_ignore.command(name="list", description="Show the skipped channels and roles")
    @commands.guild_only()
    @require(manage_guild=True)
    async def am_ignore_list(self, ctx):
        await self._ignore(ctx, "list")

    async def _config_list(self, guild, key: str) -> list[str]:
        cfg = await self._get_config(guild.id) or {}
        try:
            return list(json.loads(cfg.get(key, "[]")))
        except (TypeError, json.JSONDecodeError):
            return []

    @am_words_remove.autocomplete("word")
    async def _word_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            words = await self._config_list(interaction.guild, "badwords")
        except Exception:
            return []
        return choices([(w, w) for w in words], current)

    @am_whitelist_remove.autocomplete("domain")
    async def _domain_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            domains = await self._config_list(interaction.guild, "link_whitelist")
        except Exception:
            return []
        return choices([(d, d) for d in domains], current)


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
