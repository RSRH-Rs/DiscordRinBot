import inspect
from types import SimpleNamespace

import discord
from discord import app_commands
from discord.ext import commands

from _messages import Notice
from cogs.errors import UNEXPECTED, notice_for, permission_list, unexpected_notice, usage


@commands.hybrid_command(name="kick")
async def kick(ctx, member: discord.Member, *, reason: str = "未提供原因"):
    pass


def _param(name):
    return commands.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD)


def test_permission_list_joins_and_falls_back():
    assert permission_list(["manage_messages", "embed_links", "create_events"]) == "「管理消息」「嵌入链接」「create events」"


def test_usage_slash_and_prefix():
    assert usage(kick, slash=True) == "/kick <member> [reason]"
    assert usage(kick, slash=False) == "r!kick <member> [reason]"


def test_usage_of_app_command_parameters():
    cmd = SimpleNamespace(
        qualified_name="giveaway end",
        parameters=[SimpleNamespace(name="giveaway_id", required=True), SimpleNamespace(name="note", required=False)],
    )
    assert usage(cmd, slash=True) == "/giveaway end <giveaway_id> [note]"


def test_command_not_found_is_silent():
    assert notice_for(commands.CommandNotFound("x")) is None


def test_member_missing_permissions():
    expected = Notice("error", "你没有权限使用这条指令", "需要「封禁成员」权限。")
    assert notice_for(commands.MissingPermissions(["ban_members"])) == expected
    assert notice_for(app_commands.MissingPermissions(["ban_members"])) == expected


def test_bot_missing_permissions():
    expected = Notice(
        "error",
        "小凛缺少「管理消息」「嵌入链接」权限",
        "请服务器管理员在 服务器设置 → 身份组 里给小凛打开这个权限，再试一次。",
    )
    assert notice_for(commands.BotMissingPermissions(["manage_messages", "embed_links"])) == expected
    assert notice_for(app_commands.BotMissingPermissions(["manage_messages", "embed_links"])) == expected


def test_missing_required_argument():
    error = commands.MissingRequiredArgument(_param("reason"))
    assert notice_for(error, command=kick) == Notice("error", "缺少参数「reason」", "用法：`r!kick <member> [reason]`")
    assert notice_for(error) == Notice("error", "缺少参数「reason」")


def test_cooldown_uses_discord_timestamp():
    error = commands.CommandOnCooldown(commands.Cooldown(1, 5), 2.5, commands.BucketType.user)
    assert notice_for(error, now=1000.0) == Notice("warning", "操作太快了", "<t:1003:R>可以再用。")
    app_error = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 5), 2.0)
    assert notice_for(app_error, now=1000.0) == Notice("warning", "操作太快了", "<t:1002:R>可以再用。")


def test_no_private_message():
    expected = Notice("error", "这条指令只能在服务器里用")
    assert notice_for(commands.NoPrivateMessage()) == expected
    assert notice_for(app_commands.NoPrivateMessage()) == expected


def test_not_found_texts():
    mention = "检查一下有没有打错，或者直接 @ 对方。"
    assert notice_for(commands.MemberNotFound("x")) == Notice("error", "找不到这个成员", mention)
    assert notice_for(commands.UserNotFound("x")) == Notice("error", "找不到这个用户", mention)
    assert notice_for(commands.RoleNotFound("r")) == Notice(
        "error", "找不到这个身份组", "检查一下名字有没有打错，或者直接 @ 这个身份组。"
    )
    assert notice_for(commands.ChannelNotFound("c")) == Notice(
        "error", "找不到这个频道", "检查一下名字有没有打错，或者直接 # 这个频道。"
    )


def test_bad_arguments_show_usage():
    for error in (commands.BadArgument("x"), commands.TooManyArguments("x"), commands.UserInputError("x")):
        assert notice_for(error, command=kick, slash=True) == Notice("error", "参数格式不对", "用法：`/kick <member> [reason]`")
    assert notice_for(commands.BadArgument("x")) == Notice("error", "参数格式不对")


def test_not_owner():
    assert notice_for(commands.NotOwner("x")) == Notice("error", "只有机器人主人能用这条指令")


def test_other_check_failures_are_silent():
    assert notice_for(commands.CheckFailure()) is None
    assert notice_for(app_commands.CheckFailure()) is None


def test_hybrid_error_is_unwrapped():
    error = commands.HybridCommandError(app_commands.MissingPermissions(["kick_members"]))
    assert notice_for(error) == Notice("error", "你没有权限使用这条指令", "需要「踢出成员」权限。")


def test_unknown_errors_are_unexpected():
    assert notice_for(RuntimeError("x")) is UNEXPECTED
    assert notice_for(commands.CommandInvokeError(RuntimeError("x"))) is UNEXPECTED


def test_unexpected_notice_text():
    assert unexpected_notice("AB12CD34") == Notice(
        "error",
        "这条指令没有执行成功",
        "已自动记录，错误编号 `AB12CD34`。稍后再试；一直出错的话，反馈时带上这个编号。",
    )
