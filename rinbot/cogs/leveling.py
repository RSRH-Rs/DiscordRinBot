import asyncio
import discord
from discord import app_commands
from _messages import embed
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import io
import os
import aiohttp
import aiosqlite
import json
import random
import time
import math

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "leveling.db")

CREATE_CONFIG_SQL = """CREATE TABLE IF NOT EXISTS level_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    notify_mode TEXT DEFAULT 'here',
    notify_channel INTEGER DEFAULT 0,
    rewards TEXT DEFAULT '[]'
)"""
CONFIG_COLUMNS = "guild_id, enabled, notify_mode, notify_channel, rewards"


# --- 辅助函数：经验值格式化 ---
def format_xp_number(num):
    """将大数字格式化为 K, M, B 等简写形式，让界面更清爽"""
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B".replace(".0B", "B")
    elif num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M".replace(".0M", "M")
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K".replace(".0K", "K")
    else:
        return str(num)


def parse_rewards(raw):
    """把存储的奖励 JSON 解析成 [(等级, 身份组 id)]；内容损坏时按没有奖励处理"""
    try:
        items = json.loads(raw or "[]")
        if not isinstance(items, list):
            raise TypeError("rewards is not a list")
        return [(int(item["level"]), int(item["role_id"])) for item in items]
    except (TypeError, ValueError, KeyError) as e:
        print(f"等级奖励内容损坏，按没有奖励处理: {e!r}")
        return []


def due_role_ids(rewards, level, owned_ids):
    """已达到等级、成员却还没有的身份组 id（奖励累积保留，低等级的也要补）"""
    return [role_id for required, role_id in rewards if required <= level and role_id not in owned_ids]


def config_from_row(row):
    return {
        "enabled": bool(row[1]),
        "notify_mode": row[2],
        "notify_channel": int(row[3] or 0),
        "rewards": parse_rewards(row[4]),
    }


