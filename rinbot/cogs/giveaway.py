# cogs/giveaway.py
# RinBot — 抽奖管理模块
# 功能：
#   • /giveaway start — 发起抽奖活动（设置奖品、时长、中奖人数）
#   • /giveaway end   — 提前结束抽奖
#   • /giveaway reroll — 重新抽取获奖者
#   • /giveaway list  — 查看活跃的抽奖活动
#   • 自动倒计时 + 自动开奖

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
import aiosqlite
import secrets
import time
import asyncio
import os
from typing import Optional
from _botlog_helper import audit, check_component
from _perms import require
from _messages import embed
from _inputs import Duration, choices, duration_autocomplete, is_zh
from rincore import durations
from rincore.embeds import giveaway_ended, giveaway_running
from rincore import durations
from rincore.throttle import Debouncer

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "giveaway.db"
)
GIVEAWAY_EMOJI = "🎉"
# 参与人数标签的刷新窗口(秒)：每个抽奖最多每 5 秒编辑一次原消息
LABEL_REFRESH_SECONDS = 5.0


class GiveawayEntryButton(View):
    """抽奖参与按钮"""

    def __init__(self):
        super().__init__(timeout=None)  # 持久化

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_component(interaction.client, interaction)

    @discord.ui.button(
        label="🎉 参加抽奖!",
        style=discord.ButtonStyle.success,
        custom_id="giveaway_enter",
    )
    async def enter(self, interaction: discord.Interaction, button: Button):
        # 查找这个消息对应的抽奖
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, ended, restrict_role FROM giveaways WHERE message_id = ?",
                (interaction.message.id,),
            )
            row = await cursor.fetchone()
            if not row:
                await interaction.response.send_message(
                    "❌ 找不到该抽奖活动。", ephemeral=True
                )
                return
            giveaway_id, ended, restrict_role = row
            if ended:
                await interaction.response.send_message(
                    "❌ 这个抽奖已经结束了。", ephemeral=True
                )
                return

            if restrict_role:
                member_roles = getattr(interaction.user, "roles", ())
                if not any(role.id == restrict_role for role in member_roles):
                    await interaction.response.send_message(
                        "❌ 你没有参加该抽奖所需的身份组。", ephemeral=True
                    )
                    return

            # 检查是否已参加
            cursor2 = await db.execute(
                "SELECT 1 FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                (giveaway_id, interaction.user.id),
            )
            if await cursor2.fetchone():
                # 取消参加
                await db.execute(
                    "DELETE FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                    (giveaway_id, interaction.user.id),
                )
                await db.commit()
                # 更新计数
                cursor3 = await db.execute(
                    "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?",
                    (giveaway_id,),
                )
                count = (await cursor3.fetchone())[0]
                await interaction.response.send_message(
                    "✅ 你已取消参加抽奖。", ephemeral=True
                )
            else:
                # 参加
                await db.execute(
                    "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)",
                    (giveaway_id, interaction.user.id),
                )
                await db.commit()
                cursor3 = await db.execute(
                    "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?",
                    (giveaway_id,),
                )
                count = (await cursor3.fetchone())[0]
                await interaction.response.send_message(
                    f"✅ 你已成功参加抽奖！当前参与人数: {count}", ephemeral=True
                )

        # 按钮文字里的人数改为节流更新（点击本身只回复 ephemeral，避免大型抽奖触发限流）
        cog = interaction.client.get_cog("Giveaway")
        if cog is not None:
            message = interaction.message
            cog.label_debouncer.schedule(
                message.id,
                lambda: cog._refresh_entry_label(message, giveaway_id),
            )


