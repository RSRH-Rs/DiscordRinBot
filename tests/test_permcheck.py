import permcheck
from permcheck import base_permissions, checkup

G = "100"
VIEW, SEND, EMBED = 1 << 10, 1 << 11, 1 << 14
ADMIN = 1 << 3
ALL_NEEDED = VIEW | SEND | EMBED


def _all_perm_bits():
    from site_data import PERMISSIONS
    out = 0
    for p in PERMISSIONS:
        out |= 1 << p["bit"]
    return out


def role(rid, perms, position=0, managed=False):
    return {"id": str(rid), "permissions": str(perms), "position": position, "managed": managed}


def member(role_ids, user_id="9"):
    return {"roles": [str(r) for r in role_ids], "user": {"id": user_id}}


def test_administrator_has_everything():
    roles = [role(G, 0), role("5", ADMIN, position=3)]
    out = checkup(roles, member(["5"]), G)
    assert out == {"available": True, "blockers": [], "warnings": []}


def test_base_merges_everyone_and_roles():
    roles = [role(G, VIEW), role("5", SEND), role("6", EMBED)]
    assert base_permissions(roles, ["5"], G) == VIEW | SEND
    assert base_permissions(roles, [5, 6], int(G)) == ALL_NEEDED


def test_missing_required_is_blocker():
    from site_data import PERMISSIONS
    names = {p["bit"]: p["zh"] for p in PERMISSIONS}
    for bit in (10, 11, 14):
        have = _all_perm_bits() & ~(1 << bit)
        out = checkup([role(G, have)], member([]), G)
        assert [b["perm"] for b in out["blockers"]] == [names[bit]]
        assert out["blockers"][0]["code"] == "missing_perm"
        assert out["blockers"][0]["lose"]
        assert out["warnings"] == []


def test_missing_other_is_warning():
    have = _all_perm_bits() & ~(1 << 40)
    out = checkup([role(G, have)], member([]), G)
    assert out["blockers"] == []
    assert out["warnings"] == [
        {"code": "missing_perm", "perm": next(
            p["zh"] for p in permcheck.PERMISSIONS if p["bit"] == 40),
         "lose": "禁言相关的功能都不能用"}]


def test_role_limits():
    roles = [
        {"id": "1", "name": "@everyone", "permissions": "0", "position": 0},
        {"id": "2", "name": "Rin", "permissions": str(1 << 28), "position": 5, "managed": True},
        {"id": "3", "name": "low", "permissions": "0", "position": 2},
        {"id": "4", "name": "same", "permissions": "0", "position": 5},
        {"id": "5", "name": "high", "permissions": "0", "position": 9},
        {"id": "6", "name": "bot", "permissions": "0", "position": 1, "managed": True},
    ]
    result = permcheck.role_limits(roles, {"roles": ["2"]}, "1")
    assert result == {"can_manage_roles": True, "blocked": {"2": "managed", "4": "above", "5": "above", "6": "managed"}}


def test_role_limits_permission_bits():
    lacking = [role(G, 0), role("5", SEND, position=3)]
    assert permcheck.role_limits(lacking, member(["5"]), G)["can_manage_roles"] is False
    admin = [role(G, 0), role("5", ADMIN, position=3)]
    assert permcheck.role_limits(admin, member(["5"]), G)["can_manage_roles"] is True
    everyone = [role(G, 1 << 28), role("5", 0, position=3)]
    assert permcheck.role_limits(everyone, member(["5"]), G)["can_manage_roles"] is True
