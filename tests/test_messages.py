import ast
import asyncio
import os
from types import SimpleNamespace

import discord

from _messages import Notice, block_notice, embed, send, send_notice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Recorder:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error


def _ctx(slash=False, embed_links=True, guild=True, error=None):
    perms = SimpleNamespace(embed_links=embed_links)
    return SimpleNamespace(
        interaction=object() if slash else None,
        guild=object() if guild else None,
        me=object(),
        channel=SimpleNamespace(permissions_for=lambda member: perms),
        send=_Recorder(error),
    )


def _interaction(done=False):
    return SimpleNamespace(
        response=SimpleNamespace(is_done=lambda: done, send_message=_Recorder()),
        followup=SimpleNamespace(send=_Recorder()),
    )


def test_embed_converts_template():
    e = embed("success", "完成", fields=[("成员", "<@1>")])
    assert isinstance(e, discord.Embed)
    assert e.color.value == 0x3BA55D
    assert e.title == "完成"
    assert e.fields[0].name == "成员"


def test_private_slash_reply_is_ephemeral():
    ctx = _ctx(slash=True)
    asyncio.run(send(ctx, embed("info", "t"), private=True))
    (args, kwargs), = ctx.send.calls
    assert kwargs["ephemeral"] is True and "delete_after" not in kwargs
    assert kwargs["embed"].title == "t"


def test_private_prefix_reply_deletes_after_15s():
    ctx = _ctx()
    asyncio.run(send(ctx, embed("info", "t"), private=True))
    assert ctx.send.calls[0][1]["delete_after"] == 15


def test_public_prefix_reply_stays():
    ctx = _ctx()
    asyncio.run(send(ctx, embed("info", "t")))
    assert "delete_after" not in ctx.send.calls[0][1]


def test_prefix_without_embed_links_falls_back_to_text():
    ctx = _ctx(embed_links=False)
    notice = Notice("error", "小凛缺少「嵌入链接」权限", "请服务器管理员打开。")
    asyncio.run(send_notice(ctx, notice))
    (args, kwargs), = ctx.send.calls
    assert args == ("**小凛缺少「嵌入链接」权限**\n请服务器管理员打开。",)
    assert "embed" not in kwargs
    assert kwargs["delete_after"] == 15


def test_text_fallback_without_description():
    ctx = _ctx(embed_links=False)
    asyncio.run(send_notice(ctx, Notice("error", "这条指令只能在服务器里用")))
    assert ctx.send.calls[0][0] == ("**这条指令只能在服务器里用**",)


def test_direct_messages_keep_embeds():
    ctx = _ctx(embed_links=False, guild=False)
    asyncio.run(send(ctx, embed("info", "t")))
    assert "embed" in ctx.send.calls[0][1]


def test_fresh_interaction_uses_response():
    i = _interaction()
    asyncio.run(send(i, embed("info", "t"), private=True))
    assert i.response.send_message.calls[0][1]["ephemeral"] is True
    assert i.followup.send.calls == []


def test_deferred_interaction_uses_followup():
    i = _interaction(done=True)
    asyncio.run(send(i, embed("info", "t"), private=True))
    assert i.response.send_message.calls == []
    assert i.followup.send.calls[0][1]["ephemeral"] is True


def test_view_omitted_when_none():
    ctx, i = _ctx(), _interaction()
    asyncio.run(send(ctx, embed("info", "t"), view=None))
    asyncio.run(send(i, embed("info", "t"), view=None))
    assert "view" not in ctx.send.calls[0][1]
    assert "view" not in i.response.send_message.calls[0][1]


def test_view_passed_when_given():
    ctx, view = _ctx(), object()
    asyncio.run(send(ctx, embed("info", "t"), view=view))
    assert ctx.send.calls[0][1]["view"] is view


def test_send_swallows_http_errors():
    error = discord.HTTPException(SimpleNamespace(status=400, reason="x"), "x")
    asyncio.run(send(_ctx(error=error), embed("info", "t")))


def test_block_notices():
    block = lambda kind, text="": SimpleNamespace(kind=kind, text=text)  # noqa: E731
    assert block_notice(block("maintenance", "今晚升级")) == Notice("warning", "小凛正在维护", "今晚升级")
    assert block_notice(block("maintenance")) == Notice("warning", "小凛正在维护", "暂时用不了，请稍后再试。")
    assert block_notice(block("disabled")) == Notice("warning", "这条指令已停用", "机器人主人暂时关闭了这条指令。")
    assert block_notice(block("blacklist")) is None
    assert block_notice(block("blacklist"), component=True) == Notice("error", "你现在不能使用这个功能")


def test_bot_limits_mentions():
    with open(os.path.join(ROOT, "rinbot", "main.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    bot = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HybridBot")
    init = next(n for n in bot.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    call = next(
        n for n in ast.walk(init)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "__init__"
    )
    mentions = {kw.arg: ast.unparse(kw.value) for kw in call.keywords}["allowed_mentions"]
    assert mentions == "discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)"
