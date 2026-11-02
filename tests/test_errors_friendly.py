import inspect

from discord.ext import commands

from cogs.errors import _friendly

GENERIC = "参数有误，请检查后重试。"


def test_too_many_arguments_is_friendly():
    assert _friendly(commands.TooManyArguments("x")) == GENERIC


def test_bad_literal_argument_is_friendly():
    param = commands.Parameter("mode", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    err = commands.BadLiteralArgument(param, ("a", "b"), [], "c")
    assert _friendly(err) == GENERIC


def test_generic_user_input_error_is_friendly():
    assert _friendly(commands.UserInputError("x")) == GENERIC


def test_missing_required_argument_keeps_own_text():
    param = commands.Parameter("reason", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    assert _friendly(commands.MissingRequiredArgument(param)) == "❓ 缺少参数：`reason`。"


def test_specific_not_found_texts_unchanged():
    assert _friendly(commands.RoleNotFound("r")) == "找不到该身份组。"
    assert _friendly(commands.ChannelNotFound("c")) == "找不到该频道。"