def prune_cooldowns(cooldowns, now, ttl, max_size=5000):
    """冷却字典超过 max_size 时，就地清除早于 ttl 的过期条目，避免无限增长"""
    if len(cooldowns) <= max_size:
        return
    for key in [k for k, t in cooldowns.items() if now - t >= ttl]:
        del cooldowns[key]


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # --- 🔧 配置路径 (根据上面的文件夹结构) ---
        self.assets_path = os.path.join(BASE_DIR, "assets")
        self.bg_name = "rin_bot_leveling_bg.png"
        self.font_name = "LXGWWenKaiTC-Regular.ttf"
        self.flower_name = "flower.png"

        # --- ⚙️ 经验算法配置 ---
        self.xp_min = 15
        self.xp_max = 25
        self.cooldown_sec = 60
        self.cooldowns = {}
        self._config = {}

    async def cog_load(self):
        """插件加载时自动初始化数据库"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    guild_id INTEGER,
                    user_id INTEGER,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await db.execute(CREATE_CONFIG_SQL)
            await db.commit()
            cursor = await db.execute(f"SELECT {CONFIG_COLUMNS} FROM level_config")
            self._config = {row[0]: config_from_row(row) for row in await cursor.fetchall()}
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.register("leveling", self.reload_guild)
        print("✅ 等级系统 (小凛美化版) 已准备就绪！")

    def cog_unload(self):
        watcher = getattr(self.bot, "change_watcher", None)
        if watcher is not None:
            watcher.unregister("leveling", self.reload_guild)

    async def reload_guild(self, guild_id):
        """网页保存后由变更日志回调：只重读该服务器的一行配置"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                f"SELECT {CONFIG_COLUMNS} FROM level_config WHERE guild_id=?", (guild_id,)
            )
            row = await cursor.fetchone()
        if row:
            self._config[guild_id] = config_from_row(row)
        else:
            self._config.pop(guild_id, None)

    def get_config(self, guild_id):
        """读内存；未配置的服务器返回默认值，行为和没有这项设置时一样"""
        config = self._config.get(guild_id)
        if config:
            return {**config, "rewards": list(config["rewards"])}
        return {"enabled": True, "notify_mode": "here", "notify_channel": 0, "rewards": []}

    # --- 🛠️ 核心经验算法 ---
    def get_total_xp_for_level(self, level):
        """计算达到某个等级所需的总经验值"""
        return int((5 / 6) * level * (2 * level * level + 27 * level + 91))

    # --- 🎨 核心绘图逻辑 (内存版) ---
    def generate_cute_rank_card_bytes(
        self, username, avatar_img, level, rank, current_xp, max_xp
    ):
        card_size = (800, 250)

        # 1. 加载自定义背景图
        bg_path = os.path.join(self.assets_path, self.bg_name)
        try:
            bg_img = Image.open(bg_path).convert("RGBA")
            img = bg_img.resize(card_size)
        except FileNotFoundError:
            img = Image.new("RGBA", card_size, (255, 228, 225, 255))  # 默认粉色

        # 2. 半透明底板
        overlay = Image.new("RGBA", card_size, (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            [(20, 20), (780, 230)], radius=20, fill=(255, 255, 255, 160)
        )
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        # 3. 处理头像 (裁剪为圆形)
        avatar_pos = (40, 45)
        avatar_size = (160, 160)

        # 将传入的 Discord 头像调整尺寸并切圆
        avatar_img = avatar_img.resize(avatar_size).convert("RGBA")
        mask = Image.new("L", avatar_size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, 160, 160), fill=255)
        img.paste(avatar_img, avatar_pos, mask)

        # 4. 设置字体
        font_path = os.path.join(self.assets_path, self.font_name)
        try:
            font_large = ImageFont.truetype(font_path, 32)
            font_medium = ImageFont.truetype(font_path, 24)
            font_small = ImageFont.truetype(font_path, 20)
        except IOError:
            font_large = font_medium = font_small = ImageFont.load_default()

        # 5. 绘制文字信息
        text_color = (80, 50, 60, 255)

        # 处理超长用户名
        display_name = username if len(username) <= 15 else username[:14] + "..."
        draw.text((230, 50), display_name, fill=text_color, font=font_large)
        draw.text(
            (230, 110),
            f"Level {level}  |  Rank #{rank}",
            fill=text_color,
            font=font_medium,
        )

        # 经验值文本
        formatted_current = format_xp_number(current_xp)
        formatted_max = format_xp_number(max_xp)
        xp_text = f"{formatted_current} / {formatted_max} XP"

        # 靠右对齐 XP 文本
        try:
            xp_text_width = draw.textlength(xp_text, font=font_small)
        except AttributeError:
            xp_text_width = font_small.getsize(xp_text)[0]
        draw.text(
            (750 - xp_text_width, 115),
            xp_text,
            fill=(150, 100, 120, 255),
            font=font_small,
        )

        # 6. 绘制经验条
        bar_x0, bar_y0 = 230, 150
        bar_x1, bar_y1 = 750, 180
        bar_width = bar_x1 - bar_x0

        draw.rounded_rectangle(
            [(bar_x0, bar_y0), (bar_x1, bar_y1)], radius=15, fill=(230, 230, 235, 200)
        )

        # 计算进度条宽度并绘制
        progress_ratio = min(current_xp / max_xp, 1.0) if max_xp > 0 else 0
        current_bar_width = max(bar_width * progress_ratio, 30)
        draw.rounded_rectangle(
            [(bar_x0, bar_y0), (bar_x0 + current_bar_width, bar_y1)],
            radius=15,
            fill=(255, 182, 193, 255),
        )

        # 7. 添加进度指示器挂件 (樱花)
        marker_path = os.path.join(self.assets_path, self.flower_name)
        if os.path.exists(marker_path):
            marker = Image.open(marker_path).convert("RGBA")
            marker_size = 50
            marker = marker.resize((marker_size, marker_size))
            marker_x = int(bar_x0 + current_bar_width - (marker_size / 2))
            marker_y = int(bar_y0 + (bar_y1 - bar_y0) / 2 - (marker_size / 2))
            img.paste(marker, (marker_x, marker_y), marker)

        # 8. 存入内存并返回
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # --- 📨 消息监听 (增加 XP) ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        config = self.get_config(message.guild.id)
        if not config["enabled"]:
            return

        user_id = message.author.id
        now = time.time()

        cooldown_key = (message.guild.id, user_id)
        if cooldown_key in self.cooldowns:
            if now - self.cooldowns[cooldown_key] < self.cooldown_sec:
                return

        self.cooldowns[cooldown_key] = now
        prune_cooldowns(self.cooldowns, now, self.cooldown_sec)
        xp_gain = random.randint(self.xp_min, self.xp_max)
        leveled_to = None
        current_level = 0

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (guild_id, user_id, xp, level) VALUES (?, ?, 0, 0)",
                (message.guild.id, user_id),
            )
            await db.execute(
                "UPDATE users SET xp = xp + ? WHERE guild_id = ? AND user_id = ?",
                (xp_gain, message.guild.id, user_id),
            )

            cursor = await db.execute(
                "SELECT xp, level FROM users WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, user_id),
            )
            row = await cursor.fetchone()

            if row:
                total_xp, current_level = row
                xp_needed_for_next_lvl = self.get_total_xp_for_level(current_level + 1)

                if total_xp >= xp_needed_for_next_lvl:
                    leveled_to = current_level + 1
                    await db.execute(
                        "UPDATE users SET level = ? WHERE guild_id = ? AND user_id = ?",
                        (leveled_to, message.guild.id, user_id),
                    )

            # 先提交经验与等级，再调用 Discord（发送失败不能丢经验）
            await db.commit()

        if leveled_to is not None:
            await self._send_level_notice(message, leveled_to, config)
        if isinstance(message.author, discord.Member):
            await self._grant_rewards(message.author, leveled_to or current_level, config)

    async def _grant_rewards(self, member, level, config):
        """补发已达到等级却缺少的奖励；小凛给不了的身份组直接跳过，不调用 Discord"""
        due = due_role_ids(config["rewards"], level, {role.id for role in member.roles})
        if not due:
            return
        guild = member.guild
        me = guild.me
        if not me.guild_permissions.manage_roles:
            return
        roles = [role for role in map(guild.get_role, due) if role and not role.managed and role < me.top_role]
        if not roles:
            return
        try:
            await member.add_roles(*roles, reason="等级奖励")
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"等级奖励发放失败 (guild {guild.id}): {e}")

    async def _send_level_notice(self, message, new_level, config):
        mode = config["notify_mode"]
        if mode == "off":
            return
        # 指定频道没了就不发：选指定频道通常就是不想在聊天区刷屏，不能改发到原频道
        channel = (
            message.guild.get_channel(config["notify_channel"])
            if mode == "channel"
            else message.channel
        )
        if channel is None:
            return
        try:
            await channel.send(
                f"🎉 恭喜 **{message.author.mention}**！你升级到了 **Level {new_level}**！✨"
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"升级提示发送失败 (guild {message.guild.id}): {e}")

    # --- 🖼️ Rank 指令 ---
    @commands.hybrid_command(name="rank", description="Show a level card")
    @commands.guild_only()
    @app_commands.describe(member="Whose card; default yours")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.defer()  # 告诉 Discord 机器人正在思考，防止超时

        guild_id = ctx.guild.id
        user_id = member.id

        total_xp = 0
        current_level = 0
        rank_num = 1

        # 从数据库获取数据
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT xp, level FROM users WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            if row:
                total_xp, current_level = row

            cursor = await db.execute(
                "SELECT COUNT(*) FROM users WHERE guild_id = ? AND xp > ?",
                (guild_id, total_xp),
            )
            rank_num = (await cursor.fetchone())[0] + 1

        # 计算当前等级内的进度
        xp_current_lvl_start = self.get_total_xp_for_level(current_level)
        xp_next_lvl_end = self.get_total_xp_for_level(current_level + 1)

        xp_in_level = total_xp - xp_current_lvl_start
        xp_needed_for_level = xp_next_lvl_end - xp_current_lvl_start

        # 获取 Discord 用户头像字节流
        try:
            avatar_data = await member.display_avatar.read()
            avatar_img = Image.open(io.BytesIO(avatar_data))
        except:
            # 如果获取失败，用灰色图片占位
            avatar_img = Image.new("RGBA", (160, 160), color=(200, 200, 200, 255))

        # 调用画图函数生成图片 buffer
        image_buffer = await asyncio.to_thread(
            self.generate_cute_rank_card_bytes,
            username=member.display_name,
            avatar_img=avatar_img,
            level=current_level,
            rank=rank_num,
            current_xp=xp_in_level,
            max_xp=xp_needed_for_level,
        )

        # 发送图片到频道
        await ctx.send(file=discord.File(fp=image_buffer, filename="rank.png"))

    # --- 🏆 Leaderboard 排行榜 ---
    @commands.hybrid_command(
        name="leaderboard", aliases=["top", "lb"], description="Show this server's level leaderboard"
    )
    @commands.guild_only()
    @app_commands.describe(page="Which page to show")
    async def leaderboard(self, ctx, page: commands.Range[int, 1, None] = 1):
        per_page = 10
        offset = (page - 1) * per_page

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM users WHERE guild_id = ? AND xp > 0",
                (ctx.guild.id,),
            )
            total = (await cursor.fetchone())[0]
            if total == 0:
                await ctx.send("📭 还没有人在这个服务器获得经验值哦~")
                return

            cursor = await db.execute(
                "SELECT user_id, xp, level FROM users WHERE guild_id = ? AND xp > 0 ORDER BY xp DESC LIMIT ? OFFSET ?",
                (ctx.guild.id, per_page, offset),
            )
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send(
                f"❌ 第 {page} 页没有数据(共 {(total - 1) // per_page + 1} 页)"
            )
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, (user_id, xp, level) in enumerate(rows, start=offset + 1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"未知用户"
            rank_icon = medals.get(i, f"`#{i:02d}`")
            lines.append(
                f"{rank_icon} **{name}**\n" f"╰ Lv.{level} · {format_xp_number(xp)} XP"
            )

        total_pages = (total - 1) // per_page + 1
        card = embed(
            "info",
            f"{ctx.guild.name} 等级排行榜",
            "\n\n".join(lines),
            footer=f"第 {page} / {total_pages} 页 · 共 {total} 位活跃成员",
        )
        if ctx.guild.icon:
            card.set_thumbnail(url=ctx.guild.icon.url)

        await ctx.send(embed=card)


async def setup(bot):
    await bot.add_cog(Leveling(bot))
