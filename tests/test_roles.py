from rincore import roles


def test_exclusive_switch():
    assert roles.exclusive_changes({1, 9}, {1, 2, 3}, 2) == ({2}, {1})


def test_exclusive_already_has():
    assert roles.exclusive_changes({2}, {1, 2, 3}, 2) == (set(), set())


def test_exclusive_already_has_and_stray_other():
    assert roles.exclusive_changes({2, 3, 9}, {1, 2, 3}, 2) == (set(), {3})


def test_exclusive_ignores_roles_outside_panel():
    assert roles.exclusive_changes({9}, {1, 2}, 1) == ({1}, set())
