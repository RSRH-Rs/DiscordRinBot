from rincore import durations


def test_parse_combined_units():
    assert durations.parse_duration("1d12h") == 129600


def test_parse_simple_and_case_whitespace():
    assert durations.parse_duration("30m") == 1800
    assert durations.parse_duration(" 2H ") == 7200


def test_parse_rejects_repeated_unit():
    assert durations.parse_duration("1h1h") is None


def test_parse_upper_bound_365_days():
    assert durations.parse_duration("365d") == 365 * 86400
    assert durations.parse_duration("366d") is None


def test_parse_rejects_garbage_and_zero():
    assert durations.parse_duration("abc") is None
    assert durations.parse_duration("") is None
    assert durations.parse_duration("0s") is None
    assert durations.parse_duration("10") is None


def test_format_matches_previous_moderation_output():
    # 迁移前 Moderation._format_duration 的实际输出（写死以防回归）
    assert durations.format_duration(3600) == "1小时"
    assert durations.format_duration(0) == "0秒"
    assert durations.format_duration(45) == "45秒"
    assert durations.format_duration(61) == "1分钟 1秒"
    assert durations.format_duration(3661) == "1小时 1分钟 1秒"
    assert durations.format_duration(129600) == "1天 12小时"
    # 有天数时不显示秒
    assert durations.format_duration(90061) == "1天 1小时 1分钟"
    assert durations.format_duration(86401) == "1天"


def test_parse_weeks_and_chinese_units():
    assert durations.parse_duration("1w") == 604800
    assert durations.parse_duration("10分钟") == 600
    assert durations.parse_duration("1小时30分钟") == 5400
    assert durations.parse_duration("2 天") == 172800
    assert durations.parse_duration("1星期") == 604800
    assert durations.parse_duration("3日") == 259200
    assert durations.parse_duration("1H30M") == 5400
    assert durations.parse_duration("1 小时 30 分钟") == 5400
    assert durations.parse_duration("45秒") == 45


def test_parse_rejects_repeated_mixed_units():
    assert durations.parse_duration("1h1小时") is None
    assert durations.parse_duration("1周1w") is None


def test_canonical_and_label():
    assert durations.canonical(5400) == "1h30m"
    assert durations.canonical(604800) == "7d"
    assert durations.canonical(45) == "45s"
    assert durations.label(5400, True) == "1 小时 30 分钟"
    assert durations.label(5400, False) == "1 hour 30 minutes"
    assert durations.label(3600, False) == "1 hour"
    assert durations.label(172800, False) == "2 days"
    assert durations.label(0, True) == "关闭"
    assert durations.label(0, False) == "Off"


def _values(items):
    return [value for _, value in items]


def test_suggest_empty_gives_presets():
    got = durations.suggest("", durations.PRESETS["mute"], durations.LIMITS["mute"], True)
    assert _values(got) == ["10m", "1h", "1d", "7d", "28d"]
    assert got[0] == ("10 分钟", "10m")


def test_suggest_digit_spreads_units_within_limit():
    got = durations.suggest("3", durations.PRESETS["mute"], durations.LIMITS["mute"], True)
    assert _values(got) == ["3m", "3h", "3d", "21d"]
    assert "35d" not in _values(durations.suggest("5", durations.PRESETS["mute"], durations.LIMITS["mute"], True))
    assert _values(durations.suggest("5", durations.PRESETS["mute"], durations.LIMITS["mute"], False))[:3] == ["5m", "5h", "5d"]


def test_suggest_parsed_first():
    got = durations.suggest("1h30m", durations.PRESETS["ban"], durations.LIMITS["ban"], True)
    assert got[0] == ("1 小时 30 分钟", "1h30m")
    assert _values(got)[1:] == ["1d", "7d", "30d"]
    english = durations.suggest("1h30m", durations.PRESETS["ban"], durations.LIMITS["ban"], False)
    assert english[0] == ("1 hour 30 minutes", "1h30m")


def test_suggest_dedupes_and_ignores_garbage():
    assert _values(durations.suggest("1d", durations.PRESETS["ban"], durations.LIMITS["ban"], True)) == ["1d", "7d", "30d"]
    assert _values(durations.suggest("abc", durations.PRESETS["ban"], durations.LIMITS["ban"], True)) == ["1d", "7d", "30d"]


def test_suggest_off_preset():
    got = durations.suggest("", durations.PRESETS["slowmode"], durations.LIMITS["slowmode"], True)
    assert got[0] == ("关闭", "0")
    assert got[1] == ("5 秒", "5s")


def test_suggest_at_most_25():
    assert len(durations.suggest("1", list(range(1, 100)), 10**9, True)) <= 25
