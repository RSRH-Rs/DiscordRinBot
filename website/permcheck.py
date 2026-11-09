"""根据 Discord 返回的 roles 和小凛的成员信息，算出小凛在服务器里缺哪些权限。"""
from site_data import PERMISSIONS

ADMINISTRATOR = 1 << 3
MANAGE_ROLES = 1 << 28
_ESSENTIAL_BITS = (10, 11, 14)  # 查看频道、发送消息、嵌入链接：缺了小凛基本什么都做不了


def base_permissions(roles, member_role_ids, guild_id):
    ids = {str(r) for r in member_role_ids} | {str(guild_id)}
    perms = 0
    for r in roles:
        if str(r["id"]) in ids:
            perms |= int(r.get("permissions") or 0)
    return perms


def role_limits(roles, bot_member, guild_id):
    """小凛有没有“管理身份组”权限，以及哪些身份组它给不了（托管，或不低于自己最高身份组）。"""
    member_roles = {str(r) for r in bot_member.get("roles") or []}
    base = base_permissions(roles, member_roles, guild_id)
    top = max((int(r.get("position") or 0) for r in roles if str(r["id"]) in member_roles), default=0)
    blocked = {}
    for r in roles:
        role_id = str(r["id"])
        if role_id == str(guild_id):
            continue
        if r.get("managed"):
            blocked[role_id] = "managed"
        elif int(r.get("position") or 0) >= top:
            blocked[role_id] = "above"
    return {"can_manage_roles": bool(base & (ADMINISTRATOR | MANAGE_ROLES)), "blocked": blocked}


def checkup(roles, bot_member, guild_id):
    member_roles = [str(r) for r in bot_member.get("roles") or []]
    base = base_permissions(roles, member_roles, guild_id)
    blockers, warnings = [], []

    if not base & ADMINISTRATOR:
        for p in PERMISSIONS:
            if base & (1 << p["bit"]):
                continue
            item = {"code": "missing_perm", "perm": p["zh"], "lose": p["lose_zh"]}
            (blockers if p["bit"] in _ESSENTIAL_BITS else warnings).append(item)

    return {"available": True, "blockers": blockers, "warnings": warnings}
