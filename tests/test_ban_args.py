from cogs.moderation import DEFAULT_REASON, resolve_ban_args


def test_prefix_digit_reason_is_folded_back_and_no_deletion():
    assert resolve_ban_args(False, 3, "次刷屏") == (0, "3 次刷屏")


def test_prefix_digit_only_uses_digit_as_reason():
    assert resolve_ban_args(False, 5, DEFAULT_REASON) == (0, "5")


def test_prefix_default_unchanged():
    assert resolve_ban_args(False, 0, "spam") == (0, "spam")
    assert resolve_ban_args(False, 0, DEFAULT_REASON) == (0, DEFAULT_REASON)


def test_slash_keeps_delete_days():
    assert resolve_ban_args(True, 3, "次刷屏") == (3, "次刷屏")
    assert resolve_ban_args(True, 7, DEFAULT_REASON) == (7, DEFAULT_REASON)
