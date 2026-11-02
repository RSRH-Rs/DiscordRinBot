from rincore import textmatch
from rincore.textmatch import find_badword, find_links, host_of, is_whitelisted


def test_whole_word_ascii_does_not_match_inside_word():
    assert find_badword("this is class", ["ass"]) is None


def test_whole_word_ascii_matches_standalone():
    assert find_badword("what an ass.", ["ass"]) == "ass"


def test_fullwidth_matches():
    assert find_badword("ＡＳＳ", ["ass"]) == "ass"


def test_zero_width_matches():
    assert find_badword("a​ss", ["ass"]) == "ass"


def test_cjk_with_spaces_matches():
    assert find_badword("违 禁 词", ["违禁词"]) == "违禁词"


def test_cjk_with_separators_matches():
    assert find_badword("违.禁.词", ["违禁词"]) == "违禁词"


def test_cjk_plain_substring_matches():
    assert find_badword("这是违禁词啊", ["违禁词"]) == "违禁词"


def test_blank_words_ignored():
    assert find_badword("hello", ["", "  "]) is None


def test_separator_only_word_ignored():
    # 去分隔符后词为空，不能因此匹配任何文本
    assert find_badword("abc", ["..", "- -"]) is None


def test_returns_original_word():
    assert find_badword("You ASS", ["Ass"]) == "Ass"


def test_normalize():
    assert textmatch.normalize("Ａb‍﻿C") == "abc"


def test_links_detected():
    assert len(find_links("see example.com/x")) == 1
    assert len(find_links("www.example.com")) == 1
    assert len(find_links("discord.gg/abc")) == 1
    assert len(find_links("https://a.b/c")) == 1


def test_discord_invite_variants():
    assert find_links("join discord.com/invite/abc now") == ["discord.com/invite/abc"]
    assert find_links("discordapp.com/invite/abc") == ["discordapp.com/invite/abc"]


def test_scheme_url_counted_once():
    assert find_links("https://www.example.com/path?q=1") == [
        "https://www.example.com/path?q=1"
    ]


def test_trailing_punctuation_stripped():
    assert find_links("go to example.com.") == ["example.com"]
    assert find_links("(see https://example.com/a)") == ["https://example.com/a"]


def test_links_not_detected():
    assert find_links("me@example.com") == []
    assert find_links("v1.2.3") == []
    assert find_links("pi is 3.14") == []


def test_discord_markup_is_not_a_link():
    assert find_links("<:pepe:123456789>") == []
    assert find_links("<@123456789> <#987654321> <a:dance:111>") == []


def test_obfuscated_link_detected():
    assert len(find_links("exa​mple.com")) == 1
    assert len(find_links("ｅｘａｍｐｌｅ.com")) == 1


def test_host_of():
    assert host_of("https://CDN.Example.com:8080/x") == "cdn.example.com"
    assert host_of("example.com/x") == "example.com"
    assert host_of("discord.gg/abc") == "discord.gg"
    assert host_of("http://[bad") == ""


def test_whitelist_subdomain():
    assert is_whitelisted("cdn.example.com", ["example.com"])
    assert is_whitelisted("example.com", ["example.com"])


def test_whitelist_rejects_lookalike():
    assert not is_whitelisted("badexample.com", ["example.com"])


def test_whitelist_wildcard():
    assert is_whitelisted("x.example.com", ["*.example.com"])


def test_whitelist_ignores_blank_and_empty_host():
    assert not is_whitelisted("example.com", ["", "  "])
    assert not is_whitelisted("", ["example.com"])
