# cogs/_messages.py
# 给其他 cog 用的消息工具：按共用模板生成 embed，统一私密发送和拦截提示文案

from typing import NamedTuple, Optional

import discord

from rincore import embeds

PREFIX_PRIVATE_SECONDS = 15  # 前缀指令没法私密回复，提示过这么久自动删除


class Notice(NamedTuple):
    kind: str
    title: str
    description: Optional[str] = None


def embed(kind: str, title: Optional[str] = None, description: Optional[str] = None, **kw) -> discord.Embed:
    """按共用模板生成 discord.Embed；参数同 rincore.embeds.build。"""
    return discord.Embed.from_dict(embeds.build(kind, title, description, **kw))


def _as_text(e: discord.Embed) -> str:
    return f"**{e.title}**\n{e.description}" if e.description else f"**{e.title}**"


async def send(target, embed: discord.Embed, *, private: bool = False, view=None) -> None:
    """发到指令上下文或交互；private=True 时斜杠和交互私密回复，前缀指令过一会儿自动删除。"""
    kwargs = {"view": view} if view is not None else {}
    try:
        if hasattr(target, "response"):
            if target.response.is_done():
                await target.followup.send(embed=embed, ephemeral=private, **kwargs)
            else:
                await target.response.send_message(embed=embed, ephemeral=private, **kwargs)
            return
        prefix = target.interaction is None
        if private and prefix:
            kwargs["delete_after"] = PREFIX_PRIVATE_SECONDS
        # 前缀指令在没有「嵌入链接」权限的频道里发 embed 会失败，退回纯文字
        if prefix and target.guild is not None and not target.channel.permissions_for(target.me).embed_links:
            await target.send(_as_text(embed), **kwargs)
            return
        await target.send(embed=embed, ephemeral=private, **kwargs)
    except discord.HTTPException:
        pass


async def send_notice(target, notice: Notice) -> None:
    """私密发出一条提示（报错、拦截、冷却等）。"""
    await send(target, embed(notice.kind, notice.title, notice.description), private=True)


def block_notice(block, *, component: bool = False) -> Optional[Notice]:
    """维护、停用、黑名单拦截的提示；指令被黑名单拦下时不回复。"""
    if block.kind == "maintenance":
        return Notice("warning", "小凛正在维护", block.text or "暂时用不了，请稍后再试。")
    if block.kind == "disabled":
        return Notice("warning", "这条指令已停用", "机器人主人暂时关闭了这条指令。")
    if component:
        return Notice("error", "你现在不能使用这个功能")
    return None
