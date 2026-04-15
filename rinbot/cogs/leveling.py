import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import io
import os
import aiohttp
import aiosqlite
import random
import time
import math

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

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # --- 🔧 配置路径 (根据上面的文件夹结构) ---
        self.assets_path = "./assets"
        self.bg_name = "rin_bot_leveling_bg.png"
        self.font_name = "LXGWWenKaiTC-Regular.ttf"
        self.flower_name = "flower.png"

        # --- ⚙️ 经验算法配置 ---
        self.xp_min = 15
        self.xp_max = 25
        self.cooldown_sec = 60
        self.cooldowns = {}

    async def cog_load(self):
        """插件加载时自动初始化数据库"""
        async with aiosqlite.connect("leveling.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    guild_id INTEGER,
                    user_id INTEGER,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await db.commit()
        print("✅ 等级系统 (小凛美化版) 已准备就绪！")

    # --- 🛠️ 核心经验算法 ---
    def get_total_xp_for_level(self, level):
        """计算达到某个等级所需的总经验值"""
        return int((5 / 6) * level * (2 * level * level + 27 * level + 91))

    # --- 🎨 核心绘图逻辑 (内存版) ---
    def generate_cute_rank_card_bytes(self, username, avatar_img, level, rank, current_xp, max_xp):
        card_size = (800, 250)

        # 1. 加载自定义背景图
        bg_path = os.path.join(self.assets_path, self.bg_name)
        try:
            bg_img = Image.open(bg_path).convert("RGBA")
            img = bg_img.resize(card_size)
        except FileNotFoundError:
            img = Image.new("RGBA", card_size, (255, 228, 225, 255)) # 默认粉色

        # 2. 半透明底板
        overlay = Image.new("RGBA", card_size, (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle([(20, 20), (780, 230)], radius=20, fill=(255, 255, 255, 160))
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
        draw.text((230, 110), f"Level {level}  |  Rank #{rank}", fill=text_color, font=font_medium)

        # 经验值文本
        formatted_current = format_xp_number(current_xp)
        formatted_max = format_xp_number(max_xp)
        xp_text = f"{formatted_current} / {formatted_max} XP"

        # 靠右对齐 XP 文本
        try:
            xp_text_width = draw.textlength(xp_text, font=font_small)
        except AttributeError:
            xp_text_width = font_small.getsize(xp_text)[0]
        draw.text((750 - xp_text_width, 115), xp_text, fill=(150, 100, 120, 255), font=font_small)

        # 6. 绘制经验条
        bar_x0, bar_y0 = 230, 150
        bar_x1, bar_y1 = 750, 180
        bar_width = bar_x1 - bar_x0

        draw.rounded_rectangle([(bar_x0, bar_y0), (bar_x1, bar_y1)], radius=15, fill=(230, 230, 235, 200))

        # 计算进度条宽度并绘制
        progress_ratio = min(current_xp / max_xp, 1.0) if max_xp > 0 else 0
        current_bar_width = max(bar_width * progress_ratio, 30)
        draw.rounded_rectangle(
            [(bar_x0, bar_y0), (bar_x0 + current_bar_width, bar_y1)],
            radius=15, fill=(255, 182, 193, 255)
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

        user_id = message.author.id
        now = time.time()

        if user_id in self.cooldowns:
            if now - self.cooldowns[user_id] < self.cooldown_sec:
                return

        self.cooldowns[user_id] = now
        xp_gain = random.randint(self.xp_min, self.xp_max)

        async with aiosqlite.connect("leveling.db") as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (guild_id, user_id, xp, level) VALUES (?, ?, 0, 0)",
                (message.guild.id, user_id)
            )
            await db.execute(
                "UPDATE users SET xp = xp + ? WHERE guild_id = ? AND user_id = ?",
                (xp_gain, message.guild.id, user_id)
            )

            cursor = await db.execute("SELECT xp, level FROM users WHERE guild_id = ? AND user_id = ?", (message.guild.id, user_id))
            row = await cursor.fetchone()

            if row:
                total_xp, current_level = row
                xp_needed_for_next_lvl = self.get_total_xp_for_level(current_level + 1)

                if total_xp >= xp_needed_for_next_lvl:
                    new_level = current_level + 1
                    await db.execute("UPDATE users SET level = ? WHERE guild_id = ? AND user_id = ?", (new_level, message.guild.id, user_id))
                    await message.channel.send(f"🎉 恭喜 **{message.author.mention}**！你升级到了 **Level {new_level}**！✨")

            await db.commit()

    # --- 🖼️ Rank 指令 ---
    @commands.hybrid_command(name="rank", description="查看你的等级卡片")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.defer() # 告诉 Discord 机器人正在思考，防止超时

        guild_id = ctx.guild.id
        user_id = member.id

        total_xp = 0
        current_level = 0
        rank_num = 1

        # 从数据库获取数据
        async with aiosqlite.connect("leveling.db") as db:
            cursor = await db.execute("SELECT xp, level FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            row = await cursor.fetchone()
            if row:
                total_xp, current_level = row

            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE guild_id = ? AND xp > ?", (guild_id, total_xp))
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
        image_buffer = self.generate_cute_rank_card_bytes(
            username=member.display_name,
            avatar_img=avatar_img,
            level=current_level,
            rank=rank_num,
            current_xp=xp_in_level,
            max_xp=xp_needed_for_level
        )

        # 发送图片到频道
        await ctx.send(file=discord.File(fp=image_buffer, filename="rank.png"))


async def setup(bot):
    await bot.add_cog(Leveling(bot))