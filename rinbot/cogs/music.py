# cogs/music.py
# RinBot — 完整音乐播放器模块
# 功能：播放、队列、跳过、暂停/恢复、循环、音量、洗牌、移除、清空、歌单/Spotify 导入、队列存档

import discord
from discord.ext import commands
from discord.ui import View, Button
import yt_dlp
import aiosqlite
import asyncio
import random
import time
import json
import os
from collections import deque
from typing import Literal, Optional
from concurrent.futures import ProcessPoolExecutor


def _ytdl_run(query: str, opts: dict):
    """在独立进程里跑 yt-dlp，避免 CPU 密集解析霸占主进程 GIL 导致交互超时"""
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(query, download=False)

from config import YTDL_OPTIONS, FFMPEG_OPTIONS

try:
    from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
except ImportError:
    SPOTIFY_CLIENT_ID = SPOTIFY_CLIENT_SECRET = ""

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    _SPOTIPY_AVAILABLE = True
except ImportError:
    _SPOTIPY_AVAILABLE = False

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "music.db"
)


class MusicError(Exception):
    """面向用户的可读错误（直接展示给点歌者）"""


class _RestoredUser:
    """从存档恢复时，原点歌者已不在缓存的占位对象"""

    def __init__(self, uid: int, name: str):
        self.id = uid
        self.display_name = name
        self.mention = f"<@{uid}>" if uid else name

        class _A:
            url = None

        self.display_avatar = _A()


class Song:
    """封装一首歌的信息"""

    __slots__ = ("title", "url", "stream_url", "duration", "thumbnail", "requester", "stream_at")

    def __init__(self, title, url, stream_url, duration, thumbnail, requester):
        self.title = title
        self.url = url
        self.stream_url = stream_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.stream_at = time.time() if stream_url else 0.0  # 流地址获取时间，用于判断是否需重新解析

    @staticmethod
    def format_duration(seconds):
        if not seconds:
            return "直播"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def to_dict(self):
        # stream_url 会过期，不存；载入时按 url 重新解析
        return {
            "title": self.title,
            "url": self.url,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "requester_id": getattr(self.requester, "id", 0),
            "requester_name": getattr(self.requester, "display_name", "未知"),
        }


class GuildMusicState:
    """每个服务器独立的音乐状态"""

    MAX_CONSECUTIVE_FAILURES = 3

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
        self.fail_count = 0
        self.idle_task: Optional[asyncio.Task] = None

    def cancel_idle(self):
        if self.idle_task and not self.idle_task.done():
            self.idle_task.cancel()
        self.idle_task = None

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop_mode = "off"
        self.skip_votes.clear()
        self.is_playing = False
        self.fail_count = 0
        self.cancel_idle()


class NowPlayingView(View):
    """正在播放的控制面板 — 单排 5 按钮"""

    def __init__(self, music_cog, ctx, state=None):
        super().__init__(timeout=600)
        self.music_cog = music_cog
        self.ctx = ctx
        self.state = state

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_btn(self, interaction: discord.Interaction, button: Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
        elif vc and vc.is_paused():
            vc.resume()
            button.emoji = "⏸️"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message(
                "❌ 当前没有在播放。", ephemeral=True
            )

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: Button):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭ 已跳过!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "❌ 当前没有在播放。", ephemeral=True
            )

    @discord.ui.button(
        label="循环: 关", emoji="🔁", style=discord.ButtonStyle.secondary
    )
    async def loop_btn(self, interaction: discord.Interaction, button: Button):
        state = self.music_cog._get_state(interaction.guild.id)
        modes = ["off", "single", "queue"]
        labels = {"off": "循环: 关", "single": "单曲循环", "queue": "队列循环"}
        emojis = {"off": "🔁", "single": "🔂", "queue": "🔁"}
        idx = (modes.index(state.loop_mode) + 1) % 3
        state.loop_mode = modes[idx]
        button.label = labels[state.loop_mode]
        button.emoji = emojis[state.loop_mode]
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary)
    async def shuffle_btn(self, interaction: discord.Interaction, button: Button):
        state = self.music_cog._get_state(interaction.guild.id)
        if len(state.queue) < 2:
            await interaction.response.send_message(
                "❌ 队列歌曲不足,无需洗牌。", ephemeral=True
            )
            return
        temp = list(state.queue)
        random.shuffle(temp)
        state.queue = deque(temp)
        await interaction.response.send_message(
            f"🔀 已随机打乱 {len(state.queue)} 首歌!", ephemeral=True
        )

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.secondary)
    async def stop_btn(self, interaction: discord.Interaction, button: Button):
        state = self.music_cog._get_state(interaction.guild.id)
        state.clear()
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
        await interaction.response.send_message(
            "⏹ 已停止播放并清空队列。", ephemeral=True
        )
        self.stop()


