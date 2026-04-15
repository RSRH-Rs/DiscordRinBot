# cogs/giveaway.py
# RinBot — 抽奖管理模块
# 功能：
#   • /giveaway start — 发起抽奖活动（设置奖品、时长、中奖人数）
#   • /giveaway end   — 提前结束抽奖
#   • /giveaway reroll — 重新抽取获奖者
#   • /giveaway list  — 查看活跃的抽奖活动
#   • 自动倒计时 + 自动开奖

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import aiosqlite
import random
import time
import asyncio
from typing import Optional

DB_PATH = "giveaway.db"
GIVEAWAY_EMOJI = "🎉"


class GiveawayEntryButton(View):
    """抽奖参与按钮"""

    def __init__(self):
        super().__init__(timeout=None)  # 持久化

    @discord.ui.button(label="🎉 参加抽奖!", style=discord.ButtonStyle.success, custom_id="giveaway_enter")
    async def enter(self, interaction: discord.Interaction, button: Button):
        # 查找这个消息对应的抽奖
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, ended FROM giveaways WHERE message_id = ?",
                (interaction.message.id,),
            )
            row = await cursor.fetchone()
            if not row:
                await interaction.response.send_message("❌ 找不到该抽奖活动。", ephemeral=True)
                return
            giveaway_id, ended = row
            if ended:
                await interaction.response.send_message("❌ 这个抽奖已经结束了。", ephemeral=True)
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
                cursor3 = await db.execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,))
                count = (await cursor3.fetchone())[0]
                await interaction.response.send_message("✅ 你已取消参加抽奖。", ephemeral=True)
            else:
                # 参加
                await db.execute(
                    "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)",
                    (giveaway_id, interaction.user.id),
                )
                await db.commit()
                cursor3 = await db.execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,))
                count = (await cursor3.fetchone())[0]
                await interaction.response.send_message(f"✅ 你已成功参加抽奖！当前参与人数: {count}", ephemeral=True)

            # 更新按钮文字显示人数
            button.label = f"🎉 参加抽奖! ({count}人)"
            await interaction.message.edit(view=self)


class Giveaway(commands.Cog):
    """抽奖管理 — 公平透明的抽奖系统"""

    def __init__(self, bot):
        self.bot = bot

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
                    ended INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    giveaway_id INTEGER,
                    user_id INTEGER,
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

    # ─── 工具 ───

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
        """解析时长字符串，如 1h, 30m, 2d, 1d12h"""
        total = 0
        num_buf = ""
        for ch in duration_str.lower():
            if ch.isdigit():
                num_buf += ch
            elif ch in ("d", "h", "m", "s"):
                if not num_buf:
                    return None
                n = int(num_buf)
                if ch == "d":
                    total += n * 86400
                elif ch == "h":
                    total += n * 3600
                elif ch == "m":
                    total += n * 60
                elif ch == "s":
                    total += n
                num_buf = ""
            else:
                return None
        return total if total > 0 else None

    async def _pick_winners(self, giveaway_id: int, count: int) -> list[int]:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,),
            )
            entries = [row[0] for row in await cursor.fetchall()]

        if not entries:
            return []
        return random.sample(entries, min(count, len(entries)))

    async def _end_giveaway(self, giveaway_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT guild_id, channel_id, message_id, prize, winners_count, host_id FROM giveaways WHERE id = ?",
                (giveaway_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return
            guild_id, channel_id, message_id, prize, winners_count, host_id = row

            await db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,))
            await db.commit()

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        winners = await self._pick_winners(giveaway_id, winners_count)

        # 更新原消息
        try:
            msg = await channel.fetch_message(message_id)
            if winners:
                winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
                embed = discord.Embed(
                    title="🎊 抽奖结束！",
                    description=f"**奖品:** {prize}\n**获奖者:** {winner_mentions}",
                    color=discord.Color.gold(),
                )
            else:
                embed = discord.Embed(
                    title="🎊 抽奖结束",
                    description=f"**奖品:** {prize}\n没有人参加抽奖 😢",
                    color=discord.Color.dark_grey(),
                )
            embed.set_footer(text=f"抽奖 ID: {giveaway_id} | 由 小凛 公正开奖")
            await msg.edit(embed=embed, view=None)
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

    @commands.hybrid_group(name="giveaway", aliases=["gw"], description="抽奖管理")
    async def giveaway_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("用法: `/giveaway start`, `/giveaway end`, `/giveaway reroll`, `/giveaway list`")

    @giveaway_group.command(name="start", description="发起一个抽奖活动")
    @commands.has_permissions(manage_guild=True)
    async def gw_start(self, ctx, duration: str, winners: int = 1, *, prize: str):
        """
        duration: 持续时间 (如 1h, 30m, 2d, 1d12h)
        winners: 中奖人数 (默认 1)
        prize: 奖品描述
        """
        await ctx.defer()

        seconds = self._parse_duration(duration)
        if not seconds:
            await ctx.send("❌ 无效的时间格式！示例: `1h`, `30m`, `2d`, `1d12h`")
            return

        if winners < 1 or winners > 20:
            await ctx.send("❌ 中奖人数范围: 1-20")
            return

        end_time = time.time() + seconds
        end_ts = int(end_time)

        embed = discord.Embed(
            title="🎉 抽奖活动！",
            description=(
                f"**奖品:** {prize}\n"
                f"**中奖名额:** {winners} 人\n"
                f"**结束时间:** <t:{end_ts}:R> (<t:{end_ts}:f>)\n"
                f"**发起者:** {ctx.author.mention}\n\n"
                f"点击下方按钮参加抽奖！"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="小凛抽奖系统 | 公平公正公开")

        view = GiveawayEntryButton()
        msg = await ctx.send(embed=embed, view=view)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ctx.guild.id, ctx.channel.id, msg.id, ctx.author.id, prize, winners, end_time),
            )
            await db.commit()

    @giveaway_group.command(name="end", description="[管理] 提前结束一个抽奖")
    @commands.has_permissions(manage_guild=True)
    async def gw_end(self, ctx, giveaway_id: int):
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
        await ctx.send(f"✅ 抽奖 #{giveaway_id} 已提前结束！", ephemeral=True)

    @giveaway_group.command(name="reroll", description="[管理] 重新抽取获奖者")
    @commands.has_permissions(manage_guild=True)
    async def gw_reroll(self, ctx, giveaway_id: int, count: int = 1):
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
            winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
            await ctx.send(f"🎉 Reroll 结果: {winner_mentions} 赢得了 **{row[1]}**！")
        else:
            await ctx.send("❌ 没有参与者可以 Reroll。")

    @giveaway_group.command(name="list", description="查看当前活跃的抽奖活动")
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

        embed = discord.Embed(title="🎉 抽奖活动列表", color=discord.Color.green())
        for gw_id, prize, wc, end_time, ended in rows:
            status = "✅ 已结束" if ended else f"⏳ <t:{int(end_time)}:R>"
            embed.add_field(
                name=f"#{gw_id} — {prize}",
                value=f"名额: {wc} | 状态: {status}",
                inline=False,
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
