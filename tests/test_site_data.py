"""官网共用数据（website/site_data.py）：邀请链接、16 项权限、指令分组。"""
import site_data as sd

OLD = (
    "https://discord.com/oauth2/authorize?client_id=1352551616427069492"
    "&permissions=1374694796438&integration_type=0&scope=bot+applications.commands"
)


def test_permission_bits_add_up_to_the_invite():
    assert len(sd.PERMISSIONS) == 16
    assert sum(1 << p["bit"] for p in sd.PERMISSIONS) == sd.INVITE_PERMISSIONS
    assert len({p["bit"] for p in sd.PERMISSIONS}) == 16


def test_invite_url_is_unchanged():
    assert sd.invite_url() == OLD
    assert "permissions=6&" in sd.invite_url(6)


def test_console_invite_returns_to_the_site():
    url = sd.console_invite_url()
    assert "scope=bot+applications.commands+identify" in url and "response_type=code" in url
    assert "redirect_uri=https%3A%2F%2Frin-bot.com%2Finvited" in url and "permissions=1374694796438" in url


def test_console_invite_can_preselect_a_server():
    assert "&guild_id=5&disable_guild_select=true" in sd.console_invite_url(5)


def test_never_bits_are_not_requested():
    assert [n["bit"] for n in sd.NEVER] == [3, 5, 17, 29]
    assert all(not sd.INVITE_PERMISSIONS >> n["bit"] & 1 for n in sd.NEVER)


def test_groups_are_complete():
    assert [g["key"] for g in sd.PERMISSION_GROUPS] == ["msg", "voice", "roles", "mod", "log"]
    assert {p["group"] for p in sd.PERMISSIONS} == {g["key"] for g in sd.PERMISSION_GROUPS}
    keys = [g["key"] for g in sd.COMMAND_GROUPS]
    assert len(keys) == 10 == len(set(keys)) and keys[0] == "Music" and keys[-1] == "System"
    for entry in sd.PERMISSIONS + sd.COMMAND_GROUPS:
        assert all(entry[k] for k in entry if k.endswith(("zh", "en")) and k not in ("dashboard_zh", "dashboard_en"))


def test_perm_text_names_every_permission():
    assert sd.perm_text(["ban_members"]) == ("封禁成员", "Ban Members")
    assert sd.perm_text(["ban_members", "manage_messages"]) == ("封禁成员、管理消息", "Ban Members, Manage Messages")
    assert sd.perm_text([]) == ("", "")