class SearchView(View):
    """/search 结果选择菜单，仅发起者可选，60 秒超时"""

    def __init__(self, cog, ctx, results, timeout=60):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.results = results
        self.message = None
        nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        options = []
        for i, r in enumerate(results):
            dur = Song.format_duration(r["duration"])
            desc = f"{r['uploader']} · {dur}" if r["uploader"] else dur
            options.append(discord.SelectOption(
                label=f"{i + 1}. {r['title']}"[:100],
                value=str(i),
                description=desc[:100],
                emoji=nums[i] if i < len(nums) else None,
            ))
        select = discord.ui.Select(placeholder="选择要播放的歌曲…", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("只有发起搜索的人能选择哦。", ephemeral=True)
            return
        idx = int(interaction.data["values"][0])
        await interaction.response.defer()
        for c in self.children:
            c.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass
        vc = await self.cog._ensure_voice(self.ctx)
        if vc:
            song = self.cog._song_from_entry(self.results[idx], self.ctx.author)
            await self.cog._enqueue(self.ctx, vc, [song])
        self.stop()

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class Music(commands.Cog):
    """完整音乐播放器 — 队列 / 循环 / 音量 / 投票跳过"""

    def __init__(self, bot):
        self.bot = bot
        self._states: dict[int, GuildMusicState] = {}
        self._pool = None

    def _get_pool(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=2)
        return self._pool

    def _get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self._states:
            self._states[guild_id] = GuildMusicState(self.bot, guild_id)
        return self._states[guild_id]

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS saved_queues (
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    songs_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (guild_id, name)
                )
            """)
            await db.commit()

    def cog_unload(self):
        for state in self._states.values():
            if state._task:
                state._task.cancel()
        if self._pool:
            self._pool.shutdown(wait=False)

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
            await channel.connect(self_deaf=True)
        return ctx.voice_client

    async def _require_dj(self, ctx) -> bool:
        """控制类命令使用。无配置/管理员/有 DJ 角色 → 通过。"""
        mc = self.bot.get_cog("MusicConfig")
        if not mc:
            return True
        dj_role_id = mc.get_config(ctx.guild.id).get("dj_role", 0)
        if not dj_role_id:
            return True
        if ctx.author.guild_permissions.manage_guild:
            return True
        if any(r.id == dj_role_id for r in ctx.author.roles):
            return True
        await ctx.send("❌ 你没有 DJ 权限,无法使用此指令。", ephemeral=True)
        return False

    def _get_notify_channel(self, ctx) -> discord.TextChannel:
        """返回配置的通知频道,未配置则返回 ctx.channel"""
        mc = self.bot.get_cog("MusicConfig")
        if not mc:
            return ctx.channel
        ch_id = mc.get_config(ctx.guild.id).get("notify_channel", 0)
        if not ch_id:
            return ctx.channel
        ch = ctx.guild.get_channel(ch_id)
        return ch or ctx.channel

    async def _extract_info(self, query: str) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        opts = {**YTDL_OPTIONS, "extract_flat": False}
        try:
            info = await loop.run_in_executor(self._get_pool(), _ytdl_run, query, opts)
        except Exception:
            return None
        if not info:
            return None
        if "entries" in info:
            entries = info["entries"]
            return entries[0] if entries else None
        return info

    def _make_source(self, song: Song, volume: float):
        source = discord.FFmpegPCMAudio(song.stream_url, **FFMPEG_OPTIONS)
        return discord.PCMVolumeTransformer(source, volume=volume)

    def _make_after(self, guild_id: int):
        """生成 vc.play 的 after 回调：处理连续失败并续播下一首"""
        state = self._get_state(guild_id)

        def after_play(error):
            if error:
                print(f"[music] 播放错误 (guild {guild_id}): {error}")
                state.fail_count += 1
                if state.fail_count >= GuildMusicState.MAX_CONSECUTIVE_FAILURES:
                    state.is_playing = False
                    botlog = self.bot.get_cog("BotLog")
                    if botlog:
                        asyncio.run_coroutine_threadsafe(
                            botlog.log(
                                guild_id,
                                "error",
                                "音乐播放连续失败,已停止队列",
                                f"```{str(error)[:500]}```",
                                **{"失败次数": str(state.fail_count)},
                            ),
                            self.bot.loop,
                        )
                    return
            else:
                state.fail_count = 0
            if state.is_playing:
                asyncio.run_coroutine_threadsafe(
                    self._play_next(guild_id), self.bot.loop
                )

        return after_play

    @staticmethod
    def _is_spotify(query: str) -> bool:
        return "open.spotify.com" in query

    @staticmethod
    def _is_playlist_url(query: str) -> bool:
        q = query.lower()
        return "list=" in q or "/playlist" in q or "/sets/" in q or "/album/" in q

    async def _extract_entries(self, query: str) -> list[dict]:
        """统一入口：单曲返回 1 条，歌单/Spotify 返回多条。失败抛 MusicError 或返回 []"""
        if self._is_spotify(query):
            return await self._spotify_to_entries(query)

        if self._is_playlist_url(query):
            loop = asyncio.get_event_loop()

            def _extract():
                opts = {**YTDL_OPTIONS, "noplaylist": False, "extract_flat": "in_playlist"}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                if not info or not info.get("entries"):
                    return []
                out = []
                for e in info["entries"]:
                    if not e:
                        continue
                    url = e.get("url") or ""
                    if not url.startswith("http") and e.get("id"):
                        url = f"https://www.youtube.com/watch?v={e['id']}"
                    if not url:
                        continue
                    out.append({
                        "title": e.get("title", "未知"),
                        "url": url,
                        "duration": e.get("duration"),
                        "thumbnail": e.get("thumbnail"),
                    })
                return out

            try:
                return await loop.run_in_executor(None, _extract)
            except Exception:
                return []

        # 单曲 / 关键词搜索：沿用原逻辑，stream_url 当场拿到可直接开播
        info = await self._extract_info(query)
        if not info:
            return []
        return [{
            "title": info.get("title", "未知"),
            "url": info.get("webpage_url", query),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "stream_url": info.get("url", ""),
        }]

    async def _spotify_to_entries(self, url: str) -> list[dict]:
        if not _SPOTIPY_AVAILABLE:
            raise MusicError("Spotify 支持未安装，请先 `pip install spotipy`。")
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            raise MusicError("Spotify 未配置，请在 config.py 填入 SPOTIFY_CLIENT_ID / SECRET。")

        loop = asyncio.get_event_loop()

        def _fetch():
            sp = spotipy.Spotify(
                auth_manager=SpotifyClientCredentials(
                    client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET
                )
            )
            tracks, default_thumb = [], None
            if "/track/" in url:
                tracks.append(sp.track(url))
            elif "/playlist/" in url:
                res = sp.playlist_items(url, additional_types=("track",))
                while res:
                    tracks += [it["track"] for it in res["items"] if it and it.get("track")]
                    res = sp.next(res) if res.get("next") else None
            elif "/album/" in url:
                alb = sp.album(url)
                imgs = alb.get("images") or []
                default_thumb = imgs[0]["url"] if imgs else None
                res = sp.album_tracks(url)
                while res:
                    tracks += [t for t in res["items"] if t]
                    res = sp.next(res) if res.get("next") else None

            out = []
            for t in tracks:
                if not t:
                    continue
                name = t.get("name", "")
                artists = ", ".join(a["name"] for a in t.get("artists", []) if a.get("name"))
                q = f"{name} {artists}".strip()
                if not q:
                    continue
                imgs = (t.get("album") or {}).get("images") or []
                out.append({
                    "title": q,
                    "url": f"ytsearch1:{q}",  # 播放时再去 YouTube 解析
                    "duration": round(t["duration_ms"] / 1000) if t.get("duration_ms") else None,
                    "thumbnail": imgs[0]["url"] if imgs else default_thumb,
                })
            return out

        try:
            return await loop.run_in_executor(None, _fetch)
        except Exception as e:
            raise MusicError(f"Spotify 解析失败：{e}")

    async def _search_flat(self, query: str, n: int = 5) -> list[dict]:
        """扁平搜索前 n 个候选（不逐个完整解析，快）"""
        loop = asyncio.get_event_loop()
        opts = {**YTDL_OPTIONS, "extract_flat": True, "noplaylist": True}
        try:
            info = await loop.run_in_executor(self._get_pool(), _ytdl_run, f"ytsearch{n}:{query}", opts)
        except Exception:
            return []
        entries = info.get("entries", []) if info else []
        out = []
        for e in entries:
            if not e:
                continue
            vid = e.get("id")
            url = e.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
            if not url:
                continue
            out.append({
                "title": e.get("title", "未知"),
                "url": url,
                "duration": e.get("duration"),
                "thumbnail": e.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg" if vid else None),
                "uploader": e.get("uploader") or e.get("channel") or "",
            })
        return out

    def _song_from_entry(self, e: dict, requester) -> Song:
        return Song(
            title=e.get("title", "未知"),
            url=e.get("url", ""),
            stream_url=e.get("stream_url", ""),
            duration=e.get("duration"),
            thumbnail=e.get("thumbnail"),
            requester=requester,
        )

    def _restore_song(self, d: dict, guild) -> Song:
        rid = d.get("requester_id", 0)
        member = guild.get_member(rid) if rid else None
        return Song(
            title=d.get("title", "未知"),
            url=d.get("url", ""),
            stream_url="",  # 过期，播放时重新解析
            duration=d.get("duration"),
            thumbnail=d.get("thumbnail"),
            requester=member or _RestoredUser(rid, d.get("requester_name", "未知")),
        )

    async def _play_next(self, guild_id: int):
        """播放队列中的下一首"""
        state = self._get_state(guild_id)
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return

        vc = guild.voice_client
        state.skip_votes.clear()
        state.cancel_idle()

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
            state.idle_task = asyncio.create_task(self._idle_disconnect(guild_id))
            return

        # 流地址会过期；仅当为空或已超过 30 分钟才重新解析
        # （刚入队的歌地址还新鲜，避免「第一首被提取两次」的多余等待）
        STREAM_TTL = 1800
        if not state.current.stream_url or (time.time() - getattr(state.current, "stream_at", 0)) > STREAM_TTL:
            info = await self._extract_info(state.current.url)
            if info:
                state.current.stream_url = info.get("url", state.current.stream_url)
                state.current.stream_at = time.time()

        state.is_playing = True
        source = self._make_source(state.current, state.volume)
        vc.play(source, after=self._make_after(guild_id))

    async def _idle_disconnect(self, guild_id: int):
        """空闲 3 分钟自动断开,可被新的 /play 取消"""
        try:
            await asyncio.sleep(180)
            state = self._get_state(guild_id)
            guild = self.bot.get_guild(guild_id)
            if not state.is_playing and guild and guild.voice_client:
                await guild.voice_client.disconnect()
        except asyncio.CancelledError:
            pass

    # ─── 指令:play ───

    @commands.hybrid_command(
        name="play",
        aliases=["p"],
        description="播放音乐（歌名/链接/歌单/Spotify），支持队列",
    )
    async def play(self, ctx, *, query: str):
        await ctx.defer()
        vc = await self._ensure_voice(ctx)
        if not vc:
            return
        try:
            entries = await self._extract_entries(query)
        except MusicError as e:
            await ctx.send(f"❌ {e}")
            return
        if not entries:
            await ctx.send("❌ 找不到相关音乐，请换个关键词或检查链接。")
            return
        songs = [self._song_from_entry(e, ctx.author) for e in entries]
        await self._enqueue(ctx, vc, songs)

    async def _enqueue(self, ctx, vc, songs):
        state = self._get_state(ctx.guild.id)
        is_list = len(songs) > 1
        playing = state.is_playing or vc.is_playing() or vc.is_paused()

        if playing:
            state.queue.extend(songs)
            if is_list:
                embed = discord.Embed(
                    title="📋 歌单已加入队列",
                    description=f"成功添加 **{len(songs)}** 首歌曲。",
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"请求者: {ctx.author.display_name}")
            else:
                song = songs[0]
                embed = discord.Embed(
                    title="📋 已加入队列",
                    description=f"**{song.title}**\n⏱ 时长: {Song.format_duration(song.duration)}",
                    color=discord.Color.blue(),
                )
                embed.set_footer(
                    text=f"队列位置: #{len(state.queue)} | 请求者: {ctx.author.display_name}"
                )
                if song.thumbnail:
                    embed.set_thumbnail(url=song.thumbnail)
            await ctx.send(embed=embed)
            return

        # 空闲：第一首立即播放（惰性条目开播前先解析出 stream_url），其余进队列
        first = songs[0]
        state.cancel_idle()
        if not first.stream_url:
            info = await self._extract_info(first.url)
            if info:
                first.stream_url = info.get("url", "")
                first.stream_at = time.time()
                first.title = info.get("title", first.title)
                first.duration = first.duration or info.get("duration")
                first.thumbnail = first.thumbnail or info.get("thumbnail")
                first.url = info.get("webpage_url", first.url)
        if not first.stream_url:
            await ctx.send("❌ 第一首歌解析失败。")
            return

        state.queue.extend(songs[1:])
        state.current = first
        state.is_playing = True
        source = self._make_source(first, state.volume)
        vc.play(source, after=self._make_after(ctx.guild.id))
        await self._send_now_playing(ctx, first, state)
        if is_list:
            await ctx.send(f"📋 已将歌单中 **{len(songs)}** 首歌加入播放！")

    @commands.hybrid_command(name="search", aliases=["sc"], description="搜索歌曲并从结果中选择播放")
    async def search(self, ctx, *, query: str):
        await ctx.defer()
        results = await self._search_flat(query, 5)
        if not results:
            await ctx.send("❌ 没找到相关歌曲，换个关键词试试。")
            return
        embeds = []
        for i, r in enumerate(results, 1):
            dur = Song.format_duration(r["duration"])
            desc = f"👤 {r['uploader']}　⏱ {dur}" if r["uploader"] else f"⏱ {dur}"
            e = discord.Embed(title=f"{i}. {r['title'][:250]}", url=r["url"], description=desc, color=0xFFB6C1)
            if r.get("thumbnail"):
                e.set_thumbnail(url=r["thumbnail"])
            embeds.append(e)
        embeds[0].set_author(name=f"🔍 “{query}” 的搜索结果")
        embeds[-1].set_footer(text="60 秒内从下方菜单选择要播放的歌曲")
        view = SearchView(self, ctx, results)
        view.message = await ctx.send(embeds=embeds, view=view)

    async def _send_now_playing(self, ctx, song: Song, state: GuildMusicState):
        embed = discord.Embed(color=0xFFB6C1)
        embed.set_author(
            name="正在播放 ♪",
            icon_url=self.bot.user.display_avatar.url,
        )
        title_display = song.title if len(song.title) <= 60 else song.title[:59] + "…"
        embed.title = title_display
        embed.url = song.url

        if song.thumbnail:
            embed.set_image(url=song.thumbnail)

        loop_labels = {"off": "❌ 关闭", "single": "🔂 单曲", "queue": "🔁 队列"}
        embed.add_field(
            name="⏱ 时长", value=Song.format_duration(song.duration), inline=True
        )
        embed.add_field(
            name="🔊 音量", value=f"{int(state.volume * 100)}%", inline=True
        )
        embed.add_field(name="🔁 循环", value=loop_labels[state.loop_mode], inline=True)

        if state.queue:
            next_song = state.queue[0]
            next_title = (
                next_song.title
                if len(next_song.title) <= 50
                else next_song.title[:49] + "…"
            )
            embed.add_field(
                name="⏭ 接下来",
                value=f"**{next_title}**\n*请求者: {next_song.requester.display_name}*",
                inline=False,
            )

        embed.set_footer(
            text=f"🌸 由 {song.requester.display_name} 点歌 · 小凛音乐 ♪",
            icon_url=song.requester.display_avatar.url,
        )

        view = NowPlayingView(self, ctx, state)
        notify_ch = self._get_notify_channel(ctx)
        await notify_ch.send(embed=embed, view=view)
        if notify_ch.id != ctx.channel.id:
            await ctx.send(f"🎵 已开始播放 **{song.title}** → {notify_ch.mention}")

    # ─── 指令：skip ───

    @commands.hybrid_command(
        name="skip", aliases=["s", "next"], description="跳过当前歌曲（或投票跳过）"
    )
    async def skip(self, ctx):
        if not await self._require_dj(ctx):
            return
        vc = ctx.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await ctx.send("❌ 当前没有在播放。")
            return

        state = self._get_state(ctx.guild.id)

        # 如果是点歌者或管理员，直接跳
        if state.current and (
            ctx.author == state.current.requester
            or ctx.author.guild_permissions.manage_guild
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
        if not await self._require_dj(ctx):
            return
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send("⏸ 已暂停。")
        else:
            await ctx.send("❌ 当前没有在播放。")

    @commands.hybrid_command(name="resume", aliases=["unpause"], description="恢复播放")
    async def resume(self, ctx):
        if not await self._require_dj(ctx):
            return
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send("▶ 已恢复播放！")
        else:
            await ctx.send("❌ 没有暂停的歌曲。")

    # ─── 指令：stop ───

    @commands.hybrid_command(
        name="stop",
        aliases=["dc", "disconnect", "leave"],
        description="停止播放、清空队列并离开",
    )
    async def stop(self, ctx):
        if not await self._require_dj(ctx):
            return
        state = self._get_state(ctx.guild.id)
        state.clear()
        if ctx.voice_client:
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await ctx.send("⏹ 已停止播放并离开频道。")
        else:
            await ctx.send("❌ 我不在语音频道里。")

    # ─── 指令：nowplaying ───

    @commands.hybrid_command(
        name="nowplaying", aliases=["np"], description="查看正在播放的歌曲"
    )
    async def nowplaying(self, ctx):
        state = self._get_state(ctx.guild.id)
        if not state.current:
            await ctx.send("❌ 当前没有在播放。")
            return
        await self._send_now_playing(ctx, state.current, state)

    # ─── 指令：queue ───

    @commands.hybrid_command(
        name="queue", aliases=["q", "list"], description="查看播放队列"
    )
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
                lines.append(
                    f"`{i}.` **{song.title}** [{Song.format_duration(song.duration)}] — {song.requester.mention}"
                )
            embed.add_field(
                name=f"队列 (第 {page}/{pages} 页)",
                value="\n".join(lines),
                inline=False,
            )

        total_dur = sum(s.duration or 0 for s in state.queue)
        if state.current and state.current.duration:
            total_dur += state.current.duration
        loop_labels = {"off": "关闭", "single": "🔂 单曲", "queue": "🔁 队列"}
        embed.set_footer(
            text=f"共 {len(state.queue)} 首待播放 | 总时长: {Song.format_duration(total_dur)} | 循环: {loop_labels[state.loop_mode]}"
        )

        await ctx.send(embed=embed)

    # ─── 指令：remove ───

    @commands.hybrid_command(
        name="remove", aliases=["rm"], description="从队列中移除指定位置的歌曲"
    )
    async def remove(self, ctx, position: int):
        if not await self._require_dj(ctx):
            return
        state = self._get_state(ctx.guild.id)
        if position < 1 or position > len(state.queue):
            await ctx.send(f"❌ 无效的位置。队列长度为 {len(state.queue)}。")
            return
        removed = list(state.queue)[position - 1]
        del state.queue[position - 1]
        await ctx.send(f"🗑 已移除: **{removed.title}**")

    # ─── 指令：clear ───

    @commands.hybrid_command(
        name="clear", aliases=["cls"], description="清空播放队列（不影响当前播放）"
    )
    async def clear_queue(self, ctx):
        if not await self._require_dj(ctx):
            return
        state = self._get_state(ctx.guild.id)
        count = len(state.queue)
        state.queue.clear()
        await ctx.send(f"🗑 已清空队列（{count} 首歌曲）。")

    # ─── 指令：shuffle ───

    @commands.hybrid_command(name="shuffle", description="随机打乱队列顺序")
    async def shuffle(self, ctx):
        if not await self._require_dj(ctx):
            return
        state = self._get_state(ctx.guild.id)
        if len(state.queue) < 2:
            await ctx.send("❌ 队列中歌曲不足，无需洗牌。")
            return
        temp = list(state.queue)
        random.shuffle(temp)
        state.queue = deque(temp)
        await ctx.send(f"🔀 已随机打乱 {len(state.queue)} 首歌曲！")

    # ─── 指令：loop ───

    @commands.hybrid_command(
        name="loop", aliases=["repeat"], description="设置循环模式"
    )
    async def loop(self, ctx, mode: Literal["off", "single", "queue"] = None):
        if not await self._require_dj(ctx):
            return
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

    @commands.hybrid_command(
        name="volume", aliases=["vol"], description="调整音量 (0-200)"
    )
    async def volume(self, ctx, level: int = None):
        state = self._get_state(ctx.guild.id)
        if level is None:
            await ctx.send(f"🔊 当前音量: **{int(state.volume * 100)}%**")
            return
        if not await self._require_dj(ctx):
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
        if not await self._require_dj(ctx):
            return
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

    # ─── 指令：队列存档 ───

    @commands.hybrid_command(
        name="saveq", aliases=["savequeue"], description="保存当前队列为存档（可命名）"
    )
    async def saveq(self, ctx, *, name: str = "default"):
        state = self._get_state(ctx.guild.id)
        songs = ([state.current] if state.current else []) + list(state.queue)
        if not songs:
            await ctx.send("❌ 队列为空，没有可保存的内容。")
            return
        name = name.strip()[:50]
        songs = songs[:500]  # 单存档上限保护
        data = json.dumps([s.to_dict() for s in songs], ensure_ascii=False)

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM saved_queues WHERE guild_id=?", (ctx.guild.id,)
            )
            count = (await cur.fetchone())[0]
            cur = await db.execute(
                "SELECT 1 FROM saved_queues WHERE guild_id=? AND name=?",
                (ctx.guild.id, name),
            )
            exists = await cur.fetchone()
            if count >= 25 and not exists:
                await ctx.send("❌ 每个服务器最多保存 25 个队列存档。")
                return
            await db.execute(
                "INSERT OR REPLACE INTO saved_queues (guild_id, name, songs_json, created_at) VALUES (?,?,?,?)",
                (ctx.guild.id, name, data, time.time()),
            )
            await db.commit()
        await ctx.send(f"💾 已保存队列存档 **{name}**（{len(songs)} 首）。")

    @commands.hybrid_command(
        name="loadq", aliases=["loadqueue"], description="载入已保存的队列存档"
    )
    async def loadq(self, ctx, *, name: str = "default"):
        if not await self._require_dj(ctx):
            return
        name = name.strip()[:50]
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT songs_json FROM saved_queues WHERE guild_id=? AND name=?",
                (ctx.guild.id, name),
            )
            row = await cur.fetchone()
        if not row:
            await ctx.send(f"❌ 找不到名为 **{name}** 的存档，用 `/queues` 查看列表。")
            return
        try:
            items = json.loads(row[0])
        except Exception:
            await ctx.send("❌ 存档数据已损坏。")
            return

        songs = [self._restore_song(d, ctx.guild) for d in items]
        if not songs:
            await ctx.send("❌ 存档为空。")
            return

        state = self._get_state(ctx.guild.id)
        vc = await self._ensure_voice(ctx)
        if not vc:
            return

        if state.is_playing or vc.is_playing() or vc.is_paused():
            state.queue.extend(songs)
            await ctx.send(f"💿 已将存档 **{name}** 的 {len(songs)} 首歌加入队列。")
            return

        state.queue.extend(songs)
        state.cancel_idle()
        await ctx.send(f"💿 正在载入存档 **{name}**（{len(songs)} 首）…")
        await self._play_next(ctx.guild.id)

    @commands.hybrid_command(
        name="queues", aliases=["savedqueues", "qlist"], description="查看已保存的队列存档"
    )
    async def queues(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT name, songs_json, created_at FROM saved_queues WHERE guild_id=? ORDER BY created_at DESC",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            await ctx.send("📭 还没有保存任何队列存档。用 `/saveq` 保存当前队列。")
            return
        embed = discord.Embed(title="💾 已保存的队列存档", color=discord.Color.blurple())
        for name, sj, _ in rows[:25]:
            try:
                n = len(json.loads(sj))
            except Exception:
                n = "?"
            embed.add_field(name=name, value=f"{n} 首", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="delqueue", aliases=["delq"], description="删除一个队列存档")
    async def delqueue(self, ctx, *, name: str):
        if not await self._require_dj(ctx):
            return
        name = name.strip()[:50]
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "DELETE FROM saved_queues WHERE guild_id=? AND name=?",
                (ctx.guild.id, name),
            )
            await db.commit()
        if cur.rowcount:
            await ctx.send(f"🗑 已删除存档 **{name}**。")
        else:
            await ctx.send(f"❌ 找不到名为 **{name}** 的存档。")

    # ─── 指令：join ───

    @commands.hybrid_command(
        name="join", aliases=["j", "connect"], description="让机器人加入你的语音频道"
    )
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
            await destination.connect(self_deaf=True)
            await ctx.send(f"👋 已加入语音频道: **{destination.name}**")

    # ─── 自动断开（所有人离开语音时）───

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        vc = member.guild.voice_client
        if vc and before.channel == vc.channel:
            # 等待 1 秒，避免因用户短暂断线重连触发误判
            await asyncio.sleep(1)
            if not vc.is_connected():
                return
            # 检查频道里除了 bot 还有没有人
            real_members = [m for m in vc.channel.members if not m.bot]
            if len(real_members) == 0:
                state = self._get_state(member.guild.id)
                state.clear()
                vc.stop()
                await vc.disconnect()


async def setup(bot):
    await bot.add_cog(Music(bot))