class Giveaway(commands.Cog):
    """抽奖管理 — 公平透明的抽奖系统"""

    def __init__(self, bot):
        self.bot = bot
        self.label_debouncer = Debouncer(LABEL_REFRESH_SECONDS)

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER DEFAULT 0,
                    host_id INTEGER NOT NULL,
                    prize TEXT NOT NULL,
                    winners_count INTEGER DEFAULT 1,
                    end_time REAL NOT NULL,
                    ended INTEGER DEFAULT 0,
                    restrict_role INTEGER DEFAULT 0
                )
            """)
            try:
                await db.execute(
                    "ALTER TABLE giveaways ADD COLUMN restrict_role INTEGER DEFAULT 0"
                )
            except Exception:
                pass
            await db.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    giveaway_id INTEGER,
                    user_id INTEGER,
                    PRIMARY KEY (giveaway_id, user_id),
                    FOREIGN KEY (giveaway_id) REFERENCES giveaways(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_winners (
                    giveaway_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    selected_at REAL NOT NULL,
                    PRIMARY KEY (giveaway_id, user_id),
                    FOREIGN KEY (giveaway_id) REFERENCES giveaways(id)
                )
            """)
            await db.commit()

        # 注册持久化 View
        self.bot.add_view(GiveawayEntryButton())

        # 启动定时检查
        if not self.check_giveaways.is_running():
            self.check_giveaways.start()

        print("✅ 抽奖系统已准备就绪！")

    def cog_unload(self):
        self.check_giveaways.cancel()
        self.label_debouncer.cancel_all()

    # ─── 工具 ───

    async def _refresh_entry_label(self, message: discord.Message, giveaway_id: int):
        """节流窗口结束时执行：按此刻数据库里的人数更新参与按钮标签（已结束的抽奖不再编辑）"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT ended FROM giveaways WHERE id = ?", (giveaway_id,)
            )
            row = await cursor.fetchone()
            if not row or row[0]:
                return
            cursor = await db.execute(
                "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,),
            )
            count = (await cursor.fetchone())[0]
        view = GiveawayEntryButton()
        view.enter.label = f"🎉 参加抽奖! ({count}人)"
        try:
            await message.edit(view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    def _format_time_left(self, seconds: float) -> str:
        if seconds <= 0:
            return "已结束"
        days, rem = divmod(int(seconds), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}天")
        if hours:
            parts.append(f"{hours}小时")
        if minutes:
            parts.append(f"{minutes}分钟")
        if secs and not days:
            parts.append(f"{secs}秒")
        return " ".join(parts) if parts else "即将结束"

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """解析时长字符串，如 1h, 30m, 2d, 1d12h（共享实现见 rincore.durations）"""
        return durations.parse_duration(duration_str)

    async def _pick_winners(self, giveaway_id: int, count: int) -> list[int]:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT guild_id, restrict_role FROM giveaways WHERE id = ?",
                (giveaway_id,),
            )
            giveaway = await cursor.fetchone()
            if not giveaway:
                return []
            cursor = await db.execute(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,),
            )
            entries = [row[0] for row in await cursor.fetchall()]
            cursor = await db.execute(
                "SELECT user_id FROM giveaway_winners WHERE giveaway_id = ?",
                (giveaway_id,),
            )
            previous_winners = {row[0] for row in await cursor.fetchall()}

        guild_id, restrict_role = giveaway
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []
        eligible = []
        for user_id in entries:
            member = guild.get_member(user_id)
            if not member or member.bot or user_id in previous_winners:
                continue
            if restrict_role and not any(
                role.id == restrict_role for role in member.roles
            ):
                continue
            eligible.append(user_id)
        if not eligible:
            return []
        return secrets.SystemRandom().sample(eligible, min(count, len(eligible)))

    async def _record_winners(self, giveaway_id: int, winners: list[int]):
        if not winners:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executemany(
                "INSERT OR IGNORE INTO giveaway_winners (giveaway_id, user_id, selected_at) VALUES (?, ?, ?)",
                [(giveaway_id, user_id, time.time()) for user_id in winners],
            )
            await db.commit()

    async def _end_giveaway(self, giveaway_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT guild_id, channel_id, message_id, prize, winners_count, host_id, ended FROM giveaways WHERE id = ?",
                (giveaway_id,),
            )
            row = await cursor.fetchone()
            if not row or row[6]:
                return
            guild_id, channel_id, message_id, prize, winners_count, host_id, _ = row

            cursor = await db.execute(
                "UPDATE giveaways SET ended = 1 WHERE id = ? AND ended = 0",
                (giveaway_id,),
            )
            await db.commit()
            if cursor.rowcount != 1:
                return

        # 取消待执行的按钮人数刷新，避免它在下面移除按钮之后又把按钮挂回去
        self.label_debouncer.cancel(message_id)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        winners = await self._pick_winners(giveaway_id, winners_count)
        await self._record_winners(giveaway_id, winners)

        # 更新原消息
        try:
            msg = await channel.fetch_message(message_id)
            card = discord.Embed.from_dict(giveaway_ended(prize, giveaway_id, winners))
            await msg.edit(embed=card, view=None)
        except discord.NotFound:
            pass

        # 发送开奖通知
        if winners:
            winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
            await channel.send(
                f"🎉 恭喜 {winner_mentions} 赢得了 **{prize}**！\n"
                f"请联系 <@{host_id}> 领取奖品。"
            )

    # ─── 定时检查 ───

    @tasks.loop(seconds=15)
    async def check_giveaways(self):
        now = time.time()
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id FROM giveaways WHERE ended = 0 AND end_time <= ?", (now,)
            )
            expired = await cursor.fetchall()

        for (giveaway_id,) in expired:
            try:
                await self._end_giveaway(giveaway_id)
            except Exception as e:
                print(f"抽奖结束错误 #{giveaway_id}: {e}")

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ─── 指令：giveaway start ───

    @commands.hybrid_group(name="giveaway", aliases=["gw"], description="Start and manage giveaways")
    @commands.guild_only()
    @require(manage_guild=True)
    async def giveaway_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send(
                "用法: `/giveaway start`, `/giveaway end`, `/giveaway reroll`, `/giveaway list`"
            )

    @giveaway_group.command(name="start", description="Start a giveaway in this channel")
    @app_commands.describe(duration="How long it runs, up to 365 days", winners="How many winners, 1-20", prize="What the winners get")
    @commands.guild_only()
    @require(manage_guild=True)
    async def gw_start(
        self, ctx, duration: Duration("giveaway"), winners: commands.Range[int, 1, 20] = 1, *, prize: str
    ):
        await ctx.defer()
        seconds = duration

        end_time = time.time() + seconds
        end_ts = int(end_time)

        card = discord.Embed.from_dict(giveaway_running(prize, winners, end_ts, host_id=ctx.author.id))
        view = GiveawayEntryButton()
        msg = await ctx.send(embed=card, view=view)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time, restrict_role) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ctx.guild.id,
                    ctx.channel.id,
                    msg.id,
                    ctx.author.id,
                    prize,
                    winners,
                    end_time,
                    0,
                ),
            )
            await db.commit()

        await audit(
            self.bot,
            ctx.guild.id,
            "发起抽奖活动",
            **{
                "操作者": ctx.author.mention,
                "奖品": prize,
                "中奖人数": str(winners),
                "频道": ctx.channel.mention,
            },
        )

    @giveaway_group.command(name="end", description="End a running giveaway now")
    @app_commands.describe(giveaway="The giveaway to end; pick from the list")
    @commands.guild_only()
    @require(manage_guild=True)
    async def gw_end(self, ctx, giveaway: int):
        giveaway_id = giveaway
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT ended FROM giveaways WHERE id = ? AND guild_id = ?",
                (giveaway_id, ctx.guild.id),
            )
            row = await cursor.fetchone()
            if not row:
                await ctx.send("❌ 找不到该抽奖活动。")
                return
            if row[0]:
                await ctx.send("❌ 该抽奖已经结束了。")
                return

        await self._end_giveaway(giveaway_id)
        await ctx.send(f"✅ 抽奖 #{giveaway_id} 已提前结束!", ephemeral=True)
        await audit(
            self.bot,
            ctx.guild.id,
            "提前结束抽奖",
            **{"操作者": ctx.author.mention, "抽奖 ID": str(giveaway_id)},
        )

    @giveaway_group.command(name="reroll", description="Draw new winners for an ended giveaway")
    @app_commands.describe(giveaway="The ended giveaway; pick from the list", count="How many new winners, 1-20")
    @commands.guild_only()
    @require(manage_guild=True)
    async def gw_reroll(self, ctx, giveaway: int, count: commands.Range[int, 1, 20] = 1):
        giveaway_id = giveaway
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT channel_id, prize, ended FROM giveaways WHERE id = ? AND guild_id = ?",
                (giveaway_id, ctx.guild.id),
            )
            row = await cursor.fetchone()
            if not row:
                await ctx.send("❌ 找不到该抽奖活动。")
                return
            if not row[2]:
                await ctx.send("❌ 该抽奖还没结束，无法 Reroll。")
                return

        winners = await self._pick_winners(giveaway_id, count)
        if winners:
            await self._record_winners(giveaway_id, winners)
            winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
            await ctx.send(f"🎉 Reroll 结果: {winner_mentions} 赢得了 **{row[1]}**!")
            await audit(
                self.bot,
                ctx.guild.id,
                "重新抽取获奖者",
                **{
                    "操作者": ctx.author.mention,
                    "抽奖 ID": str(giveaway_id),
                    "新获奖者数": str(len(winners)),
                },
            )
        else:
            await ctx.send("❌ 没有新的合格参与者可以 Reroll。")

    @giveaway_group.command(name="list", description="List this server's recent giveaways")
    @commands.guild_only()
    @require(manage_guild=True)
    async def gw_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, prize, winners_count, end_time, ended FROM giveaways WHERE guild_id = ? ORDER BY end_time DESC LIMIT 10",
                (ctx.guild.id,),
            )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("📭 当前没有抽奖活动。")
            return

        fields = [
            (
                f"#{gw_id} — {prize}",
                f"名额: {wc} | 状态: {'✅ 已结束' if ended else f'⏳ <t:{int(end_time)}:R>'}",
                False,
            )
            for gw_id, prize, wc, end_time, ended in rows
        ]
        await ctx.send(embed=embed("info", "最近的抽奖", fields=fields))


    gw_start.autocomplete("duration")(duration_autocomplete("giveaway"))

    @gw_end.autocomplete("giveaway")
    async def _running_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            rows = await _giveaway_rows(interaction.guild.id, ended=False)
        except Exception:
            return []
        zh, now = is_zh(interaction), time.time()
        items = []
        for gw_id, prize, end_time in rows:
            left = durations.label(max(60, int(end_time - now) // 60 * 60), zh)
            items.append((f"{prize[:60]} 剩 {left}" if zh else f"{prize[:60]} {left} left", gw_id))
        return choices(items, current)

    @gw_reroll.autocomplete("giveaway")
    async def _ended_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        try:
            rows = await _giveaway_rows(interaction.guild.id, ended=True)
        except Exception:
            return []
        zh = is_zh(interaction)
        return choices([(f"{prize[:60]} 已结束" if zh else f"{prize[:60]} ended", gw_id) for gw_id, prize, _ in rows], current)

async def _giveaway_rows(guild_id: int, ended: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, prize, end_time FROM giveaways WHERE guild_id = ? AND ended = ? ORDER BY end_time "
            + ("DESC" if ended else "ASC") + " LIMIT 50",
            (guild_id, 1 if ended else 0),
        )
        return await cursor.fetchall()


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
