# cogs/welcome.py
# RinBot — 迎新 & 道别模块
# 功能：
#   • 新成员加入时自动发送欢迎图卡 + 分配基础身分组
#   • 成员离开时发送道别消息
#   • /welcome_setup — 配置欢迎频道、身分组、道别频道
#   • /welcome_test — 测试欢迎图卡效果

import discord
from discord.ext import commands
from discord.ui import View, Select, ChannelSelect, RoleSelect
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
import aiosqlite
from _botlog_helper import audit

DB_PATH = "welcome.db"


class WelcomeSetupView(View):
    """交互式设置面板"""

    def __init__(self, cog, guild_id):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.select(
        cls=ChannelSelect,
        placeholder="📢 选择欢迎频道...",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1,
    )
    async def welcome_channel(
        self, interaction: discord.Interaction, select: ChannelSelect
    ):
        channel = select.values[0]
        await self.cog._set_config(self.guild_id, "welcome_channel", channel.id)
        botlog = self.cog.bot.get_cog("BotLog")
        if botlog:
            await botlog.log(
                self.guild_id,
                "config",
                "设置欢迎频道",
                **{"操作者": interaction.user.mention, "频道": channel.mention},
            )
        await interaction.response.send_message(
            f"✅ 欢迎频道已设为: {channel.mention}", ephemeral=True
        )

    @discord.ui.select(
        cls=ChannelSelect,
        placeholder="👋 选择道别频道 (可选)...",
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=1,
    )
    async def farewell_channel(
        self, interaction: discord.Interaction, select: ChannelSelect
    ):
        botlog = self.cog.bot.get_cog("BotLog")
        if select.values:
            channel = select.values[0]
            await self.cog._set_config(self.guild_id, "farewell_channel", channel.id)
            if botlog:
                await botlog.log(
                    self.guild_id,
                    "config",
                    "设置道别频道",
                    **{"操作者": interaction.user.mention, "频道": channel.mention},
                )
            await interaction.response.send_message(
                f"✅ 道别频道已设为: {channel.mention}", ephemeral=True
            )
        else:
            await self.cog._set_config(self.guild_id, "farewell_channel", 0)
            if botlog:
                await botlog.log(
                    self.guild_id,
                    "config",
                    "禁用道别消息",
                    **{"操作者": interaction.user.mention},
                )
            await interaction.response.send_message(
                "✅ 已禁用道别消息。", ephemeral=True
            )

    @discord.ui.select(
        cls=RoleSelect,
        placeholder="🏷 选择自动分配的身份组...",
        min_values=0,
        max_values=3,
    )
    async def auto_roles(self, interaction: discord.Interaction, select: RoleSelect):
        role_ids = [r.id for r in select.values]
        await self.cog._set_config(
            self.guild_id, "auto_roles", ",".join(str(r) for r in role_ids)
        )
        botlog = self.cog.bot.get_cog("BotLog")
        if role_ids:
            mentions = ", ".join(r.mention for r in select.values)
            if botlog:
                await botlog.log(
                    self.guild_id,
                    "config",
                    "设置自动身份组",
                    **{"操作者": interaction.user.mention, "身份组": mentions},
                )
            await interaction.response.send_message(
                f"✅ 新成员将自动获得: {mentions}", ephemeral=True
            )
        else:
            if botlog:
                await botlog.log(
                    self.guild_id,
                    "config",
                    "清除自动身份组",
                    **{"操作者": interaction.user.mention},
                )
            await interaction.response.send_message(
                "✅ 已清除自动分配身份组。", ephemeral=True
            )


