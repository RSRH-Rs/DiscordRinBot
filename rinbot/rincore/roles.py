"""RinBot 单选（exclusive）身份组面板的纯逻辑。"""


def exclusive_changes(
    member_role_ids: set[int], panel_role_ids: set[int], chosen: int
) -> tuple[set[int], set[int]]:
    """返回 (to_add, to_remove)。

    成员已有 chosen 时 to_add 为空；to_remove 是成员已有的、属于该面板的其他身份组。
    """
    to_add = set() if chosen in member_role_ids else {chosen}
    to_remove = (member_role_ids & panel_role_ids) - {chosen}
    return to_add, to_remove
