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
