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
