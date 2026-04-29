import re

_ASTERISK_PATTERN = re.compile(r"\*[^*]*\*")
_BRACKET_PATTERN = re.compile(r"\[[^\]]*\]")


def sanitize(text: str) -> str:
    text = _ASTERISK_PATTERN.sub("", text)
    text = _BRACKET_PATTERN.sub("", text)
    return text.strip()
