# cogs/music.py
# RinBot — 完整音乐播放器模块
# 功能：播放、队列、跳过、暂停/恢复、循环、音量、洗牌、正在播放、移除、清空队列

import discord
from discord.ext import commands
from discord.ui import View, Button
import yt_dlp
import asyncio
import random
import time
from collections import deque
from typing import Literal, Optional

from config import YTDL_OPTIONS, FFMPEG_OPTIONS


class Song:
    """封装一首歌的信息"""
    __slots__ = ("title", "url", "stream_url", "duration", "thumbnail", "requester")

    def __init__(self, title, url, stream_url, duration, thumbnail, requester):
        self.title = title
        self.url = url
        self.stream_url = stream_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester

    @staticmethod
    def format_duration(seconds):
        if not seconds:
            return "直播"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class GuildMusicState:
    """每个服务器独立的音乐状态"""

    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.queue: deque[Song] = deque()
        self.current: Optional[Song] = None
        self.loop_mode = "off"  # off / single / queue
        self.volume = 0.5
        self.is_playing = False
        self.skip_votes: set[int] = set()
        self._task: Optional[asyncio.Task] = None

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop_mode = "off"
        self.skip_votes.clear()


class NowPlayingView(View):
    """正在播放的控制面板"""

    def __init__(self, music_cog, ctx):
        super().__init__(timeout=300)
        self.music_cog = music_cog
        self.ctx = ctx

    @discord.ui.button(label="⏸ 暂停", style=discord.ButtonStyle.secondary)
    async def pause_btn(self, interaction: discord.Interaction, button: Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            button.label = "▶ 恢复"
            button.style = discord.ButtonStyle.success
        elif vc and vc.is_paused():
            vc.resume()
            button.label = "⏸ 暂停"
            button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="⏭ 跳过", style=discord.ButtonStyle.primary)
    async def skip_btn(self, interaction: discord.Interaction, button: Button):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭ 已跳过当前歌曲！", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 当前没有在播放。", ephemeral=True)

    @discord.ui.button(label="⏹ 停止", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: Button):
        state = self.music_cog._get_state(interaction.guild.id)
        state.clear()
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
        await interaction.response.send_message("⏹ 已停止播放并清空队列。", ephemeral=True)
        self.stop()

    @discord.ui.button(label="🔁 循环", style=discord.ButtonStyle.secondary)
    async def loop_btn(self, interaction: discord.Interaction, button: Button):
        state = self.music_cog._get_state(interaction.guild.id)
        modes = ["off", "single", "queue"]
        labels = {"off": "🔁 循环: 关", "single": "🔂 单曲循环", "queue": "🔁 队列循环"}
        idx = (modes.index(state.loop_mode) + 1) % 3
        state.loop_mode = modes[idx]
        button.label = labels[state.loop_mode]
        await interaction.response.edit_message(view=self)


