import asyncio
import os
from types import SimpleNamespace

import discord

from cogs import general, giveaway, help as help_cog, moderation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICK = moderation.Moderation.kick
ROLL = general.General.roll
SETSTATUS = general.General.setstatus
GIVEAWAY_LIST = giveaway.Giveaway.giveaway_group.get_command("list")


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_status_fields():
    bot = SimpleNamespace(latency=0.041, start_time=1790000000, guilds=[object(), object()])
    ctx = SimpleNamespace(send=_Recorder())
    asyncio.run(general.General.status.callback(general.General(bot), ctx))
    e = ctx.send.calls[0][1]["embed"]
    assert e.title == "小凛的运行状态"
    assert e.color.value == 0xEB8BAC
    assert [(f.name, f.value) for f in e.fields] == [
        ("延迟", "41 毫秒"),
        ("上次启动", "<t:1790000000:R>"),
        ("服务器", "2 个"),
    ]
    assert e.footer.text is None


def test_status_has_no_host_info():
    with open(os.path.join(ROOT, "rinbot", "cogs", "general.py"), encoding="utf-8") as f:
        source = f.read()
    assert "psutil" not in source and "platform" not in source
    with open(os.path.join(ROOT, "rinbot", "requirements.txt"), encoding="utf-8") as f:
        assert "psutil" not in f.read()
    from rincore import command_i18n

    assert command_i18n.zh_description("status") == "查看小凛的运行状态"


def test_member_sees_no_admin_commands():
    assert help_cog.visible(KICK, discord.Permissions.none()) is False
    assert help_cog.visible(ROLL, discord.Permissions.none()) is True


def test_dm_shows_only_open_commands():
    assert help_cog.visible(KICK, None) is False
    assert help_cog.visible(ROLL, None) is True


def test_manager_sees_giveaway_subcommands():
    assert help_cog.visible(GIVEAWAY_LIST, discord.Permissions(manage_guild=True)) is True
    assert help_cog.visible(GIVEAWAY_LIST, discord.Permissions.none()) is False


def test_owner_commands_never_visible():
    assert help_cog.visible(SETSTATUS, discord.Permissions.all()) is False


async def test_menu_rejects_other_users():
    bot = SimpleNamespace(get_cog=lambda name: None, user=None)
    view = help_cog.HelpView(bot, owner_id=1, owner_name="小明")
    send = _Recorder()
    other = SimpleNamespace(
        user=SimpleNamespace(id=2),
        response=SimpleNamespace(is_done=lambda: False, send_message=send),
        followup=SimpleNamespace(send=_Recorder()),
    )
    assert await view.interaction_check(other) is False
    (args, kwargs), = send.calls
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "这个菜单是 小明 打开的"
    assert kwargs["embed"].description == "你可以自己输入 /help。"
    owner = SimpleNamespace(user=SimpleNamespace(id=1))
    assert await view.interaction_check(owner) is True
