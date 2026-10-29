"""Name matching helpers."""

from __future__ import annotations

import re
import unicodedata

_DROP = re.compile(r"[™®©]|\((tm|r|c)\)", re.IGNORECASE)
_SEPARATORS = re.compile(r"[:\-_/–—.,]")
_KEEP = re.compile(r"[^a-z0-9+# ]")
_SPACES = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Lower-case, strip accents, symbols and punctuation: 'ELDEN RING™' -> 'elden ring'."""
    text = unicodedata.normalize("NFKD", _DROP.sub("", name))  # drop ™ before NFKD makes it "TM"
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ").replace("'", "")
    text = _SEPARATORS.sub(" ", text)
    text = _KEEP.sub("", text)
    return _SPACES.sub(" ", text).strip()


def compact(name: str) -> str:
    """normalize() without spaces, so 'BrownDust2' and 'Brown Dust 2' compare equal."""
    return normalize(name).replace(" ", "")


def starts_with_words(name: str, prefix: str) -> bool:
    """True when normalized `name` equals `prefix` or begins with it as whole words."""
    return name == prefix or name.startswith(prefix + " ")
