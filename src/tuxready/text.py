from __future__ import annotations

import re
import unicodedata

_DROP = re.compile(r"[™®©]|\((tm|r|c)\)", re.IGNORECASE)
_SEPARATORS = re.compile(r"[:\-_/–—.,]")
_KEEP = re.compile(r"[^a-z0-9+# ]")
_SPACES = re.compile(r"\s+")


def normalize(name: str) -> str:
    # 'ELDEN RING™' -> 'elden ring'
    # strip ™ first, NFKD would turn it into "TM"
    text = unicodedata.normalize("NFKD", _DROP.sub("", name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ").replace("'", "")
    text = _SEPARATORS.sub(" ", text)
    text = _KEEP.sub("", text)
    return _SPACES.sub(" ", text).strip()


def strip_marks(name: str) -> str:
    # for display: 'Intel(R) Arc(TM) 140V' -> 'Intel Arc 140V'
    return _SPACES.sub(" ", _DROP.sub("", name)).strip()


def compact(name: str) -> str:
    return normalize(name).replace(" ", "")


def starts_with_words(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + " ")
