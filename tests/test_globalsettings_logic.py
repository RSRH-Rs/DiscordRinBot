from cogs.globalsettings import decide_block

OWNER = 1
USER = 42
MSG = "维护中"
DISABLED_MSG = "⛔ 该指令已被全局停用。"


def _block(user_id=USER, blacklist=(), maintenance=False, maint_msg=MSG, disabled=(), command_name=None):
    return decide_block(
        user_id, OWNER, set(blacklist), maintenance, maint_msg, set(disabled), command_name
    )


def test_owner_never_blocked():
    assert _block(OWNER, blacklist={OWNER}, maintenance=True, disabled={"ping"}, command_name="ping") is None


def test_blacklisted_silent():
    assert _block(blacklist={USER}, maintenance=True, command_name="ping") == ""


def test_maintenance_message():
    assert _block(maintenance=True) == MSG
    # 维护提示为空时使用默认文案
    assert _block(maintenance=True, maint_msg="").startswith("🔧")


def test_globally_disabled_command():
    assert _block(disabled={"ping"}, command_name="ping") == DISABLED_MSG
    assert _block(disabled={"ping"}, command_name="help") is None
    assert _block(disabled={"ping"}, command_name=None) is None


def test_normal_user_allowed():
    assert _block() is None
    assert _block(command_name="ping") is None
