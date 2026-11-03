"""Console strings: one dictionary (i18n/zh.json) shared by Jinja and the page JS."""
import json
import logging
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "i18n" / "zh.json"
_log = logging.getLogger("rinbot.i18n")
_strings = None


def _flatten(node, prefix=""):
    flat = {}
    for key, value in node.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, name))
        else:
            flat[name] = value
    return flat


def console_strings() -> dict:
    global _strings
    if _strings is None:
        with open(_PATH, encoding="utf-8") as f:
            _strings = _flatten(json.load(f))
    return _strings


def tr(key: str, **variables) -> str:
    text = console_strings().get(key)
    if text is None:
        _log.warning("missing console string: %s", key)
        return key
    for name, value in variables.items():
        text = text.replace("{" + name + "}", str(value))
    return text
