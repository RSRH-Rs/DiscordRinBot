"""违禁词与链接匹配（纯函数，供 automod 使用）。规则见设计文档 2.1。"""

import re
import unicodedata
from functools import lru_cache
from typing import Iterable, Optional
from urllib.parse import urlparse

# 零宽字符：U+200B–U+200D、U+2060、U+FEFF
_ZERO_WIDTH = re.compile("[​-‍⁠﻿]")
# 非 ASCII 词匹配时额外忽略的空白与常见分隔符
_SEPARATORS = re.compile(r"[\s.\-_*·]+")

# 链接：先匹配带协议的 URL，其余再找无协议域名（单个正则，保证同一段文字只算一次）
_LINK_RE = re.compile(
    r"https?://[^\s<>]+"
    r"|(?<![\w@./:\-])"  # 前面不能是邮箱 @、已属于别的域名/路径的字符
    r"(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+[a-z]{2,}"  # 域名，顶级域必须是字母
    r"(?![\w@\-])"
    r"(?::\d+)?(?:/[^\s<>]*)?",
    re.IGNORECASE,
)
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}'\"，。！？、）"


def normalize(text: str) -> str:
    """NFKC → 小写 → 去零宽字符。"""
    return _ZERO_WIDTH.sub("", unicodedata.normalize("NFKC", text).lower())


@lru_cache(maxsize=2048)
def _prepare_word(word: str):
    """归一化配置词；返回 (整词正则或 None, 归一化词, 去分隔符词)，空词返回 None。"""
    nword = normalize(word).strip()
    if not nword:
        return None
    if nword.isascii() and nword.isalnum():
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(nword) + r"(?![a-z0-9])")
        return pattern, nword, ""
    return None, nword, _SEPARATORS.sub("", nword)


def find_badword(text: str, words: Iterable[str]) -> Optional[str]:
    """返回第一个命中的违禁词（配置里的原始写法），没有命中返回 None。"""
    ntext = normalize(text)
    stripped = None  # 惰性计算：只有出现非 ASCII 词时才需要
    for word in words:
        prepared = _prepare_word(str(word))
        if prepared is None:
            continue
        pattern, nword, sword = prepared
        if pattern is not None:
            if pattern.search(ntext):
                return word
            continue
        if nword in ntext:
            return word
        if sword:
            if stripped is None:
                stripped = _SEPARATORS.sub("", ntext)
            if sword in stripped:
                return word
    return None


def find_links(text: str) -> list[str]:
    """识别带协议链接、无协议域名与 Discord 邀请；排除邮箱、版本号、纯数字。"""
    links = []
    for match in _LINK_RE.finditer(normalize(text)):
        link = match.group().rstrip(_TRAILING_PUNCT)
        if link:
            links.append(link)
    return links


def host_of(link: str) -> str:
    """补全协议后取小写主机名；解析失败返回空串。"""
    if not _SCHEME_RE.match(link):
        link = "http://" + link
    try:
        host = urlparse(link).hostname
    except ValueError:
        return ""
    return (host or "").lower().rstrip(".")


def is_whitelisted(host: str, whitelist: Iterable[str]) -> bool:
    """主机等于白名单域名或为其子域；白名单可写 *.example.com。"""
    if not host:
        return False
    for domain in whitelist:
        d = str(domain).lower().strip().lstrip("*.").rstrip(".")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False