class Welcome(commands.Cog):
    """迎新 & 道别系统"""

    def __init__(self, bot):
        self.bot = bot
        self.assets_path = "./assets"
        self.font_name = "LXGWWenKaiTC-Regular.ttf"

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome_config (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel INTEGER DEFAULT 0,
                    farewell_channel INTEGER DEFAULT 0,
                    auto_roles TEXT DEFAULT '',
                    welcome_msg TEXT DEFAULT '欢迎 %member% 加入 %server%！🎉',
                    farewell_msg TEXT DEFAULT '%member% 离开了我们... 👋',
                    show_card INTEGER DEFAULT 0,
                    welcome_title TEXT DEFAULT '',
                    author_icon TEXT DEFAULT '',
                    thumbnail_url TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    image_url TEXT DEFAULT ''
                )
            """)
            # 旧库补列
            for ddl in (
                "show_card INTEGER DEFAULT 0",
                "welcome_title TEXT DEFAULT ''",
                "author_icon TEXT DEFAULT ''",
                "thumbnail_url TEXT DEFAULT ''",
                "enabled INTEGER DEFAULT 1",
                "image_url TEXT DEFAULT ''",
            ):
                try:
                    await db.execute(f"ALTER TABLE welcome_config ADD COLUMN {ddl}")
                except Exception:
                    pass
            await db.commit()
        print("✅ 迎新 & 道别系统已准备就绪！")

    # ─── 数据库工具 ───

    async def _get_config(self, guild_id: int) -> dict:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM welcome_config WHERE guild_id = ?", (guild_id,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def _set_config(self, guild_id: int, key: str, value):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO welcome_config (guild_id) VALUES (?)",
                (guild_id,),
            )
            await db.execute(
                f"UPDATE welcome_config SET {key} = ? WHERE guild_id = ?",
                (value, guild_id),
            )
            await db.commit()

    # ─── 欢迎图卡生成 ───

    def _generate_welcome_card(
        self,
        member_name: str,
        guild_name: str,
        member_count: int,
        avatar_img: Image.Image,
    ) -> io.BytesIO:
        card_w, card_h = 900, 300

        # 背景
        bg_path = os.path.join(self.assets_path, "rin_bot_leveling_bg.png")
        try:
            img = Image.open(bg_path).convert("RGBA").resize((card_w, card_h))
            # 添加模糊背景效果
            blurred = img.filter(ImageFilter.GaussianBlur(3))
            img = blurred
        except FileNotFoundError:
            img = Image.new("RGBA", (card_w, card_h), (255, 182, 193, 255))

        # 半透明底板
        overlay = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle(
            [(20, 20), (card_w - 20, card_h - 20)], radius=25, fill=(255, 255, 255, 170)
        )
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        # 头像 (圆形 + 边框)
        av_size = 160
        avatar_img = avatar_img.resize((av_size, av_size)).convert("RGBA")
        # 圆形蒙版
        mask = Image.new("L", (av_size, av_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, av_size, av_size), fill=255)
        # 白色边框
        border = 6
        border_mask = Image.new(
            "RGBA", (av_size + border * 2, av_size + border * 2), (0, 0, 0, 0)
        )
        ImageDraw.Draw(border_mask).ellipse(
            (0, 0, av_size + border * 2, av_size + border * 2),
            fill=(255, 255, 255, 255),
        )
        av_x = 60
        av_y = (card_h - av_size) // 2
        img.paste(border_mask, (av_x - border, av_y - border), border_mask)
        img.paste(avatar_img, (av_x, av_y), mask)

        # 字体
        font_path = os.path.join(self.assets_path, self.font_name)
        try:
            font_title = ImageFont.truetype(font_path, 38)
            font_sub = ImageFont.truetype(font_path, 22)
            font_count = ImageFont.truetype(font_path, 18)
        except IOError:
            font_title = font_sub = font_count = ImageFont.load_default()

        text_x = av_x + av_size + 40
        text_color = (80, 50, 60, 255)
        sub_color = (120, 90, 100, 255)

        # 欢迎文字
        name_display = (
            member_name if len(member_name) <= 18 else member_name[:17] + "..."
        )
        draw.text(
            (text_x, 65), f"欢迎加入！", fill=(255, 105, 140, 255), font=font_title
        )
        draw.text((text_x, 120), name_display, fill=text_color, font=font_title)
        draw.text((text_x, 175), f"🏠 {guild_name}", fill=sub_color, font=font_sub)
        draw.text(
            (text_x, 210),
            f"✨ 你是第 {member_count} 位成员",
            fill=sub_color,
            font=font_count,
        )

        # 底部装饰线
        draw.line(
            [(text_x, 250), (card_w - 60, 250)], fill=(255, 182, 193, 200), width=2
        )

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # ─── 事件监听 ───

    @commands.Cog.listener()
    @staticmethod
    def _fmt_text(text, member, member_repr=None):
        # 统一 %xx%，同时兼容旧的 {xx}
        m = member_repr or member.mention
        return (
            (text or "")
            .replace("%member%", m)
            .replace("{member}", m)
            .replace("%server%", member.guild.name)
            .replace("{server}", member.guild.name)
        )

    @staticmethod
    def _resolve_img(value, member):
        v = (value or "").strip()
        if not v:
            return None
        if v == "%avatar%":
            return member.display_avatar.url
        if v in ("%server_avatar%", "%server%"):
            return member.guild.icon.url if member.guild.icon else None
        return v if v.lower().startswith(("http://", "https://")) else None

    def _build_welcome_embed(self, member, config):
        if not config.get("enabled", 1):
            return None
        guild = member.guild
        title = (config.get("welcome_title") or "").strip() or f"欢迎来到 {guild.name}"
        icon = (config.get("author_icon") or "").strip() or (
            guild.icon.url if guild.icon else None
        )
        thumb = self._resolve_img(config.get("thumbnail_url") or "%avatar%", member)
        big = self._resolve_img(config.get("image_url"), member)
        msg = self._fmt_text(
            config.get("welcome_msg") or "欢迎 %member% 加入 %server%！🎉", member
        )
        embed = discord.Embed(description=msg, color=discord.Color.pink())
        embed.set_author(name=title, icon_url=icon)
        if thumb:
            embed.set_thumbnail(url=thumb)
        if big:
            embed.set_image(url=big)
        return embed

    async def _render_card_file(self, member):
        try:
            avatar_data = await member.display_avatar.with_size(256).read()
            avatar_img = Image.open(io.BytesIO(avatar_data))
        except Exception:
            avatar_img = Image.new("RGBA", (256, 256), (200, 200, 200, 255))
        buf = self._generate_welcome_card(
            member_name=member.display_name,
            guild_name=member.guild.name,
            member_count=member.guild.member_count,
            avatar_img=avatar_img,
        )
        return discord.File(fp=buf, filename="welcome.png")

    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        config = await self._get_config(member.guild.id)
        if not config:
            return

        # 1. 自动分配身份组
        if config["auto_roles"]:
            role_ids = [int(r) for r in config["auto_roles"].split(",") if r]
            for role_id in role_ids:
                role = member.guild.get_role(role_id)
                if role:
                    try:
                        await member.add_roles(role, reason="小凛自动分配")
                    except discord.Forbidden:
                        pass

        # 2. 发送欢迎卡
        channel_id = config.get("welcome_channel", 0)
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        embed = self._build_welcome_embed(member, config)
        if embed is None:
            return
        files = []
        if config.get("show_card", 0):
            card = await self._render_card_file(member)
            files.append(card)
            embed.set_image(url="attachment://welcome.png")

        await channel.send(embed=embed, files=files)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        config = await self._get_config(member.guild.id)
        if not config:
            return

        channel_id = config.get("farewell_channel", 0)
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        embed = discord.Embed(
            description=self._fmt_text(
                config["farewell_msg"] or "%member% 离开了我们... 👋",
                member,
                member_repr=f"**{member.display_name}**",
            ),
            color=discord.Color.dark_grey(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"当前成员数: {member.guild.member_count}")
        await channel.send(embed=embed)

    # ─── 配置指令 ───

    @commands.hybrid_command(
        name="welcome_setup", description="[管理] 配置迎新 & 道别系统"
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_setup(self, ctx):
        embed = discord.Embed(
            title="🎀 迎新 & 道别设置面板",
            description=(
                "使用下方的选择器来配置各项功能：\n\n"
                "**📢 欢迎频道** — 新成员加入时发送欢迎图卡\n"
                "**👋 道别频道** — 成员离开时发送道别消息\n"
                "**🏷 自动身份组** — 新成员自动获得的身份组"
            ),
            color=discord.Color.pink(),
        )
        view = WelcomeSetupView(self, ctx.guild.id)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(
        name="welcome_message", description="[管理] 自定义欢迎/道别消息"
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_message(self, ctx, msg_type: str, *, text: str):
        """
        msg_type: welcome 或 farewell
        text: 消息模板，可用 {member} 和 {server}
        """
        if msg_type not in ("welcome", "farewell"):
            await ctx.send("❌ 类型只能是 `welcome` 或 `farewell`")
            return
        key = f"{msg_type}_msg"
        await self._set_config(ctx.guild.id, key, text)
        label = "欢迎消息" if msg_type == "welcome" else "道别消息"
        await audit(
            self.bot,
            ctx.guild.id,
            f"修改{label}模板",
            **{"操作者": ctx.author.mention, "内容": text[:200]},
        )
        preview = self._fmt_text(text, ctx.author)
        await ctx.send(f"✅ 已更新 {msg_type} 消息！\n预览: {preview}")

    @commands.hybrid_command(name="welcome_test", description="[管理] 预览欢迎卡片效果")
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(self, ctx):
        await ctx.defer()
        config = await self._get_config(ctx.guild.id) or {}
        embed = self._build_welcome_embed(ctx.author, config)
        if embed is None:
            await ctx.send("ℹ️ 欢迎讯息当前已停用。", ephemeral=True)
            return
        files = []
        if config.get("show_card", 0):
            card = await self._render_card_file(ctx.author)
            files.append(card)
            embed.set_image(url="attachment://welcome.png")
        await ctx.send(embed=embed, files=files)

    @commands.hybrid_command(
        name="welcome_toggle", description="[管理] 开启/关闭欢迎讯息"
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_toggle(self, ctx, enabled: bool):
        await self._set_config(ctx.guild.id, "enabled", 1 if enabled else 0)
        await ctx.send(
            f"✅ 欢迎讯息已{'开启' if enabled else '关闭'}。", ephemeral=True
        )

    @commands.hybrid_command(
        name="welcome_image",
        description="[管理] 自定义大图（留空关闭；支持 %avatar% / %server_avatar%）",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_image(self, ctx, url: str = ""):
        url = url.strip()
        if (
            url
            and url not in ("%avatar%", "%server_avatar%")
            and not url.lower().startswith(("http://", "https://"))
        ):
            await ctx.send(
                "❌ 请提供有效链接，或 %avatar% / %server_avatar%，或留空关闭。",
                ephemeral=True,
            )
            return
        await self._set_config(ctx.guild.id, "image_url", url)
        await ctx.send(
            "✅ 已关闭大图。" if not url else "✅ 大图已更新。", ephemeral=True
        )

    @commands.hybrid_command(
        name="welcome_title", description="[管理] 自定义欢迎卡标题"
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_title(self, ctx, *, text: str):
        await self._set_config(ctx.guild.id, "welcome_title", text[:200])
        await ctx.send(f"✅ 欢迎卡标题已设为：{text[:200]}", ephemeral=True)

    @commands.hybrid_command(
        name="welcome_icon", description="[管理] 自定义标题小图标（留空恢复服务器头像）"
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_icon(self, ctx, url: str = ""):
        url = url.strip()
        if url and not url.lower().startswith(("http://", "https://")):
            await ctx.send(
                "❌ 请提供有效图片链接（http/https），或留空恢复默认。", ephemeral=True
            )
            return
        await self._set_config(ctx.guild.id, "author_icon", url)
        await ctx.send(
            "✅ 已恢复默认（服务器头像）。" if not url else "✅ 标题图标已更新。",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="welcome_thumbnail",
        aliases=["welcome_thumb"],
        description="[管理] 自定义右侧缩略图（留空恢复用户头像）",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_thumbnail(self, ctx, url: str = ""):
        url = url.strip()
        if (
            url
            and url not in ("%avatar%", "%server_avatar%")
            and not url.lower().startswith(("http://", "https://"))
        ):
            await ctx.send(
                "❌ 请提供有效图片链接，或 %avatar% / %server_avatar%，或留空恢复默认。",
                ephemeral=True,
            )
            return
        await self._set_config(ctx.guild.id, "thumbnail_url", url)
        await ctx.send(
            "✅ 已恢复默认（用户头像）。" if not url else "✅ 缩略图已更新。",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="welcome_card", description="[管理] 是否附带图片横幅卡面"
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_card(self, ctx, enabled: bool):
        await self._set_config(ctx.guild.id, "show_card", 1 if enabled else 0)
        await ctx.send(
            f"✅ 图片横幅已{'开启' if enabled else '关闭'}。", ephemeral=True
        )

    @commands.hybrid_command(
        name="welcome_disable", description="[管理] 禁用迎新/道别系统"
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_disable(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM welcome_config WHERE guild_id = ?", (ctx.guild.id,)
            )
            await db.commit()
        await audit(
            self.bot,
            ctx.guild.id,
            "禁用迎新 & 道别系统",
            **{"操作者": ctx.author.mention},
        )
        await ctx.send("✅ 已禁用迎新 & 道别系统。")


async def setup(bot):
    await bot.add_cog(Welcome(bot))