class Music(commands.Cog):
    """完整音乐播放器 — 队列 / 循环 / 音量 / 投票跳过"""

    def __init__(self, bot):
        self.bot = bot
        self._states: dict[int, GuildMusicState] = {}

    def _get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self._states:
            self._states[guild_id] = GuildMusicState(self.bot, guild_id)
        return self._states[guild_id]

    def cog_unload(self):
        for state in self._states.values():
            if state._task:
                state._task.cancel()

    # ─── 内部工具 ───

    async def _ensure_voice(self, ctx) -> Optional[discord.VoiceClient]:
        """确保用户在语音频道且 bot 已连接"""
        if not ctx.author.voice:
            await ctx.send("❌ 你必须先加入一个语音频道！")
            return None
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            if ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        return ctx.voice_client

    async def _extract_info(self, query: str) -> Optional[dict]:
        """用 yt-dlp 提取音频信息（异步包装）"""
        loop = asyncio.get_event_loop()
        opts = {**YTDL_OPTIONS, 'extract_flat': False}

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if "entries" in info:
                    return info["entries"][0] if info["entries"] else None
                return info

        try:
            return await loop.run_in_executor(None, _extract)
        except Exception:
            return None

    def _make_source(self, song: Song, volume: float):
        source = discord.FFmpegPCMAudio(song.stream_url, **FFMPEG_OPTIONS)
        return discord.PCMVolumeTransformer(source, volume=volume)

    async def _play_next(self, guild_id: int):
        """播放队列中的下一首"""
        state = self._get_state(guild_id)
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return

        vc = guild.voice_client
        state.skip_votes.clear()

        # 循环逻辑
        if state.loop_mode == "single" and state.current:
            pass  # current 不变
        elif state.loop_mode == "queue" and state.current:
            state.queue.append(state.current)
            state.current = state.queue.popleft() if state.queue else None
        else:
            state.current = state.queue.popleft() if state.queue else None

        if not state.current:
            state.is_playing = False
            # 3 分钟无歌自动断开
            await asyncio.sleep(180)
            if not state.is_playing and guild.voice_client:
                await guild.voice_client.disconnect()
            return

        # 重新获取流媒体 URL（旧 URL 可能过期）
        info = await self._extract_info(state.current.url)
        if info:
            state.current.stream_url = info.get("url", state.current.stream_url)

        state.is_playing = True
        source = self._make_source(state.current, state.volume)

        def after_play(error):
            if error:
                print(f"播放错误: {error}")
            asyncio.run_coroutine_threadsafe(self._play_next(guild_id), self.bot.loop)

        vc.play(source, after=after_play)

    # ─── 指令：play ───

    @commands.hybrid_command(name="play", aliases=["p"], description="播放音乐（歌名或链接），支持队列")
    async def play(self, ctx, *, query: str):
        await ctx.defer()
        vc = await self._ensure_voice(ctx)
        if not vc:
            return

        state = self._get_state(ctx.guild.id)

        info = await self._extract_info(query)
        if not info:
            await ctx.send("❌ 找不到相关音乐，请换个关键词试试。")
            return

        song = Song(
            title=info.get("title", "未知"),
            url=info.get("webpage_url", query),
            stream_url=info.get("url", ""),
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            requester=ctx.author,
        )

        if state.is_playing or vc.is_playing() or vc.is_paused():
            state.queue.append(song)
            embed = discord.Embed(
                title="📋 已加入队列",
                description=f"**{song.title}**\n⏱ 时长: {Song.format_duration(song.duration)}",
                color=discord.Color.blue(),
            )
            embed.set_footer(text=f"队列位置: #{len(state.queue)} | 请求者: {ctx.author.display_name}")
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            await ctx.send(embed=embed)
        else:
            state.current = song
            state.is_playing = True
            source = self._make_source(song, state.volume)

            def after_play(error):
                if error:
                    print(f"播放错误: {error}")
                asyncio.run_coroutine_threadsafe(self._play_next(ctx.guild.id), self.bot.loop)

            vc.play(source, after=after_play)
            await self._send_now_playing(ctx, song, state)

    async def _send_now_playing(self, ctx, song: Song, state: GuildMusicState):
        embed = discord.Embed(
            title="🎵 正在播放",
            description=f"**[{song.title}]({song.url})**",
            color=discord.Color.pink(),
        )
        embed.add_field(name="⏱ 时长", value=Song.format_duration(song.duration), inline=True)
        embed.add_field(name="🔊 音量", value=f"{int(state.volume * 100)}%", inline=True)
        loop_labels = {"off": "关闭", "single": "单曲循环", "queue": "队列循环"}
        embed.add_field(name="🔁 循环", value=loop_labels[state.loop_mode], inline=True)
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        embed.set_footer(text=f"请求者: {song.requester.display_name}", icon_url=song.requester.display_avatar.url)

        view = NowPlayingView(self, ctx)
        await ctx.send(embed=embed, view=view)

    # ─── 指令：skip ───

    @commands.hybrid_command(name="skip", aliases=["s", "next"], description="跳过当前歌曲（或投票跳过）")
    async def skip(self, ctx):
        vc = ctx.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await ctx.send("❌ 当前没有在播放。")
            return

        state = self._get_state(ctx.guild.id)

        # 如果是点歌者或管理员，直接跳
        if (
            state.current
            and (ctx.author == state.current.requester or ctx.author.guild_permissions.manage_guild)
        ):
            vc.stop()
            await ctx.send("⏭ 已跳过！")
            return

        # 否则需要投票
        state.skip_votes.add(ctx.author.id)
        listeners = len([m for m in vc.channel.members if not m.bot])
        needed = max(2, listeners // 2)

        if len(state.skip_votes) >= needed:
            vc.stop()
            await ctx.send("⏭ 投票通过，已跳过！")
        else:
            await ctx.send(f"🗳 跳过投票: {len(state.skip_votes)}/{needed}")

    # ─── 指令：pause / resume ───

    @commands.hybrid_command(name="pause", description="暂停播放")
    async def pause(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send("⏸ 已暂停。")
        else:
            await ctx.send("❌ 当前没有在播放。")

    @commands.hybrid_command(name="resume", aliases=["unpause"], description="恢复播放")
    async def resume(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send("▶ 已恢复播放！")
        else:
            await ctx.send("❌ 没有暂停的歌曲。")

    # ─── 指令：stop ───

    @commands.hybrid_command(name="stop", aliases=["dc", "disconnect", "leave"], description="停止播放、清空队列并离开")
    async def stop(self, ctx):
        state = self._get_state(ctx.guild.id)
        state.clear()
        if ctx.voice_client:
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await ctx.send("⏹ 已停止播放并离开频道。")
        else:
            await ctx.send("❌ 我不在语音频道里。")

    # ─── 指令：nowplaying ───

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="查看正在播放的歌曲")
    async def nowplaying(self, ctx):
        state = self._get_state(ctx.guild.id)
        if not state.current:
            await ctx.send("❌ 当前没有在播放。")
            return
        await self._send_now_playing(ctx, state.current, state)

    # ─── 指令：queue ───

    @commands.hybrid_command(name="queue", aliases=["q", "list"], description="查看播放队列")
    async def queue(self, ctx, page: int = 1):
        state = self._get_state(ctx.guild.id)

        if not state.current and not state.queue:
            await ctx.send("📭 队列是空的，用 `/play` 来点歌吧！")
            return

        items_per_page = 10
        pages = max(1, (len(state.queue) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, pages))

        embed = discord.Embed(title="📋 播放队列", color=discord.Color.blurple())

        if state.current:
            embed.add_field(
                name="🎵 正在播放",
                value=f"**{state.current.title}** [{Song.format_duration(state.current.duration)}]\n请求者: {state.current.requester.mention}",
                inline=False,
            )

        if state.queue:
            start = (page - 1) * items_per_page
            end = start + items_per_page
            lines = []
            for i, song in enumerate(list(state.queue)[start:end], start=start + 1):
                lines.append(f"`{i}.` **{song.title}** [{Song.format_duration(song.duration)}] — {song.requester.mention}")
            embed.add_field(name=f"队列 (第 {page}/{pages} 页)", value="\n".join(lines), inline=False)

        total_dur = sum(s.duration or 0 for s in state.queue)
        if state.current and state.current.duration:
            total_dur += state.current.duration
        loop_labels = {"off": "关闭", "single": "🔂 单曲", "queue": "🔁 队列"}
        embed.set_footer(text=f"共 {len(state.queue)} 首待播放 | 总时长: {Song.format_duration(total_dur)} | 循环: {loop_labels[state.loop_mode]}")

        await ctx.send(embed=embed)

    # ─── 指令：remove ───

    @commands.hybrid_command(name="remove", aliases=["rm"], description="从队列中移除指定位置的歌曲")
    async def remove(self, ctx, position: int):
        state = self._get_state(ctx.guild.id)
        if position < 1 or position > len(state.queue):
            await ctx.send(f"❌ 无效的位置。队列长度为 {len(state.queue)}。")
            return
        removed = list(state.queue)[position - 1]
        del state.queue[position - 1]
        await ctx.send(f"🗑 已移除: **{removed.title}**")

    # ─── 指令：clear ───

    @commands.hybrid_command(name="clear", aliases=["cls"], description="清空播放队列（不影响当前播放）")
    async def clear_queue(self, ctx):
        state = self._get_state(ctx.guild.id)
        count = len(state.queue)
        state.queue.clear()
        await ctx.send(f"🗑 已清空队列（{count} 首歌曲）。")

    # ─── 指令：shuffle ───

    @commands.hybrid_command(name="shuffle", description="随机打乱队列顺序")
    async def shuffle(self, ctx):
        state = self._get_state(ctx.guild.id)
        if len(state.queue) < 2:
            await ctx.send("❌ 队列中歌曲不足，无需洗牌。")
            return
        temp = list(state.queue)
        random.shuffle(temp)
        state.queue = deque(temp)
        await ctx.send(f"🔀 已随机打乱 {len(state.queue)} 首歌曲！")

    # ─── 指令：loop ───

    @commands.hybrid_command(name="loop", aliases=["repeat"], description="设置循环模式")
    async def loop(self, ctx, mode: Literal["off", "single", "queue"] = None):
        state = self._get_state(ctx.guild.id)
        if mode is None:
            modes = ["off", "single", "queue"]
            idx = (modes.index(state.loop_mode) + 1) % 3
            state.loop_mode = modes[idx]
        else:
            state.loop_mode = mode
        labels = {"off": "🔁 关闭循环", "single": "🔂 单曲循环", "queue": "🔁 队列循环"}
        await ctx.send(f"循环模式已设为: **{labels[state.loop_mode]}**")

    # ─── 指令：volume ───

    @commands.hybrid_command(name="volume", aliases=["vol"], description="调整音量 (0-200)")
    async def volume(self, ctx, level: int = None):
        state = self._get_state(ctx.guild.id)
        if level is None:
            await ctx.send(f"🔊 当前音量: **{int(state.volume * 100)}%**")
            return
        if level < 0 or level > 200:
            await ctx.send("❌ 音量范围: 0-200")
            return
        state.volume = level / 100
        vc = ctx.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = state.volume
        await ctx.send(f"🔊 音量已调至: **{level}%**")

    # ─── 指令：move ───

    @commands.hybrid_command(name="move", description="移动队列中的歌曲位置")
    async def move(self, ctx, from_pos: int, to_pos: int):
        state = self._get_state(ctx.guild.id)
        q = state.queue
        if from_pos < 1 or from_pos > len(q) or to_pos < 1 or to_pos > len(q):
            await ctx.send(f"❌ 无效位置。队列长度为 {len(q)}。")
            return
        temp = list(q)
        song = temp.pop(from_pos - 1)
        temp.insert(to_pos - 1, song)
        state.queue = deque(temp)
        await ctx.send(f"✅ 已将 **{song.title}** 移动到位置 #{to_pos}")

    # ─── 指令：join ───

    @commands.hybrid_command(name="join", aliases=["j", "connect"], description="让机器人加入你的语音频道")
    async def join(self, ctx):
        if not ctx.author.voice:
            await ctx.send("❌ 你必须先加入一个语音频道！")
            return
        await ctx.defer()
        destination = ctx.author.voice.channel
        if ctx.voice_client:
            if ctx.voice_client.channel.id == destination.id:
                await ctx.send("✅ 我已经在你的频道里了。")
            else:
                old = ctx.voice_client.channel.name
                await ctx.voice_client.move_to(destination)
                await ctx.send(f"➡️ 已从 {old} 移动到 **{destination.name}**")
        else:
            await destination.connect()
            await ctx.send(f"👋 已加入语音频道: **{destination.name}**")

    # ─── 自动断开（所有人离开语音时）───

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        vc = member.guild.voice_client
        if vc and before.channel == vc.channel:
            # 检查频道里除了 bot 还有没有人
            real_members = [m for m in vc.channel.members if not m.bot]
            if len(real_members) == 0:
                state = self._get_state(member.guild.id)
                state.clear()
                vc.stop()
                await vc.disconnect()


async def setup(bot):
    await bot.add_cog(Music(bot))
